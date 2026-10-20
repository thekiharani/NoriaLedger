"""Bank accounts, statement import, matching suggestions and reconciliation.

Imported lines become ERPNext Bank Transactions; matching and reconciliation use
ERPNext's Bank Reconciliation Tool functions, so clearance dates and allocation
follow upstream rules.
"""

import base64
import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, now_datetime

from noria_ledger.importers import get_parser
from noria_ledger.importers.base import StatementError
from noria_ledger.service import (
	doc_summary,
	find_idempotent_result,
	get_company,
	parse_json_arg,
	service_endpoint,
)

MAX_STATEMENT_BYTES = 5 * 1024 * 1024


def _bank_account(name: str) -> dict:
	row = frappe.db.get_value(
		"Bank Account",
		{"name": name, "company": get_company(), "is_company_account": 1},
		["name", "account", "company", "bank"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Bank account {0} not found").format(name))
	return row


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("banking.accounts")
def accounts():
	company = get_company()
	rows = frappe.get_all(
		"Bank Account",
		filters={"company": company, "is_company_account": 1, "disabled": 0},
		fields=["name", "account_name", "bank", "account", "bank_account_no"],
	)
	for r in rows:
		r["unreconciled"] = frappe.db.count(
			"Bank Transaction", {"bank_account": r["name"], "docstatus": 1, "status": "Unreconciled"}
		)
		r["gl_balance"] = flt(
			frappe.db.sql(
				"select sum(debit)-sum(credit) from `tabGL Entry` where account=%s and is_cancelled=0",
				r["account"],
			)[0][0]
		)
	return rows


@frappe.whitelist(methods=["POST"])
@service_endpoint("banking.create_account", write=True)
def create_account(
	bank_name: str,
	account_name: str,
	account_number: str | None = None,
	gl_account: str | None = None,
	idempotency_key: str | None = None,
):
	"""Create a company bank account; creates its GL account under Bank Accounts if needed."""
	if existing := find_idempotent_result(idempotency_key):
		return doc_summary(frappe.get_doc(existing.reference_doctype, existing.reference_name), idempotent_replay=True)
	company = get_company()
	if not frappe.db.exists("Bank", bank_name):
		# ERPNext lets only System Manager create the Bank master (a bank *name*
		# reference with no ledger impact). Create just that record without
		# granting the service user System Manager.
		frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True)

	if gl_account:
		acc_type = frappe.db.get_value("Account", {"name": gl_account, "company": company, "is_group": 0}, "account_type")
		if acc_type not in ("Bank", "Cash"):
			frappe.throw(_("{0} is not a bank or cash GL account").format(gl_account))
	else:
		parent = frappe.db.get_value(
			"Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name"
		) or frappe.db.get_value("Account", {"company": company, "account_name": "Bank Accounts", "is_group": 1}, "name")
		if not parent:
			frappe.throw(_("No 'Bank Accounts' group found in the chart of accounts"))
		gl = frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"parent_account": parent,
				"account_name": f"{bank_name} - {account_name}"[:120],
				"account_type": "Bank",
				"is_group": 0,
			}
		).insert()
		gl_account = gl.name

	ba = frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": account_name,
			"bank": bank_name,
			"account": gl_account,
			"company": company,
			"is_company_account": 1,
			"bank_account_no": account_number,
		}
	).insert()
	return doc_summary(ba, gl_account=gl_account)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("banking.formats")
def formats():
	from noria_ledger.importers import PARSERS

	return [{"code": code, "label": p.label} for code, p in PARSERS.items()]


