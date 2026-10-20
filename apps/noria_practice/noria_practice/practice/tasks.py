"""Recurring practice work generated from Task Templates."""

from datetime import date

import frappe
from frappe.utils import add_days, add_months, get_last_day, getdate

from noria_practice import authz
from noria_practice.utils import period_bounds

QUARTER_END_MONTHS = (3, 6, 9, 12)


def previous_period(today: date | None = None) -> str:
	today = getdate(today)
	prev = add_months(today.replace(day=1), -1)
	return f"{prev.year:04d}-{prev.month:02d}"


def generate_recurring_tasks_for_current_period():
	"""Daily scheduler job: idempotently create the work for the month that just ended."""
	period = previous_period()
	for firm in frappe.get_all("Accounting Firm", filters={"status": "Active"}, pluck="name"):
		generate_for_firm(firm, period)
		frappe.db.commit()


def generate_for_firm(firm: str, period: str) -> list[str]:
	start, end = period_bounds(period)
	templates = frappe.get_all("Task Template", filters={"enabled": 1}, fields=["*"])
	created = []
	engagements = frappe.get_all("Client Engagement", filters={"firm": firm, "status": "Active"}, pluck="client")
	for client in engagements:
		if frappe.db.get_value("Client Business", client, "status") not in ("Active", "Onboarding"):
			continue
		modules = authz.client_modules(client, firm)
		team = frappe.get_all(
			"Client Assignment",
			filters={"client": client, "firm": firm, "status": "Active"},
			fields=["user", "assignment_role"],
			order_by="creation asc",
		)
		by_role = {}
		for a in team:
			by_role.setdefault(a.assignment_role, a.user)
		lead = by_role.get("Lead Accountant") or by_role.get("Accountant")
		reviewer = by_role.get("Reviewer")
		fy_start = frappe.db.get_value("Client Business", client, "fiscal_year_start")
		for tpl in templates:
			if tpl.required_module and tpl.required_module not in modules:
				continue
			if not _applies(tpl.frequency, end, fy_start):
				continue
			if frappe.db.exists("Practice Task", {"client": client, "template": tpl.name, "period": period}):
				continue
			task = frappe.get_doc(
				{
					"doctype": "Practice Task",
					"title": f"{tpl.template_name} — {period}",
					"client": client,
					"firm": firm,
					"task_type": tpl.task_type,
					"period": period,
					"template": tpl.name,
					"status": "Open",
					"priority": tpl.default_priority or "Medium",
					"due_date": add_days(end, tpl.due_days_after_period_end or 0),
					"assigned_to": lead,
					"reviewer": reviewer,
					"description": "\n\n".join(filter(None, [tpl.description, tpl.statutory_note])),
				}
			).insert(ignore_permissions=True)
			created.append(task.name)
	return created


def _applies(frequency: str, period_end: date, fy_start) -> bool:
	if frequency == "Monthly":
		return True
	if frequency == "Quarterly":
		return period_end.month in QUARTER_END_MONTHS
	if frequency == "Annual":
		if not fy_start:
			return period_end.month == 12
		fy_start = getdate(fy_start)
		fy_end_month = get_last_day(add_months(fy_start, 11)).month
		return period_end.month == fy_end_month
	return False
