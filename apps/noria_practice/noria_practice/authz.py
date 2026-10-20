"""Authorization for the practice hub — the single place access is decided.

Model
-----
* A user belongs to firms through active `Firm Member` rows (firm_role).
* A firm serves a client through an active `Client Engagement`; a client can be
  served by several firms at once.
* A user may act on a client when, through a firm with an active engagement:
    - they are that firm's Firm Admin (full access), or
    - they hold an active `Client Assignment` for the client in that firm.
* Client (business-owner) users reach only their own client via
  `Client Portal User`, and only portal endpoints.
* Platform operators (System Manager) administer the platform but are not
  implicitly given client data access through the product APIs.

Hub DocTypes grant permissions to System Manager only, so /api/resource cannot be
used by ordinary users; every product API calls into this module first.
"""

from dataclasses import dataclass

import frappe
from frappe import _

from noria_practice.constants import ACCESS_LEVELS, FIRM_ADMIN, LEAD, READ

PLATFORM_ROLES = ("System Manager",)


@dataclass(frozen=True)
class ClientAccess:
	client: str
	firm: str
	level: int
	role: str  # "Firm Admin" or the assignment role


def session_user() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		raise frappe.AuthenticationError(_("Login required"))
	return user


def is_platform_admin(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(set(frappe.get_roles(user)) & set(PLATFORM_ROLES))


def require_platform_admin():
	if not is_platform_admin(session_user()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def memberships(user: str | None = None) -> list[dict]:
	user = user or session_user()
	fm = frappe.qb.DocType("Firm Member")
	firm = frappe.qb.DocType("Accounting Firm")
	return (
		frappe.qb.from_(fm)
		.join(firm)
		.on(fm.firm == firm.name)
		.select(fm.firm, fm.firm_role, firm.firm_name, firm.firm_type)
		.where((fm.user == user) & (fm.status == "Active") & (firm.status == "Active"))
		.run(as_dict=True)
	)


def firm_role(firm: str, user: str | None = None) -> str | None:
	user = user or session_user()
	if frappe.db.get_value("Accounting Firm", firm, "status") != "Active":
		return None
	return frappe.db.get_value("Firm Member", {"firm": firm, "user": user, "status": "Active"}, "firm_role")


def require_firm_member(firm: str, roles: tuple[str, ...] | None = None) -> str:
	role = firm_role(firm)
	if not role or (roles and role not in roles):
		frappe.throw(_("Not permitted for this firm"), frappe.PermissionError)
	return role


def require_firm_admin(firm: str) -> str:
	return require_firm_member(firm, (FIRM_ADMIN,))


def client_access(client: str, user: str | None = None) -> ClientAccess | None:
	"""Highest access level the user has to the client across their firms."""
	user = user or session_user()
	best: ClientAccess | None = None
	for m in memberships(user):
		if not frappe.db.exists("Client Engagement", {"client": client, "firm": m.firm, "status": "Active"}):
			continue
		if m.firm_role == FIRM_ADMIN:
			candidate = ClientAccess(client, m.firm, LEAD, FIRM_ADMIN)
		else:
			role = frappe.db.get_value(
				"Client Assignment",
				{"client": client, "firm": m.firm, "user": user, "status": "Active"},
				"assignment_role",
			)
			if not role:
				continue
			candidate = ClientAccess(client, m.firm, ACCESS_LEVELS[role], role)
		if best is None or candidate.level > best.level:
			best = candidate
	return best


def require_client_access(client: str, level: int = READ) -> ClientAccess:
	if not client or not isinstance(client, str):
		frappe.throw(_("Client is required"))
	access = client_access(client)
	if not access or access.level < level:
		# Same response whether the client exists or not: no existence oracle.
		frappe.throw(_("Client not found or access denied"), frappe.PermissionError)
	return access


def accessible_clients(user: str | None = None) -> dict[str, ClientAccess]:
	"""All clients the user may see, keyed by client name (bounded by firm size)."""
	user = user or session_user()
	result: dict[str, ClientAccess] = {}
	for m in memberships(user):
		engaged = frappe.get_all(
			"Client Engagement", filters={"firm": m.firm, "status": "Active"}, pluck="client"
		)
		if not engaged:
			continue
		if m.firm_role == FIRM_ADMIN:
			for c in engaged:
				_keep_best(result, ClientAccess(c, m.firm, LEAD, FIRM_ADMIN))
			continue
		for a in frappe.get_all(
			"Client Assignment",
			filters={"firm": m.firm, "user": user, "status": "Active", "client": ["in", engaged]},
			fields=["client", "assignment_role"],
		):
			_keep_best(result, ClientAccess(a.client, m.firm, ACCESS_LEVELS[a.assignment_role], a.assignment_role))
	return result


def _keep_best(result, candidate):
	current = result.get(candidate.client)
	if current is None or candidate.level > current.level:
		result[candidate.client] = candidate


# ----------------------------------------------------------------- portal users


def portal_clients(user: str | None = None) -> list[dict]:
	user = user or session_user()
	return frappe.get_all(
		"Client Portal User",
		filters={"user": user, "status": "Active"},
		fields=["client", "contact_role", "can_approve"],
	)


def require_portal_access(client: str, approve: bool = False) -> dict:
	for row in portal_clients():
		if row.client == client and (not approve or row.can_approve):
			if frappe.db.get_value("Client Business", client, "status") == "Archived":
				break
			return row
	frappe.throw(_("Client not found or access denied"), frappe.PermissionError)


# ---------------------------------------------------------------- entitlements


def firm_modules(firm: str) -> set[str]:
	core = set(frappe.get_all("Noria Module", filters={"is_core": 1}, pluck="name"))
	enabled = set(
		frappe.get_all(
			"Firm Module", filters={"parent": firm, "parenttype": "Accounting Firm", "enabled": 1}, pluck="module"
		)
	)
	return core | enabled


def client_modules(client: str, firm: str) -> set[str]:
	"""Modules usable for this client through this firm.

	Firm subscription ∩ engagement services (an engagement without an explicit
	service list gets all of the firm's modules). Core accounting always applies.
	"""
	available = firm_modules(firm)
	engagement = frappe.db.get_value("Client Engagement", {"client": client, "firm": firm, "status": "Active"}, "name")
	if not engagement:
		return set()
	services = set(
		frappe.get_all(
			"Engagement Service", filters={"parent": engagement, "parenttype": "Client Engagement"}, pluck="module"
		)
	)
	core = set(frappe.get_all("Noria Module", filters={"is_core": 1}, pluck="name"))
	return available & (services | core) if services else available


def client_modules_bulk(pairs: list[tuple[str, str]]) -> dict[str, set[str]]:
	"""client_modules for many (client, firm) pairs with a constant number of queries."""
	if not pairs:
		return {}
	core = set(frappe.get_all("Noria Module", filters={"is_core": 1}, pluck="name"))
	firms = {f for _c, f in pairs}
	firm_mods = {f: set(core) for f in firms}
	for row in frappe.get_all(
		"Firm Module",
		filters={"parent": ["in", list(firms)], "parenttype": "Accounting Firm", "enabled": 1},
		fields=["parent", "module"],
	):
		firm_mods[row.parent].add(row.module)
	engagements = frappe.get_all(
		"Client Engagement",
		filters={"client": ["in", [c for c, _f in pairs]], "firm": ["in", list(firms)], "status": "Active"},
		fields=["name", "client", "firm"],
	)
	eng_by_pair = {(e.client, e.firm): e.name for e in engagements}
	services: dict[str, set[str]] = {}
	for row in frappe.get_all(
		"Engagement Service",
		filters={"parent": ["in", [e.name for e in engagements] or [""]], "parenttype": "Client Engagement"},
		fields=["parent", "module"],
	):
		services.setdefault(row.parent, set()).add(row.module)
	result = {}
	for client, firm in pairs:
		eng = eng_by_pair.get((client, firm))
		if not eng:
			result[client] = set()
			continue
		svc = services.get(eng)
		result[client] = firm_mods[firm] & (svc | core) if svc else firm_mods[firm]
	return result


def require_module(access: ClientAccess, module: str):
	if module not in client_modules(access.client, access.firm):
		frappe.throw(
			_("The {0} module is not enabled for this client").format(
				frappe.db.get_value("Noria Module", module, "title") or module
			),
			frappe.PermissionError,
		)


def require_firm_module(firm: str, module: str):
	if module not in firm_modules(firm):
		frappe.throw(_("The {0} module is not enabled for this firm").format(module), frappe.PermissionError)