@frappe.whitelist(methods=["POST"])
@service_endpoint("banking.import_statement", write=True)
def import_statement(
	bank_account: str,
	format: str,
	content: str,
	encoding: str = "text",
	mapping: dict | str | None = None,
	date_format: str | None = None,
	dry_run: bool = False,
	idempotency_key: str | None = None,
):
	"""Parse a statement and create submitted Bank Transactions, skipping duplicates.

	Duplicates are detected by fingerprint (bank's transaction id when available,
	otherwise date/amount/reference/description) and enforced by a unique column.
	"""
	ba = _bank_account(bank_account)
	if encoding == "base64":
		raw = base64.b64decode(content, validate=True)
	else:
		raw = content.encode()
	if len(raw) > MAX_STATEMENT_BYTES:
		frappe.throw(_("Statement file is larger than 5 MB"))
	text = raw.decode("utf-8-sig", errors="replace")

	try:
		parser = get_parser(format)(mapping=parse_json_arg(mapping, "mapping"), date_format=date_format)
		rows = parser.parse(text)
	except (StatementError, ValueError) as e:
		frappe.throw(str(e), title=_("Statement could not be read"))

	batch = idempotency_key or frappe.generate_hash(length=12)
	currency = frappe.get_cached_value("Company", ba.company, "default_currency")
	created, duplicates = [], []
	seen = set()
	occurrences: dict[str, int] = {}
	for row in rows:
		base = row.fingerprint(ba.name)
		occurrence = occurrences.get(base, 0)
		occurrences[base] = occurrence + 1
		fp = row.fingerprint(ba.name, occurrence)
		if fp in seen or frappe.db.exists("Bank Transaction", {"noria_fingerprint": fp}):
			duplicates.append({"line": row.line, "date": str(row.date), "description": row.description})
			continue
		seen.add(fp)
		if frappe.utils.sbool(dry_run):
			created.append({"line": row.line, "date": str(row.date), "deposit": str(row.deposit), "withdrawal": str(row.withdrawal), "description": row.description})
			continue
		bt = frappe.get_doc(
			{
				"doctype": "Bank Transaction",
				"date": row.date,
				"bank_account": ba.name,
				"company": ba.company,
				"currency": currency,
				"deposit": float(row.deposit),
				"withdrawal": float(row.withdrawal),
				"description": row.description[:1000],
				"reference_number": row.reference[:140] or None,
				"transaction_id": row.transaction_id[:140] or None,
				"bank_party_name": row.party_name[:140] or None,
				"noria_fingerprint": fp,
				"noria_import_batch": batch,
			}
		)
		bt.insert()
		bt.submit()
		created.append({"name": bt.name, "line": row.line, "date": str(row.date)})
	return {
		"doctype": "Bank Account",
		"name": ba.name,
		"batch": batch,
		"dry_run": frappe.utils.sbool(dry_run),
		"parsed": len(rows),
		"created": len(created),
		"duplicates": len(duplicates),
		"duplicate_lines": duplicates[:200],
		"rows": created[:500],
		"imported_at": str(now_datetime()),
	}


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("banking.transactions")
def transactions(bank_account: str | None = None, status: str | None = None, limit: int = 200, start: int = 0):
	filters = {"company": get_company(), "docstatus": 1}
	if bank_account:
		filters["bank_account"] = _bank_account(bank_account).name
	if status in ("Unreconciled", "Reconciled", "Pending", "Settled"):
		filters["status"] = status
	return frappe.get_all(
		"Bank Transaction",
		filters=filters,
		fields=[
			"name",
			"date",
			"bank_account",
			"description",
			"reference_number",
			"transaction_id",
			"deposit",
			"withdrawal",
			"allocated_amount",
			"unallocated_amount",
			"status",
			"bank_party_name",
			"noria_import_batch",
		],
		order_by="date desc, creation desc",
		limit=min(int(limit), 1000),
		start=int(start),
	)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("banking.suggestions")
def suggestions(bank_transaction: str, window_days: int = 60):
	"""ERPNext's matching vouchers for a bank transaction, ranked by its rules.

	ERPNext only searches vouchers posted inside a date range; we use
	transaction date +/- `window_days`.
	"""
	bt = frappe.get_doc("Bank Transaction", bank_transaction)
	if bt.company != get_company():
		raise frappe.DoesNotExistError
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import get_linked_payments

	window = max(1, min(int(window_days), 366))
	matches = get_linked_payments(
		bank_transaction,
		document_types=["payment_entry", "journal_entry", "sales_invoice", "purchase_invoice", "unpaid_invoices"],
		from_date=str(add_days(bt.date, -window)),
		to_date=str(add_days(bt.date, window)),
	)
	return [
		{
			"rank": m.get("rank"),
			"doctype": m.get("doctype"),
			"name": m.get("name"),
			"paid_amount": m.get("paid_amount"),
			"reference_no": m.get("reference_no"),
			"reference_date": str(m.get("reference_date")) if m.get("reference_date") else None,
			"party": m.get("party"),
			"posting_date": str(m.get("posting_date")) if m.get("posting_date") else None,
			"currency": m.get("currency"),
		}
		for m in (matches or [])
	]


@frappe.whitelist(methods=["POST"])
@service_endpoint("banking.reconcile", write=True)
def reconcile(bank_transaction: str, vouchers: list | str):
	"""Allocate vouchers [{payment_doctype, payment_name, amount}] to a bank transaction."""
	bt = frappe.get_doc("Bank Transaction", bank_transaction)
	if bt.company != get_company():
		raise frappe.DoesNotExistError
	vouchers = parse_json_arg(vouchers, "vouchers")
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import reconcile_vouchers

	result = reconcile_vouchers(bank_transaction, json.dumps(vouchers))
	return doc_summary(result, unallocated_amount=result.unallocated_amount, allocated_amount=result.allocated_amount)


@frappe.whitelist(methods=["POST"])
@service_endpoint("banking.categorize", write=True)
def categorize(
	bank_transaction: str,
	account: str,
	party_type: str | None = None,
	party: str | None = None,
	remark: str | None = None,
):
	"""Post a bank/cash journal entry for an unmatched line and reconcile it.

	Uses ERPNext's create_journal_entry_bts (Bank Reconciliation Tool).
	"""
	bt = frappe.get_doc("Bank Transaction", bank_transaction)
	if bt.company != get_company():
		raise frappe.DoesNotExistError
	if bt.status == "Reconciled":
		frappe.throw(_("{0} is already reconciled").format(bank_transaction))
	acc = frappe.db.get_value("Account", {"name": account, "company": bt.company, "is_group": 0}, "name")
	if not acc:
		frappe.throw(_("Invalid account {0}").format(account))
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import create_journal_entry_bts

	result = create_journal_entry_bts(
		bank_transaction_name=bank_transaction,
		reference_number=bt.reference_number or bt.transaction_id or bank_transaction,
		reference_date=getdate(bt.date),
		posting_date=getdate(bt.date),
		entry_type="Bank Entry",
		second_account=account,
		party_type=party_type,
		party=party,
	)
	# `remark` is kept in the Noria Activity Log for this call; posted vouchers are
	# never edited after submission.
	bt.reload()
	return doc_summary(bt, unallocated_amount=bt.unallocated_amount, result=getattr(result, "name", None))
