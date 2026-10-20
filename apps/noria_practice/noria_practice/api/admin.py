"""Platform-operator endpoints (System Manager only)."""

import frappe
from frappe import _
from frappe.utils import getdate

from noria_practice import audit, authz
from noria_practice.api.session import create_firm_with_admin


@frappe.whitelist(methods=["POST"])
def create_firm(firm_name: str, firm_type: str, admin_email: str, admin_full_name: str, modules: list | str | None = None,
                password: str | None = None):
	authz.require_platform_admin()
	modules = frappe.parse_json(modules) if isinstance(modules, str) else modules
	result = create_firm_with_admin(firm_name, firm_type, admin_full_name, admin_email, password=password,
	                                **({"modules": modules} if modules is not None else {}))
	audit.record("admin.create_firm", firm=result["firm"])
	return result


@frappe.whitelist(methods=["POST"])
def grant_engagement(client: str, firm: str, services: list | str | None = None):
	"""Authorise an additional firm to serve a client (explicit, audited)."""
	authz.require_platform_admin()
	if frappe.db.exists("Client Engagement", {"client": client, "firm": firm, "status": "Active"}):
		frappe.throw(_("This firm already serves this client"))
	services = frappe.parse_json(services) if isinstance(services, str) else (services or [])
	eng = frappe.get_doc({"doctype": "Client Engagement", "client": client, "firm": firm, "status": "Active",
	                      "start_date": getdate(), "services": [{"module": s} for s in services]}).insert(ignore_permissions=True)
	audit.record("admin.grant_engagement", client=client, firm=firm, reference=("Client Engagement", eng.name))
	return {"name": eng.name}
