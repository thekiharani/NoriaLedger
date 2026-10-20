"""Client-site bootstrap, executed by the hub's provisioner right after `bench new-site`.

    bench --site <site> execute noria_ledger.provisioning.bootstrap --kwargs '<json>'

Runs ERPNext's own setup wizard stages (company, chart of accounts, fiscal year,
country tax templates) and creates the service user the hub broker calls with.
The printed return value is parsed by the provisioner; it contains the API secret,
so the provisioner must not log it.
"""

import frappe
from frappe.utils import add_days, add_years, getdate

from noria_ledger.constants import MODULE_PROFILE, SERVICE_USER_ROLES


def bootstrap(
	company_name: str,
	company_abbr: str,
	fy_start_date: str,
	chart_of_accounts: str = "Standard with Numbers",
	country: str = "Kenya",
	currency: str = "KES",
	timezone: str = "Africa/Nairobi",
	service_user: str | None = None,
):
	frappe.set_user("Administrator")
	run_setup_wizard(company_name, company_abbr, fy_start_date, chart_of_accounts, country, currency, timezone)

	from noria_ledger.install import apply_configuration

	apply_configuration()
	credentials = ensure_service_user(service_user or f"noria-service@{frappe.local.site}")
	frappe.db.commit()
	return {
		"company": frappe.defaults.get_global_default("company") or company_name,
		"company_abbr": frappe.db.get_value("Company", company_name, "abbr"),
		**credentials,
	}


def run_setup_wizard(company_name, company_abbr, fy_start_date, chart_of_accounts, country, currency, timezone):
	if frappe.is_setup_complete():
		return

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	start = getdate(fy_start_date)
	end = add_days(add_years(start, 1), -1)
	result = setup_complete(
		{
			"language": "English",
			"country": country,
			"timezone": timezone,
			"currency": currency,
			"company_name": company_name,
			"company_abbr": company_abbr,
			"chart_of_accounts": chart_of_accounts,
			"fy_start_date": str(start),
			"fy_end_date": str(end),
			"setup_demo": 0,
			"enable_telemetry": 0,
		}
	)
	if not frappe.is_setup_complete():
		frappe.throw(f"ERPNext setup wizard did not complete: {result}")


def ensure_service_user(email: str) -> dict:
	"""Create (or rotate the secret of) the hub's service user on this site."""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = "Noria"
		user.last_name = "Service"
		user.send_welcome_email = 0
		user.user_type = "System User"

	user.module_profile = MODULE_PROFILE
	existing = {r.role for r in user.roles}
	for role in SERVICE_USER_ROLES:
		if role not in existing:
			user.append("roles", {"role": role})

	api_secret = frappe.generate_hash(length=32)
	if not user.api_key:
		user.api_key = frappe.generate_hash(length=20)
	user.api_secret = api_secret
	user.flags.ignore_password_policy = True
	user.save(ignore_permissions=True)
	return {"service_user": user.name, "api_key": user.api_key, "api_secret": api_secret}


def rotate_service_credentials(service_user: str):
	"""Issue a new API secret for the service user (old one stops working)."""
	frappe.set_user("Administrator")
	creds = ensure_service_user(service_user)
	frappe.db.commit()
	return creds


def describe():
	"""Small, secret-free status used by provisioning health checks."""
	return {
		"setup_complete": frappe.is_setup_complete(),
		"company": frappe.defaults.get_global_default("company"),
		"apps": frappe.get_installed_apps(),
	}
