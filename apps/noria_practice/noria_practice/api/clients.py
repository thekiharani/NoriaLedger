import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from noria_practice import audit, authz
from noria_practice.constants import CLIENT_ROLE, FIRM_ADMIN, LEAD, READ, WRITE
from noria_practice.provisioning import enqueue_offboarding_backup, enqueue_provisioning
from noria_practice.utils import ensure_user, user_names

ASSIGNMENT_ROLES = ("Lead Accountant", "Accountant", "Reviewer", "Read Only")
EDITABLE_FIELDS = (
	"business_name",
	"legal_name",
	"business_type",
	"industry",
	"kra_pin",
	"registration_number",
	"vat_registered",
	"email",
	"phone",
	"address",
	"status",
)
DEFAULT_CHECKLIST = (
	"Signed engagement letter received",
	"KRA PIN certificate on file",
	"Opening balances confirmed",
	"Bank and M-PESA accounts set up",
	"Client portal user invited",
)
LIST_FIELDS = [
	"name",
	"business_name",
	"kra_pin",
	"business_type",
	"industry",
	"status",
	"provisioning_status",
	"currency",
	"last_activity",
	"stat_unreconciled",
	"stat_drafts",
	"stat_overdue_invoices",
	"stat_last_posting_date",
	"stat_cash_and_bank",
	"stat_updated_on",
]


@frappe.whitelist(methods=["GET"])
def list_clients(search: str | None = None, status: str | None = None, firm: str | None = None, assigned_to: str | None = None):
	access = authz.accessible_clients()
	if firm:
		access = {k: v for k, v in access.items() if v.firm == firm}
	if not access:
		return []
	filters = {"name": ["in", list(access)]}
	if status:
		filters["status"] = status
	or_filters = None
	if search:
		or_filters = {"business_name": ["like", f"%{search}%"], "kra_pin": ["like", f"%{search}%"], "name": ["like", f"%{search}%"]}
	rows = frappe.get_all("Client Business", filters=filters, or_filters=or_filters, fields=LIST_FIELDS, order_by="business_name asc")

	assignments = frappe.get_all(
		"Client Assignment",
		filters={"client": ["in", [r.name for r in rows] or [""]], "status": "Active"},
		fields=["client", "user", "assignment_role", "firm"],
	)
	names = user_names([a.user for a in assignments])
	open_tasks = dict(
		frappe.db.sql(
			"""select client, count(*) from `tabPractice Task`
			where client in %(clients)s and status in ('Open','In Progress','In Review') group by client""",
			{"clients": [r.name for r in rows] or [""]},
		)
	)
	result = []
	for r in rows:
		a = access[r.name]
		team = [
			{"user": x.user, "full_name": names.get(x.user), "role": x.assignment_role}
			for x in assignments
			if x.client == r.name and x.firm == a.firm
		]
		if assigned_to and assigned_to not in {t["user"] for t in team}:
			continue
		result.append(
			{
				**r,
				"firm": a.firm,
				"access_role": a.role,
				"access_level": a.level,
				"team": team,
				"open_tasks": open_tasks.get(r.name, 0),
				"modules": sorted(authz.client_modules(r.name, a.firm)),
			}
		)
	return result


