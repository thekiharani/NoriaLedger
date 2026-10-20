"""Install / migrate hooks: accounting-only presentation of a client site.

Upstream ERPNext stays intact. We only add roles, a module profile, custom fields
and hide unrelated workspaces/desktop icons. Hiding is presentation; the service
API and role permissions are the security boundary.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from noria_ledger.constants import (
	ACCOUNTANT_ROLE,
	ALLOWED_MODULES,
	MODULE_PROFILE,
	SERVICE_ROLE,
	VISIBLE_WORKSPACES,
)

TRACKED_DOCTYPES = ("Journal Entry", "Sales Invoice", "Purchase Invoice", "Payment Entry", "Bank Transaction")


def after_install():
	apply_configuration()


def after_migrate():
	apply_configuration()


def apply_configuration():
	ensure_roles()
	ensure_custom_fields()
	ensure_module_profile()
	hide_unrelated_workspaces()
	apply_branding()
	frappe.db.commit()


def ensure_roles():
	for role_name, desk_access in ((SERVICE_ROLE, 1), (ACCOUNTANT_ROLE, 1)):
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role_name, "desk_access": desk_access, "is_custom": 1}
			).insert(ignore_permissions=True)


def ensure_custom_fields():
	acting_user = {
		"fieldname": "noria_acting_user",
		"label": "Noria Acting User",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"print_hide": 1,
		"insert_after": "amended_from",
		"description": "Noria user who requested this document through the practice hub",
	}
	fields = {doctype: [acting_user] for doctype in TRACKED_DOCTYPES}
	fields["Bank Transaction"] = [
		acting_user,
		{
			"fieldname": "noria_fingerprint",
			"label": "Noria Import Fingerprint",
			"fieldtype": "Data",
			"read_only": 1,
			"no_copy": 1,
			"unique": 1,
			"insert_after": "transaction_id",
			"description": "Duplicate-detection key computed by the Noria statement importer",
		},
		{
			"fieldname": "noria_import_batch",
			"label": "Noria Import Batch",
			"fieldtype": "Data",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "noria_fingerprint",
		},
	]
	create_custom_fields(fields, ignore_validate=True, update=True)


def ensure_module_profile():
	all_modules = frappe.get_all("Module Def", pluck="name")
	blocked = sorted(m for m in all_modules if m not in ALLOWED_MODULES)
	if frappe.db.exists("Module Profile", MODULE_PROFILE):
		profile = frappe.get_doc("Module Profile", MODULE_PROFILE)
		profile.set("block_modules", [])
	else:
		profile = frappe.new_doc("Module Profile")
		profile.module_profile_name = MODULE_PROFILE
	for module in blocked:
		profile.append("block_modules", {"module": module})
	profile.save(ignore_permissions=True)


def hide_unrelated_workspaces():
	for ws in frappe.get_all("Workspace", filters={"public": 1}, fields=["name", "is_hidden"]):
		hidden = 0 if ws.name in VISIBLE_WORKSPACES else 1
		if ws.is_hidden != hidden:
			frappe.db.set_value("Workspace", ws.name, "is_hidden", hidden, update_modified=False)

	if frappe.db.exists("DocType", "Desktop Icon"):
		visible_labels = {*VISIBLE_WORKSPACES, "Accounts", "Settings"}
		for icon in frappe.get_all("Desktop Icon", fields=["name", "label", "hidden"]):
			hidden = 0 if icon.label in visible_labels else 1
			if icon.hidden != hidden:
				frappe.db.set_value("Desktop Icon", icon.name, "hidden", hidden, update_modified=False)


def apply_branding():
	frappe.db.set_single_value("System Settings", "app_name", "Noria Ledger")
	frappe.db.set_single_value("Website Settings", "app_name", "Noria Ledger")
