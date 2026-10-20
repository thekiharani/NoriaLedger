import json

import frappe


def record(action: str, client: str | None = None, firm: str | None = None, reference=None, detail: dict | None = None):
	"""Append-only audit event for hub actions (who did what to which client)."""
	ref_doctype, ref_name = reference if reference else (None, None)
	frappe.get_doc(
		{
			"doctype": "Noria Audit Event",
			"action": action,
			"user": frappe.session.user,
			"client": client,
			"firm": firm,
			"reference_doctype": ref_doctype,
			"reference_name": ref_name,
			"ip_address": getattr(frappe.local, "request_ip", None),
			"request_id": getattr(frappe.local, "noria_request_id", None),
			"detail": json.dumps(detail or {}, default=str)[:10000],
		}
	).insert(ignore_permissions=True)