@frappe.whitelist(methods=["POST"])
def create(
	firm: str,
	business_name: str,
	fiscal_year_start: str,
	kra_pin: str | None = None,
	legal_name: str | None = None,
	business_type: str = "Limited Company",
	industry: str | None = None,
	registration_number: str | None = None,
	vat_registered: bool = False,
	email: str | None = None,
	phone: str | None = None,
	chart_of_accounts: str = "Standard with Numbers",
	services: list | str | None = None,
	monthly_retainer: float | None = None,
	provision: bool = True,
):
	role = authz.require_firm_member(firm, (FIRM_ADMIN, "Accountant"))
	firm_doc = frappe.get_doc("Accounting Firm", firm)
	if firm_doc.max_clients:
		active = frappe.db.count("Client Engagement", {"firm": firm, "status": "Active"})
		if active >= firm_doc.max_clients:
			frappe.throw(_("Your subscription allows {0} active clients").format(firm_doc.max_clients))
	if kra_pin:
		kra_pin = kra_pin.strip().upper()
		# Same KRA PIN already engaged by this firm -> probably a duplicate entry.
		for existing in frappe.get_all("Client Business", filters={"kra_pin": kra_pin}, pluck="name"):
			if frappe.db.exists("Client Engagement", {"client": existing, "firm": firm, "status": "Active"}):
				frappe.throw(_("A client with KRA PIN {0} already exists in your firm ({1})").format(kra_pin, existing))
	services = frappe.parse_json(services) if isinstance(services, str) else (services or [])
	firm_modules = authz.firm_modules(firm)
	invalid = [s for s in services if s not in firm_modules]
	if invalid:
		frappe.throw(_("Modules not in your subscription: {0}").format(", ".join(invalid)))

	client = frappe.get_doc(
		{
			"doctype": "Client Business",
			"business_name": business_name.strip(),
			"legal_name": legal_name,
			"business_type": business_type,
			"industry": industry,
			"kra_pin": kra_pin,
			"registration_number": registration_number,
			"vat_registered": 1 if frappe.utils.sbool(vat_registered) else 0,
			"email": email,
			"phone": phone,
			"fiscal_year_start": getdate(fiscal_year_start),
			"chart_of_accounts": chart_of_accounts,
			"created_by_firm": firm,
			"status": "Onboarding",
			"onboarding_checklist": [{"item": i} for i in DEFAULT_CHECKLIST],
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Client Engagement",
			"client": client.name,
			"firm": firm,
			"status": "Active",
			"start_date": getdate(),
			"monthly_retainer": monthly_retainer or 0,
			"services": [{"module": s} for s in services],
		}
	).insert(ignore_permissions=True)
	if role != FIRM_ADMIN:
		frappe.get_doc(
			{
				"doctype": "Client Assignment",
				"client": client.name,
				"firm": firm,
				"user": frappe.session.user,
				"assignment_role": "Lead Accountant",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
	audit.record("client.create", client=client.name, firm=firm, reference=("Client Business", client.name))
	if frappe.utils.sbool(provision):
		enqueue_provisioning(client.name)
	return {"name": client.name, "provisioning_status": frappe.db.get_value("Client Business", client.name, "provisioning_status")}


@frappe.whitelist(methods=["GET"])
def get(client: str):
	access = authz.require_client_access(client, READ)
	doc = frappe.get_doc("Client Business", client)
	audit.record("client.view", client=client, firm=access.firm)
	assignments = frappe.get_all(
		"Client Assignment",
		filters={"client": client, "firm": access.firm},
		fields=["name", "user", "assignment_role", "status"],
	)
	portal_users = frappe.get_all(
		"Client Portal User", filters={"client": client}, fields=["name", "user", "contact_role", "can_approve", "status"]
	)
	names = user_names([a.user for a in assignments] + [p.user for p in portal_users])
	for row in assignments + portal_users:
		row["full_name"] = names.get(row["user"])
	engagement = frappe.get_doc("Client Engagement", {"client": client, "firm": access.firm, "status": "Active"})
	data = {f: doc.get(f) for f in ("name", *EDITABLE_FIELDS, *LIST_FIELDS[5:], "fiscal_year_start", "chart_of_accounts",
	                                "country", "company_name", "provisioning_error", "stat_receivables", "stat_payables")}
	data.update(
		{
			"firm": access.firm,
			"access_role": access.role,
			"access_level": access.level,
			"modules": sorted(authz.client_modules(client, access.firm)),
			"engagement": {
				"name": engagement.name,
				"start_date": engagement.start_date,
				"monthly_retainer": engagement.monthly_retainer,
				"services": [s.module for s in engagement.services],
			},
			"team": assignments,
			"portal_users": portal_users,
			"onboarding_checklist": [
				{"idx": i.idx, "item": i.item, "done": i.done, "done_by": i.done_by, "done_on": i.done_on}
				for i in doc.onboarding_checklist
			],
			"other_firms": frappe.db.count("Client Engagement", {"client": client, "status": "Active", "firm": ["!=", access.firm]}),
		}
	)
	return data


@frappe.whitelist(methods=["POST"])
def update(client: str, **fields):
	access = authz.require_client_access(client, LEAD)
	doc = frappe.get_doc("Client Business", client)
	for key in EDITABLE_FIELDS:
		if key in fields:
			if key == "status" and fields[key] not in ("Onboarding", "Active", "Suspended"):
				frappe.throw(_("Use the archive action to archive a client"))
			doc.set(key, fields[key])
	doc.save(ignore_permissions=True)
	audit.record("client.update", client=client, firm=access.firm, detail={k: fields[k] for k in EDITABLE_FIELDS if k in fields})
	return get(client)


@frappe.whitelist(methods=["POST"])
def provision(client: str):
	access = authz.require_client_access(client, LEAD)
	status = enqueue_provisioning(client)
	audit.record("client.provision", client=client, firm=access.firm)
	return {"provisioning_status": status}


@frappe.whitelist(methods=["POST"])
def toggle_checklist(client: str, idx: int, done: bool):
	access = authz.require_client_access(client, WRITE)
	doc = frappe.get_doc("Client Business", client)
	row = next((r for r in doc.onboarding_checklist if r.idx == int(idx)), None)
	if not row:
		frappe.throw(_("Checklist item not found"))
	row.done = 1 if frappe.utils.sbool(done) else 0
	row.done_by = frappe.session.user if row.done else None
	row.done_on = now_datetime() if row.done else None
	doc.save(ignore_permissions=True)
	audit.record("client.checklist", client=client, firm=access.firm, detail={"item": row.item, "done": row.done})
	return {"idx": row.idx, "done": row.done}


@frappe.whitelist(methods=["POST"])
def assign(client: str, user: str, assignment_role: str = "Accountant"):
	access = authz.require_client_access(client, LEAD)
	if assignment_role not in ASSIGNMENT_ROLES:
		frappe.throw(_("Invalid assignment role"))
	if not frappe.db.exists("Firm Member", {"firm": access.firm, "user": user, "status": "Active"}):
		frappe.throw(_("{0} is not an active member of your firm").format(user))
	existing = frappe.db.get_value("Client Assignment", {"client": client, "firm": access.firm, "user": user}, "name")
	if existing:
		frappe.db.set_value("Client Assignment", existing, {"assignment_role": assignment_role, "status": "Active"})
		name = existing
	else:
		name = frappe.get_doc(
			{"doctype": "Client Assignment", "client": client, "firm": access.firm, "user": user,
			 "assignment_role": assignment_role, "status": "Active"}
		).insert(ignore_permissions=True).name
	audit.record("client.assign", client=client, firm=access.firm, reference=("Client Assignment", name), detail={"user": user, "role": assignment_role})
	return {"name": name}


@frappe.whitelist(methods=["POST"])
def unassign(client: str, assignment: str):
	access = authz.require_client_access(client, LEAD)
	row = frappe.db.get_value("Client Assignment", assignment, ["client", "firm", "user"], as_dict=True)
	if not row or row.client != client or row.firm != access.firm:
		frappe.throw(_("Assignment not found"), frappe.PermissionError)
	frappe.db.set_value("Client Assignment", assignment, "status", "Inactive")
	audit.record("client.unassign", client=client, firm=access.firm, detail={"user": row.user})
	return {"name": assignment, "status": "Inactive"}


@frappe.whitelist(methods=["POST"])
def set_services(client: str, services: list | str, monthly_retainer: float | None = None):
	access = authz.require_client_access(client, LEAD)
	if access.role != FIRM_ADMIN:
		frappe.throw(_("Only firm admins change client services"), frappe.PermissionError)
	services = frappe.parse_json(services) if isinstance(services, str) else services
	invalid = [s for s in services if s not in authz.firm_modules(access.firm)]
	if invalid:
		frappe.throw(_("Modules not in your subscription: {0}").format(", ".join(invalid)))
	eng = frappe.get_doc("Client Engagement", {"client": client, "firm": access.firm, "status": "Active"})
	eng.set("services", [{"module": s} for s in services])
	if monthly_retainer is not None:
		eng.monthly_retainer = monthly_retainer
	eng.save(ignore_permissions=True)
	audit.record("client.set_services", client=client, firm=access.firm, detail={"services": services})
	return sorted(authz.client_modules(client, access.firm))


@frappe.whitelist(methods=["POST"])
def invite_portal_user(client: str, email: str, full_name: str, contact_role: str = "Owner", can_approve: bool = True, password: str | None = None):
	access = authz.require_client_access(client, LEAD)
	authz.require_module(access, "client_portal")
	if contact_role not in ("Owner", "Finance Contact", "Viewer"):
		frappe.throw(_("Invalid contact role"))
	if frappe.db.exists("Firm Member", {"user": (email or "").lower()}):
		frappe.throw(_("Firm staff cannot be client portal users"))
	user = ensure_user(email, full_name, CLIENT_ROLE, password=password, send_welcome=not password)
	existing = frappe.db.get_value("Client Portal User", {"client": client, "user": user}, "name")
	values = {"contact_role": contact_role, "can_approve": 1 if frappe.utils.sbool(can_approve) else 0, "status": "Active"}
	if existing:
		frappe.db.set_value("Client Portal User", existing, values)
		name = existing
	else:
		name = frappe.get_doc({"doctype": "Client Portal User", "client": client, "user": user, **values}).insert(ignore_permissions=True).name
	audit.record("client.invite_portal_user", client=client, firm=access.firm, detail={"user": user})
	return {"name": name, "user": user}


@frappe.whitelist(methods=["POST"])
def revoke_portal_user(client: str, portal_user: str):
	access = authz.require_client_access(client, LEAD)
	row = frappe.db.get_value("Client Portal User", portal_user, ["client", "user"], as_dict=True)
	if not row or row.client != client:
		frappe.throw(_("Portal user not found"), frappe.PermissionError)
	frappe.db.set_value("Client Portal User", portal_user, "status", "Inactive")
	audit.record("client.revoke_portal_user", client=client, firm=access.firm, detail={"user": row.user})
	return {"name": portal_user, "status": "Inactive"}


@frappe.whitelist(methods=["POST"])
def archive(client: str, reason: str | None = None):
	"""End this firm's engagement. The client is archived (and backed up) only
	when no other firm still serves it. Financial data is retained."""
	access = authz.require_client_access(client, LEAD)
	if access.role != FIRM_ADMIN:
		frappe.throw(_("Only firm admins can offboard clients"), frappe.PermissionError)
	eng = frappe.get_doc("Client Engagement", {"client": client, "firm": access.firm, "status": "Active"})
	eng.status = "Ended"
	eng.end_date = getdate()
	eng.billing_notes = "\n".join(filter(None, [eng.billing_notes, f"Offboarded: {reason or ''}".strip()]))
	eng.save(ignore_permissions=True)
	for a in frappe.get_all("Client Assignment", filters={"client": client, "firm": access.firm, "status": "Active"}, pluck="name"):
		frappe.db.set_value("Client Assignment", a, "status", "Inactive")
	remaining = frappe.db.count("Client Engagement", {"client": client, "status": "Active"})
	if not remaining:
		frappe.db.set_value("Client Business", client, {"status": "Archived", "archived_on": now_datetime()})
		if frappe.db.exists("Client Site", {"client": client, "status": "Active"}):
			enqueue_offboarding_backup(client)
	audit.record("client.archive", client=client, firm=access.firm, detail={"reason": reason, "client_archived": not remaining})
	return {"engagement": eng.name, "client_archived": not remaining}


@frappe.whitelist(methods=["GET"])
def team_candidates(client: str):
	access = authz.require_client_access(client, LEAD)
	return frappe.get_all(
		"Firm Member", filters={"firm": access.firm, "status": "Active"}, fields=["user", "full_name", "firm_role"], order_by="full_name asc"
	)
