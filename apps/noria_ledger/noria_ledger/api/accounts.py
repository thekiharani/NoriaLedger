import frappe
from frappe import _
from frappe.utils import flt

from noria_ledger.service import doc_summary, get_company, service_endpoint

ACCOUNT_TYPES = (
	"",
	"Bank",
	"Cash",
	"Receivable",
	"Payable",
	"Income Account",
	"Expense Account",
	"Tax",
	"Fixed Asset",
	"Equity",
	"Cost of Goods Sold",
	"Depreciation",
	"Accumulated Depreciation",
	"Chargeable",
	"Round Off",
	"Temporary",
)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("accounts.chart")
def chart():
	"""Flat chart of accounts with closing balances (tree built by the client)."""
	company = get_company()
	accounts = frappe.get_all(
		"Account",
		filters={"company": company},
		fields=[
			"name",
			"account_name",
			"account_number",
			"parent_account",
			"root_type",
			"report_type",
			"account_type",
			"is_group",
			"disabled",
			"lft",
		],
		order_by="lft asc",
	)
	balances = dict(
		frappe.db.sql(
			"""select account, sum(debit) - sum(credit) from `tabGL Entry`
			where company=%s and is_cancelled=0 group by account""",
			company,
		)
	)
	for a in accounts:
		a["balance"] = flt(balances.get(a["name"]))
		del a["lft"]
	_roll_up_group_balances(accounts)
	return {"company": company, "accounts": accounts}


def _roll_up_group_balances(accounts):
	by_name = {a["name"]: a for a in accounts}
	for a in reversed(accounts):  # children come after parents in lft order
		parent = by_name.get(a["parent_account"])
		if parent:
			parent["balance"] = flt(parent["balance"]) + flt(a["balance"])


@frappe.whitelist(methods=["POST"])
@service_endpoint("accounts.create", write=True)
def create(
	parent_account: str,
	account_name: str,
	account_number: str | None = None,
	account_type: str | None = None,
	is_group: bool = False,
	idempotency_key: str | None = None,
):
	company = get_company()
	if not frappe.db.get_value("Account", {"name": parent_account, "company": company, "is_group": 1}):
		frappe.throw(_("Parent account {0} is not a group account of {1}").format(parent_account, company))
	if account_type and account_type not in ACCOUNT_TYPES:
		frappe.throw(_("Unsupported account type {0}").format(account_type))
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"company": company,
			"parent_account": parent_account,
			"account_name": account_name.strip(),
			"account_number": (account_number or "").strip() or None,
			"account_type": account_type or "",
			"is_group": 1 if is_group else 0,
		}
	).insert()
	return doc_summary(doc, account_name=doc.account_name)


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("accounts.postable")
def postable(root_type: str | None = None, account_type: str | None = None):
	"""Non-group, enabled accounts — for line-item pickers."""
	filters = {"company": get_company(), "is_group": 0, "disabled": 0}
	if root_type:
		filters["root_type"] = root_type
	if account_type:
		filters["account_type"] = ["in", account_type.split(",")]
	return frappe.get_all(
		"Account",
		filters=filters,
		fields=["name", "account_name", "account_number", "root_type", "account_type"],
		order_by="lft asc",
	)
