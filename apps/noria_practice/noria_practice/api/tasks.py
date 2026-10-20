import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime

from noria_practice import audit, authz
from noria_practice.constants import FIRM_ADMIN, LEAD, READ, REVIEW, WRITE
from noria_practice.practice.tasks import generate_for_firm
from noria_practice.utils import period_bounds, user_names

STATUSES = ("Open", "In Progress", "In Review", "Done", "Cancelled")
PRIORITIES = ("Low", "Medium", "High", "Urgent")
TASK_TYPES = ("Bookkeeping", "Bank Reconciliation", "Tax Filing", "Payroll", "Monthly Report", "Year End", "Other")
FIELDS = ["name", "title", "client", "firm", "task_type", "period", "status", "priority", "due_date",
          "assigned_to", "reviewer", "template", "completed_on", "description", "estimated_hours"]


@frappe.whitelist(methods=["GET"])
def list_tasks(client: str | None = None, status: str | None = None, assigned_to: str | None = None,
               due_within_days: int | None = None, include_done: bool = False, limit: int = 500):
	if client:
		authz.require_client_access(client, READ)
		clients = [client]
	else:
		clients = list(authz.accessible_clients())
	if not clients:
		return []
	filters = {"client": ["in", clients]}
	if status:
		filters["status"] = status
	elif not frappe.utils.sbool(include_done):
		filters["status"] = ["in", ["Open", "In Progress", "In Review"]]
	if assigned_to:
		filters["assigned_to"] = frappe.session.user if assigned_to == "me" else assigned_to
	if due_within_days not in (None, ""):
		filters["due_date"] = ["<=", add_days(getdate(), int(due_within_days))]
	rows = frappe.get_all("Practice Task", filters=filters, fields=FIELDS, order_by="due_date asc, priority desc", limit=min(int(limit), 2000))
	names = user_names([r.assigned_to for r in rows] + [r.reviewer for r in rows])
	clients_map = dict(frappe.get_all("Client Business", filters={"name": ["in", list({r.client for r in rows}) or [""]]},
	                                  fields=["name", "business_name"], as_list=True))
	today = getdate()
	for r in rows:
		r["client_name"] = clients_map.get(r.client)
		r["assigned_to_name"] = names.get(r.assigned_to)
		r["reviewer_name"] = names.get(r.reviewer)
		r["overdue"] = bool(r.due_date and getdate(r.due_date) < today and r.status not in ("Done", "Cancelled"))
	return rows


def _validate_people(firm, *users):
	for u in users:
		if u and not frappe.db.exists("Firm Member", {"firm": firm, "user": u, "status": "Active"}):
			frappe.throw(_("{0} is not an active member of the firm").format(u))


@frappe.whitelist(methods=["POST"])
def create(client: str, title: str, task_type: str = "Other", due_date: str | None = None, assigned_to: str | None = None,
           reviewer: str | None = None, priority: str = "Medium", period: str | None = None, description: str | None = None):
	access = authz.require_client_access(client, WRITE)
	authz.require_module(access, "practice_management")
	if task_type not in TASK_TYPES or priority not in PRIORITIES:
		frappe.throw(_("Invalid task type or priority"))
	if period:
		period_bounds(period)
	_validate_people(access.firm, assigned_to, reviewer)
	doc = frappe.get_doc({
		"doctype": "Practice Task", "title": title, "client": client, "firm": access.firm, "task_type": task_type,
		"due_date": getdate(due_date) if due_date else None, "assigned_to": assigned_to, "reviewer": reviewer,
		"priority": priority, "period": period, "description": description, "status": "Open",
	}).insert(ignore_permissions=True)
	audit.record("task.create", client=client, firm=access.firm, reference=("Practice Task", doc.name))
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def update(task: str, status: str | None = None, assigned_to: str | None = None, reviewer: str | None = None,
           priority: str | None = None, due_date: str | None = None, internal_notes: str | None = None):
	doc = frappe.get_doc("Practice Task", task)
	access = authz.require_client_access(doc.client, REVIEW)
	if access.firm != doc.firm:
		frappe.throw(_("Task not found"), frappe.PermissionError)
	user = frappe.session.user
	is_assignee = doc.assigned_to == user
	if access.level < WRITE and not (status and doc.reviewer == user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if status:
		if status not in STATUSES:
			frappe.throw(_("Invalid status"))
		if status == "Done" and doc.reviewer and doc.status != "In Review":
			frappe.throw(_("This task needs review: move it to In Review first"))
		if status == "Done" and doc.reviewer and user != doc.reviewer and access.level < LEAD:
			frappe.throw(_("Only the reviewer can complete a reviewed task"))
		if status == "In Review" and not (is_assignee or access.level >= LEAD):
			frappe.throw(_("Only the assignee can submit the task for review"))
		doc.status = status
		doc.completed_on = now_datetime() if status == "Done" else None
	if assigned_to is not None or reviewer is not None:
		if access.level < LEAD:
			frappe.throw(_("Only lead accountants and firm admins reassign tasks"), frappe.PermissionError)
		_validate_people(access.firm, assigned_to, reviewer)
		if assigned_to is not None:
			doc.assigned_to = assigned_to or None
		if reviewer is not None:
			doc.reviewer = reviewer or None
	if priority:
		if priority not in PRIORITIES:
			frappe.throw(_("Invalid priority"))
		doc.priority = priority
	if due_date:
		doc.due_date = getdate(due_date)
	if internal_notes is not None:
		doc.internal_notes = internal_notes
	doc.save(ignore_permissions=True)
	audit.record("task.update", client=doc.client, firm=doc.firm, reference=("Practice Task", doc.name), detail={"status": doc.status})
	return {f: doc.get(f) for f in FIELDS}


@frappe.whitelist(methods=["POST"])
def generate(firm: str, period: str):
	authz.require_firm_member(firm, (FIRM_ADMIN,))
	authz.require_firm_module(firm, "practice_management")
	period_bounds(period)
	created = generate_for_firm(firm, period)
	audit.record("task.generate", firm=firm, detail={"period": period, "created": len(created)})
	return {"created": len(created), "tasks": created}


@frappe.whitelist(methods=["GET"])
def workload(firm: str):
	authz.require_firm_member(firm, (FIRM_ADMIN, "Reviewer"))
	rows = frappe.db.sql(
		"""select assigned_to, status, count(*) as n,
		sum(case when due_date < curdate() then 1 else 0 end) as overdue,
		coalesce(sum(estimated_hours), 0) as hours
		from `tabPractice Task` where firm=%s and status in ('Open','In Progress','In Review')
		group by assigned_to, status""",
		firm,
		as_dict=True,
	)
	names = user_names([r.assigned_to for r in rows])
	out = {}
	for r in rows:
		key = r.assigned_to or "unassigned"
		entry = out.setdefault(key, {"user": r.assigned_to, "full_name": names.get(r.assigned_to) or "Unassigned",
		                             "Open": 0, "In Progress": 0, "In Review": 0, "overdue": 0, "hours": 0})
		entry[r.status] = r.n
		entry["overdue"] += int(r.overdue or 0)
		entry["hours"] += float(r.hours or 0)
	return sorted(out.values(), key=lambda e: -(e["Open"] + e["In Progress"] + e["In Review"]))
