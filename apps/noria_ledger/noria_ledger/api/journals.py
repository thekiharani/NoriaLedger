"""Journal entries: create, post (submit), reverse, cancel — via ERPNext controllers.

Lifecycle exposed to Noria users:
  Draft (docstatus 0) -> Posted (submit, docstatus 1) -> Reversed (a new posted
  reversing entry) or Cancelled (ERPNext cancel, which posts reversing GL rows).
"""

from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from noria_ledger.service import (
	doc_summary,
	find_idempotent_result,
	get_company,
	parse_json_arg,
	posting_date_filter,
	service_endpoint,
	to_decimal,
)

MAX_LINES = 500


def _company_account(account: str, company: str) -> dict:
	row = frappe.db.get_value(
		"Account",
		{"name": account, "company": company},
		["name", "is_group", "disabled", "account_type"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Account {0} does not belong to {1}").format(account, company))
	if row.is_group:
		frappe.throw(_("Account {0} is a group account and cannot be posted to").format(account))
	if row.disabled:
		frappe.throw(_("Account {0} is disabled").format(account))
	return row


def build_journal_entry(company: str, posting_date, lines: list[dict], user_remark=None, cheque_no=None, cheque_date=None):
	if not lines or len(lines) < 2:
		frappe.throw(_("A journal entry needs at least two lines"))
	if len(lines) > MAX_LINES:
		frappe.throw(_("A journal entry can have at most {0} lines").format(MAX_LINES))

	total_debit = Decimal("0")
	total_credit = Decimal("0")
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = getdate(posting_date or nowdate())
	je.user_remark = user_remark
	je.cheque_no = cheque_no
	je.cheque_date = getdate(cheque_date) if cheque_date else None

	for idx, line in enumerate(lines, start=1):
		debit = to_decimal(line.get("debit"), f"line {idx} debit")
		credit = to_decimal(line.get("credit"), f"line {idx} credit")
		if debit < 0 or credit < 0:
			frappe.throw(_("Line {0}: amounts cannot be negative").format(idx))
		if (debit > 0) == (credit > 0):
			frappe.throw(_("Line {0}: enter either a debit or a credit amount").format(idx))
		account = _company_account(line.get("account"), company)
		row = {
			"account": account.name,
			"debit_in_account_currency": float(debit),
			"credit_in_account_currency": float(credit),
			"user_remark": line.get("remark"),
		}
		if line.get("party_type") and line.get("party"):
			if line["party_type"] not in ("Customer", "Supplier"):
				frappe.throw(_("Line {0}: unsupported party type").format(idx))
			row["party_type"] = line["party_type"]
			row["party"] = line["party"]
		if line.get("cost_center"):
			row["cost_center"] = line["cost_center"]
		je.append("accounts", row)
		total_debit += debit
		total_credit += credit

	if total_debit != total_credit:
		frappe.throw(
			_("Journal entry is not balanced: debits {0} vs credits {1}").format(total_debit, total_credit)
		)
	return je


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("journals.list")
def list_entries(status: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 100, start: int = 0):
	filters = {"company": get_company()}
	if status == "Draft":
		filters["docstatus"] = 0
	elif status == "Posted":
		filters["docstatus"] = 1
	elif status == "Cancelled":
		filters["docstatus"] = 2
	if date_filter := posting_date_filter(from_date, to_date):
		filters["posting_date"] = date_filter
	return frappe.get_all(
		"Journal Entry",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"voucher_type",
			"total_debit",
			"total_credit",
			"user_remark",
			"docstatus",
			"reversal_of",
			"noria_acting_user",
			"modified",
		],
		order_by="posting_date desc, creation desc",
		limit=min(int(limit), 500),
		start=int(start),
	)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("journals.get")
def get(name: str):
	doc = frappe.get_doc("Journal Entry", name)
	if doc.company != get_company():
		raise frappe.DoesNotExistError
	return {
		**doc_summary(doc),
		"posting_date": str(doc.posting_date),
		"user_remark": doc.user_remark,
		"total_debit": doc.total_debit,
		"total_credit": doc.total_credit,
		"reversal_of": doc.get("reversal_of"),
		"acting_user": doc.get("noria_acting_user"),
		"lines": [
			{
				"account": a.account,
				"debit": a.debit_in_account_currency,
				"credit": a.credit_in_account_currency,
				"party_type": a.party_type,
				"party": a.party,
				"remark": a.user_remark,
			}
			for a in doc.accounts
		],
	}


@frappe.whitelist(methods=["POST"])
@service_endpoint("journals.create", write=True)
def create(
	posting_date: str,
	lines: list | str,
	user_remark: str | None = None,
	cheque_no: str | None = None,
	cheque_date: str | None = None,
	submit: bool = False,
	idempotency_key: str | None = None,
):
	if existing := find_idempotent_result(idempotency_key):
		return doc_summary(frappe.get_doc(existing.reference_doctype, existing.reference_name), idempotent_replay=True)
	je = build_journal_entry(
		get_company(), posting_date, parse_json_arg(lines, "lines"), user_remark, cheque_no, cheque_date
	)
	je.insert()
	if frappe.utils.sbool(submit):
		je.submit()
	return doc_summary(je, total=je.total_debit)


@frappe.whitelist(methods=["POST"])
@service_endpoint("journals.record_simple", write=True)
def record_simple(
	kind: str,
	posting_date: str,
	amount: str | float,
	cash_account: str,
	category_account: str,
	description: str | None = None,
	reference: str | None = None,
	submit: bool = True,
	idempotency_key: str | None = None,
):
	"""Income / expense recording for simple bookkeeping clients.

	kind=income : Dr cash/bank, Cr income (category) account
	kind=expense: Dr expense (category) account, Cr cash/bank
	"""
	if existing := find_idempotent_result(idempotency_key):
		return doc_summary(frappe.get_doc(existing.reference_doctype, existing.reference_name), idempotent_replay=True)
	company = get_company()
	value = to_decimal(amount)
	if value <= 0:
		frappe.throw(_("Amount must be greater than zero"))
	cash = _company_account(cash_account, company)
	if cash.account_type not in ("Cash", "Bank"):
		frappe.throw(_("{0} is not a cash or bank account").format(cash_account))
	category_root = frappe.db.get_value("Account", category_account, "root_type")
	if kind == "income":
		if category_root != "Income":
			frappe.throw(_("{0} is not an income account").format(category_account))
		lines = [{"account": cash_account, "debit": value}, {"account": category_account, "credit": value}]
	elif kind == "expense":
		if category_root != "Expense":
			frappe.throw(_("{0} is not an expense account").format(category_account))
		lines = [{"account": category_account, "debit": value}, {"account": cash_account, "credit": value}]
	else:
		frappe.throw(_("kind must be 'income' or 'expense'"))
	je = build_journal_entry(company, posting_date, lines, user_remark=description, cheque_no=reference, cheque_date=posting_date if reference else None)
	je.voucher_type = "Cash Entry" if cash.account_type == "Cash" else "Bank Entry"
	je.insert()
	if frappe.utils.sbool(submit):
		je.submit()
	return doc_summary(je, total=je.total_debit)


@frappe.whitelist(methods=["POST"])
@service_endpoint("journals.submit", write=True)
def submit(name: str):
	doc = frappe.get_doc("Journal Entry", name)
	if doc.company != get_company():
		raise frappe.DoesNotExistError
	doc.submit()
	return doc_summary(doc)


@frappe.whitelist(methods=["POST"])
@service_endpoint("journals.reverse", write=True)
def reverse(name: str, posting_date: str | None = None, idempotency_key: str | None = None):
	"""Post a reversing journal entry (ERPNext make_reverse_journal_entry)."""
	if existing := find_idempotent_result(idempotency_key):
		return doc_summary(frappe.get_doc(existing.reference_doctype, existing.reference_name), idempotent_replay=True)
	from erpnext.accounts.doctype.journal_entry.journal_entry import make_reverse_journal_entry

	source = frappe.get_doc("Journal Entry", name)
	if source.company != get_company() or source.docstatus != 1:
		frappe.throw(_("Only posted journal entries can be reversed"))
	reversal = make_reverse_journal_entry(name)
	reversal.posting_date = getdate(posting_date or nowdate())
	reversal.user_remark = _("Reversal of {0}").format(name)
	reversal.insert()
	reversal.submit()
	return doc_summary(reversal, reversal_of=name)


@frappe.whitelist(methods=["POST"])
@service_endpoint("journals.cancel", write=True)
def cancel(name: str):
	"""ERPNext cancel: posts reversing GL entries and marks the voucher cancelled."""
	doc = frappe.get_doc("Journal Entry", name)
	if doc.company != get_company():
		raise frappe.DoesNotExistError
	doc.cancel()
	return doc_summary(doc)


@frappe.whitelist(methods=["POST"])
@service_endpoint("journals.delete_draft", write=True)
def delete_draft(name: str):
	doc = frappe.get_doc("Journal Entry", name)
	if doc.company != get_company() or doc.docstatus != 0:
		frappe.throw(_("Only draft journal entries can be deleted"))
	frappe.delete_doc("Journal Entry", name)
	return {"doctype": "Journal Entry", "name": name, "deleted": True}
