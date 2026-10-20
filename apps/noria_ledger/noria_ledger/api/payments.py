"""Receipts and payments against invoices via ERPNext Payment Entry."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from noria_ledger.service import (
	doc_summary,
	find_idempotent_result,
	get_company,
	posting_date_filter,
	service_endpoint,
	to_decimal,
)

INVOICE_DOCTYPES = {"sales": "Sales Invoice", "purchase": "Purchase Invoice"}


@frappe.whitelist(methods=["POST"])
@service_endpoint("payments.pay_invoice", write=True)
def pay_invoice(
	kind: str,
	invoice: str,
	account: str,
	posting_date: str | None = None,
	amount: str | float | None = None,
	reference_no: str | None = None,
	reference_date: str | None = None,
	submit: bool = True,
	idempotency_key: str | None = None,
):
	"""Record a customer receipt (sales) or supplier payment (purchase).

	`account` is the company's cash/bank GL account the money moved through.
	Allocation and outstanding updates are done by ERPNext's Payment Entry.
	"""
	if existing := find_idempotent_result(idempotency_key):
		return doc_summary(frappe.get_doc(existing.reference_doctype, existing.reference_name), idempotent_replay=True)
	if kind not in INVOICE_DOCTYPES:
		frappe.throw(_("kind must be 'sales' or 'purchase'"))
	company = get_company()
	inv = frappe.get_doc(INVOICE_DOCTYPES[kind], invoice)
	if inv.company != company or inv.docstatus != 1:
		frappe.throw(_("Payments can only be recorded against posted invoices"))
	if flt(inv.outstanding_amount) <= 0:
		frappe.throw(_("{0} has no outstanding amount").format(invoice))
	acc = frappe.db.get_value("Account", {"name": account, "company": company}, ["account_type", "account_currency"], as_dict=True)
	if not acc or acc.account_type not in ("Cash", "Bank"):
		frappe.throw(_("{0} is not a cash or bank account").format(account))

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	pay_amount = to_decimal(amount) if amount not in (None, "") else to_decimal(inv.outstanding_amount)
	if pay_amount <= 0:
		frappe.throw(_("Amount must be greater than zero"))
	if pay_amount > to_decimal(inv.outstanding_amount):
		frappe.throw(_("Amount exceeds the outstanding balance of {0}").format(inv.outstanding_amount))

	pe = get_payment_entry(INVOICE_DOCTYPES[kind], invoice, party_amount=float(pay_amount))
	pe.posting_date = getdate(posting_date or nowdate())
	if kind == "sales":
		pe.paid_to = account
		pe.paid_to_account_currency = acc.account_currency
	else:
		pe.paid_from = account
		pe.paid_from_account_currency = acc.account_currency
	pe.paid_amount = float(pay_amount)
	pe.received_amount = float(pay_amount)
	for ref in pe.references:
		ref.allocated_amount = float(pay_amount)
	pe.reference_no = reference_no or f"{invoice}-{pe.posting_date}"
	pe.reference_date = getdate(reference_date or pe.posting_date)
	pe.setup_party_account_field()
	pe.set_missing_values()
	pe.set_amounts()
	pe.insert()
	if frappe.utils.sbool(submit):
		pe.submit()
	return doc_summary(pe, paid_amount=pe.paid_amount, invoice=invoice)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("payments.list")
def list_payments(payment_type: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 100, start: int = 0):
	filters = {"company": get_company()}
	if payment_type in ("Receive", "Pay", "Internal Transfer"):
		filters["payment_type"] = payment_type
	if date_filter := posting_date_filter(from_date, to_date):
		filters["posting_date"] = date_filter
	return frappe.get_all(
		"Payment Entry",
		filters=filters,
		fields=[
			"name",
			"payment_type",
			"posting_date",
			"party_type",
			"party",
			"paid_amount",
			"paid_from",
			"paid_to",
			"reference_no",
			"status",
			"docstatus",
			"noria_acting_user",
		],
		order_by="posting_date desc, creation desc",
		limit=min(int(limit), 500),
		start=int(start),
	)


@frappe.whitelist(methods=["POST"])
@service_endpoint("payments.cancel", write=True)
def cancel(name: str):
	doc = frappe.get_doc("Payment Entry", name)
	if doc.company != get_company():
		raise frappe.DoesNotExistError
	doc.cancel()
	return doc_summary(doc)
