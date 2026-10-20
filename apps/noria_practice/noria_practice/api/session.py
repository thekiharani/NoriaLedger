import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from noria_practice import authz
from noria_practice.constants import FIRM_ADMIN, PRACTICE_ROLE
from noria_practice.utils import ensure_user

DEFAULT_TRIAL_MODULES = (
	"bank_reconciliation",
	"practice_management",
	"document_management",
	"client_portal",
	"advanced_reporting",
)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def bootstrap():
	"""Session bootstrap for the SPA: identity, memberships, CSRF token."""
	user = frappe.session.user
	allow_signup = bool(frappe.conf.get("noria_allow_firm_signup"))
	if user == "Guest":
		return {"user": None, "allow_signup": allow_signup}

	from frappe.sessions import get_csrf_token

	portal = authz.portal_clients(user)
	names = dict(
		frappe.get_all(
			"Client Business",
			filters={"name": ["in", [p.client for p in portal] or [""]]},
			fields=["name", "business_name"],
			as_list=True,
		)
	)
	return {
		"user": user,
		"full_name": frappe.db.get_value("User", user, "full_name"),
		"csrf_token": get_csrf_token(),
		"is_platform_admin": authz.is_platform_admin(user),
		"firms": [
			{"firm": m.firm, "firm_name": m.firm_name, "firm_type": m.firm_type, "firm_role": m.firm_role,
			 "modules": sorted(authz.firm_modules(m.firm))}
			for m in authz.memberships(user)
		],
		"portal_clients": [
			{"client": p.client, "business_name": names.get(p.client), "contact_role": p.contact_role, "can_approve": p.can_approve}
			for p in portal
		],
		"allow_signup": allow_signup,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def signup_firm(
	firm_name: str,
	full_name: str,
	email: str,
	password: str,
	firm_type: str = "Accounting Firm",
	kra_pin: str | None = None,
	phone: str | None = None,
):
	"""Self-service onboarding of an accounting firm (or independent accountant).

	Disabled unless the site config sets noria_allow_firm_signup.
	"""
	if not frappe.conf.get("noria_allow_firm_signup"):
		frappe.throw(_("Sign-up is not available"), frappe.PermissionError)
	if firm_type not in ("Accounting Firm", "Independent Accountant"):
		frappe.throw(_("Invalid firm type"))
	if not (firm_name or "").strip():
		frappe.throw(_("Firm name is required"))
	if frappe.db.exists("User", (email or "").strip().lower()):
		frappe.throw(_("An account with this email already exists. Sign in instead."))
	return create_firm_with_admin(firm_name, firm_type, full_name, email, password, kra_pin, phone)


def create_firm_with_admin(firm_name, firm_type, full_name, email, password=None, kra_pin=None, phone=None, modules=DEFAULT_TRIAL_MODULES):
	user = ensure_user(email, full_name, PRACTICE_ROLE, password=password, send_welcome=not password)
	firm = frappe.get_doc(
		{
			"doctype": "Accounting Firm",
			"firm_name": firm_name.strip(),
			"firm_type": firm_type,
			"kra_pin": kra_pin,
			"email": email,
			"phone": phone,
			"status": "Active",
			"modules": [{"module": m, "enabled": 1} for m in modules],
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{"doctype": "Firm Member", "firm": firm.name, "user": user, "firm_role": FIRM_ADMIN, "status": "Active"}
	).insert(ignore_permissions=True)
	return {"firm": firm.name, "user": user}
