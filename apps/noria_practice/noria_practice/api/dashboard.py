import frappe
from frappe.utils import add_days, getdate

from noria_practice import authz
from noria_practice.practice.tasks import previous_period


@frappe.whitelist(methods=["GET"])
def practice(firm: str | None = None):
	"""Cross-client overview for the user's accessible clients (cached stats only)."""
	access = authz.accessible_clients()
	if firm:
		authz.require_firm_member(firm)
		access = {k: v for k, v in access.items() if v.firm == firm}
	clients = list(access)
	today = getdate()
	period = previous_period(today)
	empty = {"clients": 0, "active_clients": 0, "period": period}
	if not clients:
		return empty | {"tasks": {}, "attention": [], "monthly_reports": {}, "documents": {}, "billing": {}}

	rows = frappe.get_all("Client Business", filters={"name": ["in", clients]},
	                      fields=["name", "business_name", "status", "provisioning_status", "stat_unreconciled",
	                              "stat_drafts", "stat_overdue_invoices", "last_activity"])
	tasks = frappe.get_all("Practice Task",
	                       filters={"client": ["in", clients], "status": ["in", ["Open", "In Progress", "In Review"]]},
	                       fields=["status", "due_date", "task_type", "assigned_to"])
	overdue = [t for t in tasks if t.due_date and getdate(t.due_date) < today]
	due_week = [t for t in tasks if t.due_date and today <= getdate(t.due_date) <= add_days(today, 7)]
	reports = frappe.get_all("Monthly Report", filters={"client": ["in", clients], "period": period},
	                         fields=["client", "status"])
	reported = {r.client for r in reports if r.status in ("Approved", "Published")}
	requests = frappe.db.count("Document Request", {"client": ["in", clients], "status": ["in", ["Requested", "Rejected"]]})
	uploaded = frappe.db.count("Document Request", {"client": ["in", clients], "status": "Uploaded"})
	firms = {a.firm for a in access.values()}
	retainers = frappe.get_all("Client Engagement", filters={"firm": ["in", list(firms)], "status": "Active",
	                                                         "client": ["in", clients]}, pluck="monthly_retainer")
	active = [r for r in rows if r.status == "Active"]
	attention = sorted(
		[
			{"client": r.name, "business_name": r.business_name, "unreconciled": r.stat_unreconciled or 0,
			 "drafts": r.stat_drafts or 0, "overdue_invoices": r.stat_overdue_invoices or 0,
			 "provisioning_status": r.provisioning_status}
			for r in rows
			if (r.stat_unreconciled or 0) or (r.stat_drafts or 0) or r.provisioning_status in ("Failed", "Queued", "Provisioning")
		],
		key=lambda x: -(x["unreconciled"] + x["drafts"]),
	)[:15]
	return {
		"period": period,
		"clients": len(rows),
		"active_clients": len(active),
		"tasks": {
			"open": len(tasks),
			"overdue": len(overdue),
			"due_this_week": len(due_week),
			"in_review": len([t for t in tasks if t.status == "In Review"]),
			"tax_filings_due": len([t for t in tasks if t.task_type == "Tax Filing"]),
			"mine": len([t for t in tasks if t.assigned_to == frappe.session.user]),
		},
		"reconciliation": {
			"unreconciled_lines": sum(r.stat_unreconciled or 0 for r in rows),
			"clients_with_unreconciled": len([r for r in rows if r.stat_unreconciled]),
		},
		"monthly_reports": {
			"completed": len(reported),
			"pending": len([c for c in active if c.name not in reported]),
			"in_review": len([r for r in reports if r.status == "In Review"]),
		},
		"documents": {"outstanding_requests": requests, "awaiting_review": uploaded},
		"billing": {"monthly_retainers": sum(x or 0 for x in retainers), "engagements": len(retainers)},
		"attention": attention,
	}
