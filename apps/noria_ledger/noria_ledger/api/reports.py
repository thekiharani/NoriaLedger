"""Financial reports — executed by ERPNext's own report engine (authoritative data).

Only allow-listed reports run, always scoped to this site's company. Filters are
constructed server-side from a small set of inputs so callers cannot inject
arbitrary report filters.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from noria_ledger.constants import ALLOWED_REPORTS
from noria_ledger.service import get_company, service_endpoint

PERIODICITIES = ("Monthly", "Quarterly", "Half-Yearly", "Yearly")


def _fiscal_year(date, company):
	from erpnext.accounts.utils import get_fiscal_year

	return get_fiscal_year(date, company=company, as_dict=True)


def build_filters(report: str, from_date: str, to_date: str, options: dict) -> dict:
	company = get_company()
	start, end = getdate(from_date), getdate(to_date)
	if start > end:
		frappe.throw(_("From date cannot be after to date"))
	fy_start = _fiscal_year(start, company)
	fy_end = _fiscal_year(end, company)

	if report == "Trial Balance":
		if fy_start.name != fy_end.name:
			frappe.throw(_("Trial balance dates must fall within one fiscal year"))
		return {
			"company": company,
			"fiscal_year": fy_start.name,
			"from_date": str(start),
			"to_date": str(end),
			"show_zero_values": 0,
			"include_default_book_entries": 1,
			"show_net_values": 1 if options.get("show_net_values") else 0,
		}
	if report in ("Profit and Loss Statement", "Balance Sheet", "Cash Flow"):
		periodicity = options.get("periodicity") or "Monthly"
		if periodicity not in PERIODICITIES:
			frappe.throw(_("Invalid periodicity"))
		return {
			"company": company,
			"filter_based_on": "Date Range",
			"period_start_date": str(start),
			"period_end_date": str(end),
			"from_fiscal_year": fy_start.name,
			"to_fiscal_year": fy_end.name,
			"periodicity": periodicity,
			"accumulated_values": 1 if report == "Balance Sheet" else 0,
			"include_default_book_entries": 1,
			"presentation_currency": frappe.get_cached_value("Company", company, "default_currency"),
		}
	if report == "General Ledger":
		filters = {
			"company": company,
			"from_date": str(start),
			"to_date": str(end),
			"group_by": "Group by Voucher (Consolidated)",
			"include_dimensions": 0,
			"include_default_book_entries": 1,
		}
		if options.get("account"):
			filters["account"] = [a for a in options["account"]] if isinstance(options["account"], list) else [options["account"]]
		if options.get("party_type") and options.get("party"):
			filters["party_type"] = options["party_type"]
			filters["party"] = [options["party"]]
		return filters
	if report in ("Accounts Receivable", "Accounts Payable"):
		return {
			"company": company,
			"report_date": str(end),
			"ageing_based_on": "Due Date",
			"calculate_ageing_with": "Report Date",
			"range": "30, 60, 90, 120",
		}
	if report == "Bank Reconciliation Statement":
		account = options.get("account")
		if not account or not frappe.db.exists("Account", {"name": account, "company": company, "account_type": ["in", ["Bank", "Cash"]]}):
			frappe.throw(_("A bank or cash account is required"))
		return {"company": company, "account": account, "report_date": str(end)}
	frappe.throw(_("Report {0} is not available").format(report))


def run_report(report: str, from_date: str, to_date: str, options: dict | None = None) -> dict:
	if report not in ALLOWED_REPORTS:
		frappe.throw(_("Report {0} is not available").format(report), frappe.PermissionError)
	filters = build_filters(report, from_date, to_date, options or {})
	from frappe.desk.query_report import run

	data = run(report, filters=filters, ignore_prepared_report=True)
	columns = []
	for c in data.get("columns") or []:
		if isinstance(c, str):  # legacy "Label:Fieldtype/Options:Width"
			label, _sep, rest = c.partition(":")
			columns.append({"fieldname": frappe.scrub(label), "label": label, "fieldtype": rest.split("/")[0] or "Data"})
		else:
			columns.append(
				{
					"fieldname": c.get("fieldname"),
					"label": c.get("label"),
					"fieldtype": c.get("fieldtype") or "Data",
					"options": c.get("options") if c.get("fieldtype") == "Link" else None,
				}
			)
	rows = []
	for r in data.get("result") or []:
		if isinstance(r, dict):
			rows.append({k: v for k, v in r.items() if not k.startswith("_")})
		elif isinstance(r, list | tuple):
			rows.append({columns[i]["fieldname"]: v for i, v in enumerate(r) if i < len(columns)})
	return {
		"report": report,
		"company": filters["company"],
		"filters": filters,
		"columns": columns,
		"rows": rows,
		"report_summary": data.get("report_summary"),
	}


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("reports.run")
def run(report: str, from_date: str, to_date: str, options: dict | str | None = None):
	if isinstance(options, str):
		options = frappe.parse_json(options)
	return run_report(report, from_date, to_date, options or {})


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("reports.monthly_pack")
def monthly_pack(from_date: str, to_date: str):
	"""Trial balance + P&L + balance sheet for a period, plus headline totals.

	Used by the hub to snapshot a Monthly Report. Totals come from the P&L rows
	ERPNext produces (Total Income / Total Expense / Profit for the period).
	"""
	tb = run_report("Trial Balance", from_date, to_date)
	pl = run_report("Profit and Loss Statement", from_date, to_date, {"periodicity": "Yearly"})
	bs = run_report("Balance Sheet", from_date, to_date, {"periodicity": "Yearly"})
	return {
		"trial_balance": tb,
		"profit_and_loss": pl,
		"balance_sheet": bs,
		"totals": _pl_totals(pl),
		"trial_balance_check": _tb_check(tb),
		"currency": frappe.get_cached_value("Company", tb["company"], "default_currency"),
	}


def _pl_total_value(row: dict) -> float:
	return float(row.get("total") or 0)


def _pl_totals(pl: dict) -> dict:
	income = expense = profit = 0.0
	for row in pl["rows"]:
		label = (row.get("account_name") or row.get("account") or "").strip("'\" ")
		if label in ("Total Income (Credit)", "Total Income"):
			income = _pl_total_value(row)
		elif label in ("Total Expense (Debit)", "Total Expense"):
			expense = _pl_total_value(row)
		elif label.startswith("Profit for the") or label in ("Net Profit", "Profit/Loss"):
			profit = _pl_total_value(row)
	return {"total_income": income, "total_expense": expense, "net_profit": profit}


def _tb_check(tb: dict) -> dict:
	"""Independent sanity check: closing debits must equal closing credits."""
	debit = credit = 0.0
	for row in tb["rows"]:
		if row.get("indent") == 0 and row.get("account") and not str(row.get("account")).startswith("'"):
			debit += float(row.get("closing_debit") or 0)
			credit += float(row.get("closing_credit") or 0)
	return {"closing_debit": round(debit, 2), "closing_credit": round(credit, 2), "balanced": abs(debit - credit) < 0.005}
