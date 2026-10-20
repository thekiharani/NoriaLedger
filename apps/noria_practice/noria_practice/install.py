import frappe

from noria_practice.constants import CLIENT_ROLE, MODULES, PRACTICE_ROLE, TASK_TEMPLATES


def after_install():
	apply_configuration()


def after_migrate():
	apply_configuration()


def apply_configuration():
	ensure_roles()
	ensure_modules()
	ensure_task_templates()
	frappe.db.set_single_value("System Settings", "app_name", "Noria Ledger")
	frappe.db.commit()


def ensure_roles():
	# No desk access: firm staff and client users only use the Noria frontend,
	# which talks to whitelisted noria_practice.api methods.
	for role in (PRACTICE_ROLE, CLIENT_ROLE):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0, "is_custom": 1}).insert(
				ignore_permissions=True
			)


def ensure_modules():
	for order, (code, title, description, is_core) in enumerate(MODULES, start=1):
		if frappe.db.exists("Noria Module", code):
			continue
		frappe.get_doc(
			{
				"doctype": "Noria Module",
				"module_code": code,
				"title": title,
				"description": description,
				"is_core": is_core,
				"sort_order": order,
			}
		).insert(ignore_permissions=True)


def ensure_task_templates():
	"""Seed editable defaults once; firms/operators own them afterwards."""
	for tpl in TASK_TEMPLATES:
		if frappe.db.exists("Task Template", tpl["template_name"]):
			continue
		frappe.get_doc({"doctype": "Task Template", **tpl}).insert(ignore_permissions=True)
