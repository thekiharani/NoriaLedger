import frappe
from frappe import _

from noria_practice import audit, authz
from noria_practice.constants import FIRM_ADMIN, PRACTICE_ROLE
from noria_practice.utils import ensure_user

FIRM_ROLES = ("Firm Admin", "Accountant", "Reviewer", "Staff")
EDITABLE_FIRM_FIELDS = ("firm_name", "kra_pin", "registration_number", "email", "phone", "address", "city")


@frappe.whitelist(methods=["GET"])
def get(firm: str):
	role = authz.require_firm_member(firm)
	doc = frappe.get_doc("Accounting Firm", firm)
	enabled = authz.firm_modules(firm)
	modules = frappe.get_all("Noria Module", fields=["name", "title", "description", "is_core"], order_by="sort_order asc")
	for m in modules:
		m["enabled"] = m["name"] in enabled
	engagements = frappe.get_all(
		"Client Engagement", filters={"firm": firm, "status": "Active"}, fields=["monthly_retainer"]
	)
	return {
		"name": doc.name,
		"firm_name": doc.firm_name,
		"firm_type": doc.firm_type,
		"status": doc.status,
		"kra_pin": doc.kra_pin,
		"registration_number": doc.registration_number,
		"email": doc.email,
		"phone": doc.phone,
		"address": doc.address,
		"city": doc.city,
		"max_clients": doc.max_clients,
		"my_role": role,
		"modules": modules,
		"active_clients": len(engagements),
		"monthly_retainers": sum(e.monthly_retainer or 0 for e in engagements),
	}


@frappe.whitelist(methods=["POST"])
def update(firm: str, **fields):
	authz.require_firm_admin(firm)
	doc = frappe.get_doc("Accounting Firm", firm)
	for key in EDITABLE_FIRM_FIELDS:
		if key in fields:
			doc.set(key, fields[key])
	doc.save(ignore_permissions=True)
	audit.record("firm.update", firm=firm, reference=("Accounting Firm", firm))
	return get(firm)


@frappe.whitelist(methods=["GET"])
def members(firm: str):
	authz.require_firm_member(firm)
	rows = frappe.get_all(
		"Firm Member",
		filters={"firm": firm},
		fields=["name", "user", "full_name", "firm_role", "department", "status"],
		order_by="full_name asc",
	)
	counts = dict(
		frappe.db.sql(
			"""select assigned_to, count(*) from `tabPractice Task`
			where firm=%s and status in ('Open','In Progress','In Review') group by assigned_to""",
			firm,
		)
	)
	clients = dict(
		frappe.db.sql(
			"""select user, count(*) from `tabClient Assignment`
			where firm=%s and status='Active' group by user""",
			firm,
		)
	)
	for r in rows:
		r["open_tasks"] = counts.get(r["user"], 0)
		r["assigned_clients"] = clients.get(r["user"], 0)
	return rows


@frappe.whitelist(methods=["POST"])
def add_member(firm: str, email: str, full_name: str, firm_role: str = "Accountant", department: str | None = None, password: str | None = None):
	authz.require_firm_admin(firm)
	if firm_role not in FIRM_ROLES:
		frappe.throw(_("Invalid firm role"))
	if frappe.db.get_value("Accounting Firm", firm, "firm_type") == "Independent Accountant":
		frappe.throw(_("Independent accountant accounts have a single member. Convert to an accounting firm first."))
	user = ensure_user(email, full_name, PRACTICE_ROLE, password=password, send_welcome=not password)
	if frappe.db.exists("Firm Member", {"firm": firm, "user": user}):
		frappe.throw(_("{0} is already a member of this firm").format(user))
	member = frappe.get_doc(
		{"doctype": "Firm Member", "firm": firm, "user": user, "firm_role": firm_role, "department": department, "status": "Active"}
	).insert(ignore_permissions=True)
	audit.record("firm.add_member", firm=firm, reference=("Firm Member", member.name), detail={"user": user, "role": firm_role})
	return {"name": member.name, "user": user}


@frappe.whitelist(methods=["POST"])
def update_member(firm: str, member: str, firm_role: str | None = None, status: str | None = None, department: str | None = None):
	authz.require_firm_admin(firm)
	doc = frappe.get_doc("Firm Member", member)
	if doc.firm != firm:
		frappe.throw(_("Member not found"), frappe.PermissionError)
	if firm_role:
		if firm_role not in FIRM_ROLES:
			frappe.throw(_("Invalid firm role"))
		doc.firm_role = firm_role
	if status:
		if status not in ("Active", "Inactive"):
			frappe.throw(_("Invalid status"))
		doc.status = status
	if department is not None:
		doc.department = department
	if doc.firm_role != FIRM_ADMIN or doc.status != "Active":
		other_admins = frappe.db.count(
			"Firm Member", {"firm": firm, "firm_role": FIRM_ADMIN, "status": "Active", "name": ["!=", doc.name]}
		)
		if not other_admins:
			frappe.throw(_("A firm must keep at least one active Firm Admin"))
	doc.save(ignore_permissions=True)
	if doc.status == "Inactive":
		# Deactivated members lose client assignments in this firm immediately.
		for a in frappe.get_all("Client Assignment", filters={"firm": firm, "user": doc.user, "status": "Active"}, pluck="name"):
			frappe.db.set_value("Client Assignment", a, "status", "Inactive")
	audit.record("firm.update_member", firm=firm, reference=("Firm Member", doc.name), detail={"role": doc.firm_role, "status": doc.status})
	return {"name": doc.name, "firm_role": doc.firm_role, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def set_modules(firm: str, modules: list | str):
	"""Subscription entitlements — platform operators only."""
	authz.require_platform_admin()
	modules = frappe.parse_json(modules) if isinstance(modules, str) else modules
	valid = set(frappe.get_all("Noria Module", pluck="name"))
	doc = frappe.get_doc("Accounting Firm", firm)
	doc.set("modules", [{"module": m, "enabled": 1} for m in modules if m in valid])
	doc.save(ignore_permissions=True)
	audit.record("firm.set_modules", firm=firm, reference=("Accounting Firm", firm), detail={"modules": modules})
	return sorted(authz.firm_modules(firm))
