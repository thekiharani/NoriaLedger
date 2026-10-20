"""Sales invoices (+ credit notes) and purchase invoices / bills (+ debit notes).

Service-style lines without stock items: ERPNext accepts invoice rows with an
item name, UOM and income/expense account and no Item master record.
"""

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

KINDS = {
	"sales": {
		"doctype": "Sales Invoice",
		"party_field": "customer",
		"party_type": "Customer",
		"account_field": "income_account",
		"default_account": "default_income_account",
		"root_type": "Income",
		"tax_template": "Sales Taxes and Charges Template",
	},
	"purchase": {
		"doctype": "Purchase Invoice",
		"party_field": "supplier",
		"party_type": "Supplier",
		"account_field": "expense_account",
		"default_account": "default_expense_account",
		"root_type": "Expense",
		"tax_template": "Purchase Taxes and Charges Template",
	},
}
MAX_ITEMS = 300


def _kind(kind: str) -> dict:
	if kind not in KINDS:
		frappe.throw(_("kind must be 'sales' or 'purchase'"))
	return KINDS[kind]


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("invoices.list")
def list_invoices(
	kind: str,
	status: str | None = None,
	party: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int = 100,
	start: int = 0,
):
	cfg = _kind(kind)
	filters = {"company": get_company()}
	if status == "Draft":
		filters["docstatus"] = 0
	elif status == "Unpaid":
		filters.update({"docstatus": 1, "outstanding_amount": [">", 0]})
	elif status:
		filters["status"] = status
	if party:
		filters[cfg["party_field"]] = party
	if date_filter := posting_date_filter(from_date, to_date):
		filters["posting_date"] = date_filter
	fields = [
		"name",
		f"{cfg['party_field']} as party",
		"posting_date",
		"due_date",
		"grand_total",
		"outstanding_amount",
		"currency",
		"status",
		"docstatus",
		"is_return",
		"return_against",
		"noria_acting_user",
	]
	if kind == "purchase":
		fields.append("bill_no")
	return frappe.get_all(
		cfg["doctype"],
		filters=filters,
		fields=fields,
		order_by="posting_date desc, creation desc",
		limit=min(int(limit), 500),
		start=int(start),
	)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("invoices.get")
def get(kind: str, name: str):
	cfg = _kind(kind)
	doc = frappe.get_doc(cfg["doctype"], name)
	if doc.company != get_company():
		raise frappe.DoesNotExistError
	return {
		**doc_summary(doc),
		"party": doc.get(cfg["party_field"]),
		"posting_date": str(doc.posting_date),
		"due_date": str(doc.due_date) if doc.due_date else None,
		"currency": doc.currency,
		"net_total": doc.net_total,
		"total_taxes_and_charges": doc.total_taxes_and_charges,
		"grand_total": doc.grand_total,
		"outstanding_amount": doc.outstanding_amount,
		"is_return": doc.is_return,
		"return_against": doc.return_against,
		"bill_no": doc.get("bill_no"),
		"acting_user": doc.get("noria_acting_user"),
		"items": [
			{
				"item_name": i.item_name,
				"description": i.description,
				"qty": i.qty,
				"rate": i.rate,
				"amount": i.amount,
				"account": i.get(cfg["account_field"]),
			}
			for i in doc.items
		],
		"taxes": [
			{"description": t.description, "account_head": t.account_head, "rate": t.rate, "tax_amount": t.tax_amount}
			for t in doc.taxes
		],
	}


