import frappe
from frappe.utils import add_days, flt, get_first_day, getdate, nowdate

from noria_ledger.service import get_company, service_endpoint


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("company.overview")
def overview():
	"""Headline figures for the client workspace, read from ERPNext's ledger."""
	company = get_company()
	currency = frappe.get_cached_value("Company", company, "default_currency")
	today = getdate(nowdate())
	month_start = get_first_day(today)

	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")

	def balance(account_types: tuple[str, ...]) -> float:
		q = (
			frappe.qb.from_(gle)
			.join(acc)
			.on(gle.account == acc.name)
			.select((frappe.query_builder.functions.Sum(gle.debit) - frappe.query_builder.functions.Sum(gle.credit)))
			.where((gle.company == company) & (gle.is_cancelled == 0) & (acc.account_type.isin(account_types)))
		)
		return flt(q.run()[0][0])

	def period_total(root_type: str) -> float:
		Sum = frappe.query_builder.functions.Sum
		q = (
			frappe.qb.from_(gle)
			.join(acc)
			.on(gle.account == acc.name)
			.select(Sum(gle.credit) - Sum(gle.debit))
			.where(
				(gle.company == company)
				& (gle.is_cancelled == 0)
				& (acc.root_type == root_type)
				& (gle.posting_date >= month_start)
				& (gle.posting_date <= today)
			)
		)
		value = flt(q.run()[0][0])
		return (value if root_type == "Income" else -value) or 0.0

	last_posting = (
		frappe.qb.from_(gle)
		.select(frappe.query_builder.functions.Max(gle.posting_date))
		.where((gle.company == company) & (gle.is_cancelled == 0))
		.run()[0][0]
	)
	return {
		"company": company,
		"currency": currency,
		"fiscal_year": _current_fiscal_year(company),
		"cash_and_bank": balance(("Cash", "Bank")),
		"receivables": balance(("Receivable",)),
		"payables": -balance(("Payable",)) or 0.0,
		"income_mtd": period_total("Income"),
		"expense_mtd": period_total("Expense"),
		"unreconciled_bank_transactions": frappe.db.count(
			"Bank Transaction", {"company": company, "docstatus": 1, "status": "Unreconciled"}
		),
		"draft_documents": sum(
			frappe.db.count(dt, {"company": company, "docstatus": 0})
			for dt in ("Journal Entry", "Sales Invoice", "Purchase Invoice", "Payment Entry")
		),
		"overdue_sales_invoices": frappe.db.count(
			"Sales Invoice",
			{"company": company, "docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", today]},
		),
		"last_posting_date": str(last_posting) if last_posting else None,
		"as_of": str(today),
		"month_start": str(month_start),
		"previous_month_end": str(add_days(month_start, -1)),
	}


def _current_fiscal_year(company: str):
	from erpnext.accounts.utils import get_fiscal_year

	try:
		fy = get_fiscal_year(nowdate(), company=company, as_dict=True)
		return {"name": fy.name, "from_date": str(fy.year_start_date), "to_date": str(fy.year_end_date)}
	except Exception:
		return None