@frappe.whitelist(methods=["POST"])
@service_endpoint("invoices.create", write=True)
def create(
	kind: str,
	party: str,
	posting_date: str,
	items: list | str,
	due_date: str | None = None,
	taxes_and_charges: str | None = None,
	bill_no: str | None = None,
	bill_date: str | None = None,
	remarks: str | None = None,
	submit: bool = False,
	idempotency_key: str | None = None,
):
	if existing := find_idempotent_result(idempotency_key):
		return doc_summary(frappe.get_doc(existing.reference_doctype, existing.reference_name), idempotent_replay=True)

	cfg = _kind(kind)
	company = get_company()
	items = parse_json_arg(items, "items") or []
	if not items:
		frappe.throw(_("At least one line item is required"))
	if len(items) > MAX_ITEMS:
		frappe.throw(_("At most {0} line items are allowed").format(MAX_ITEMS))
	if not frappe.db.exists(cfg["party_type"], party):
		frappe.throw(_("{0} {1} not found").format(cfg["party_type"], party))

	default_account = frappe.get_cached_value("Company", company, cfg["default_account"])
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	doc = frappe.new_doc(cfg["doctype"])
	doc.company = company
	doc.set(cfg["party_field"], party)
	doc.posting_date = getdate(posting_date or nowdate())
	doc.set_posting_time = 1
	if due_date:
		doc.due_date = getdate(due_date)
	doc.remarks = remarks
	if kind == "purchase":
		doc.bill_no = bill_no
		doc.bill_date = getdate(bill_date) if bill_date else None
		doc.update_stock = 0
	else:
		doc.update_stock = 0

	for idx, item in enumerate(items, start=1):
		qty = to_decimal(item.get("qty", 1), f"item {idx} qty")
		rate = to_decimal(item.get("rate"), f"item {idx} rate")
		if qty <= 0:
			frappe.throw(_("Item {0}: quantity must be positive").format(idx))
		if rate < 0:
			frappe.throw(_("Item {0}: rate cannot be negative").format(idx))
		account = item.get("account") or default_account
		acc = frappe.db.get_value("Account", {"name": account, "company": company}, ["root_type", "is_group"], as_dict=True)
		if not acc or acc.is_group:
			frappe.throw(_("Item {0}: invalid account {1}").format(idx, account))
		if kind == "sales" and acc.root_type != "Income":
			frappe.throw(_("Item {0}: {1} is not an income account").format(idx, account))
		if kind == "purchase" and acc.root_type not in ("Expense", "Asset"):
			frappe.throw(_("Item {0}: {1} is not an expense or asset account").format(idx, account))
		name = (item.get("item_name") or item.get("description") or "").strip()
		if not name:
			frappe.throw(_("Item {0}: description is required").format(idx))
		doc.append(
			"items",
			{
				"item_name": name[:140],
				"description": item.get("description") or name,
				"qty": float(qty),
				"uom": "Nos",
				"stock_uom": "Nos",
				"conversion_factor": 1,
				"rate": float(rate),
				cfg["account_field"]: account,
				"cost_center": cost_center,
			},
		)

	if taxes_and_charges:
		if not frappe.db.exists(cfg["tax_template"], {"name": taxes_and_charges, "company": company}):
			frappe.throw(_("Tax template {0} not found").format(taxes_and_charges))
		doc.taxes_and_charges = taxes_and_charges
		doc.append_taxes_from_master()

	doc.insert()
	if frappe.utils.sbool(submit):
		doc.submit()
	return doc_summary(doc, grand_total=doc.grand_total, outstanding_amount=doc.outstanding_amount)


@frappe.whitelist(methods=["POST"])
@service_endpoint("invoices.submit", write=True)
def submit(kind: str, name: str):
	cfg = _kind(kind)
	doc = frappe.get_doc(cfg["doctype"], name)
	if doc.company != get_company():
		raise frappe.DoesNotExistError
	doc.submit()
	return doc_summary(doc, grand_total=doc.grand_total, outstanding_amount=doc.outstanding_amount)


@frappe.whitelist(methods=["POST"])
@service_endpoint("invoices.cancel", write=True)
def cancel(kind: str, name: str):
	cfg = _kind(kind)
	doc = frappe.get_doc(cfg["doctype"], name)
	if doc.company != get_company():
		raise frappe.DoesNotExistError
	doc.cancel()
	return doc_summary(doc)


@frappe.whitelist(methods=["POST"])
@service_endpoint("invoices.make_return", write=True)
def make_return(kind: str, name: str, posting_date: str | None = None, reason: str | None = None,
                apply_to_invoice: bool = True, idempotency_key: str | None = None):
	"""Full credit note (sales) or debit note (purchase) against a posted invoice.

	apply_to_invoice=True offsets the original invoice's outstanding amount
	(ERPNext `update_outstanding_for_self = 0`). False keeps a standalone
	credit balance to be allocated later via payment reconciliation.
	"""
	if existing := find_idempotent_result(idempotency_key):
		return doc_summary(frappe.get_doc(existing.reference_doctype, existing.reference_name), idempotent_replay=True)
	cfg = _kind(kind)
	source = frappe.get_doc(cfg["doctype"], name)
	if source.company != get_company() or source.docstatus != 1:
		frappe.throw(_("Returns can only be made against posted invoices"))
	if kind == "sales":
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return as make
	else:
		from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import make_debit_note as make
	ret = make(name)
	ret.update_outstanding_for_self = 0 if frappe.utils.sbool(apply_to_invoice) else 1
	ret.posting_date = getdate(posting_date or nowdate())
	ret.set_posting_time = 1
	ret.remarks = reason
	ret.insert()
	ret.submit()
	return doc_summary(ret, return_against=name, grand_total=ret.grand_total)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("invoices.tax_templates")
def tax_templates(kind: str):
	cfg = _kind(kind)
	templates = frappe.get_all(
		cfg["tax_template"],
		filters={"company": get_company(), "disabled": 0},
		fields=["name", "title", "is_default"],
	)
	for t in templates:
		t["taxes"] = frappe.get_all(
			"Sales Taxes and Charges" if kind == "sales" else "Purchase Taxes and Charges",
			filters={"parent": t["name"], "parenttype": cfg["tax_template"]},
			fields=["account_head", "rate", "description", "charge_type"],
		)
	return templates
