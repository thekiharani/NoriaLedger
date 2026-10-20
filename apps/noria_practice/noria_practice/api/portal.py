"""Client portal: what a business owner sees. Only their own client(s), only
published reports, their document requests/documents, and messages."""

import frappe
from frappe import _
from frappe.utils import now_datetime

from noria_practice import audit, authz
from noria_practice.api import documents as docs
from noria_practice.api.monthly_reports import SUMMARY_FIELDS, serialize
from noria_practice.utils import user_names

PORTAL_TASK_FIELDS = ["name", "title", "task_type", "period", "status", "due_date"]


def _portal_enabled(client: str):
	firms = frappe.get_all("Client Engagement", filters={"client": client, "status": "Active"}, pluck="firm")
	if not any("client_portal" in authz.client_modules(client, f) for f in firms):
		frappe.throw(_("The client portal is not enabled for this business"), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def overview(client: str):
	row = authz.require_portal_access(client)
	_portal_enabled(client)
	cb = frappe.get_doc("Client Business", client)
	firms = frappe.get_all("Client Engagement", filters={"client": client, "status": "Active"}, pluck="firm")
	team = frappe.get_all("Client Assignment", filters={"client": client, "status": "Active", "firm": ["in", firms or [""]]},
	                      fields=["user", "assignment_role"])
	names = user_names([t.user for t in team])
	return {
		"client": client,
		"business_name": cb.business_name,
		"kra_pin": cb.kra_pin,
		"status": cb.status,
		"my_role": row.contact_role,
		"can_approve": row.can_approve,
		"firms": [frappe.db.get_value("Accounting Firm", f, "firm_name") for f in firms],
		"accountants": [{"full_name": names.get(t.user), "role": t.assignment_role} for t in team],
		"open_requests": docs.list_requests_for(client, open_only=True),
		"published_reports": reports(client),
		"work_in_progress": frappe.get_all(
			"Practice Task", filters={"client": client, "status": ["in", ["Open", "In Progress", "In Review"]]},
			fields=PORTAL_TASK_FIELDS, order_by="due_date asc", limit=50,
		),
		"last_activity": cb.last_activity,
	}


@frappe.whitelist(methods=["GET"])
def reports(client: str):
	authz.require_portal_access(client)
	_portal_enabled(client)
	return frappe.get_all("Monthly Report", filters={"client": client, "status": "Published"},
	                      fields=SUMMARY_FIELDS, order_by="period desc")


@frappe.whitelist(methods=["GET"])
def report(report: str):
	doc = frappe.get_doc("Monthly Report", report)
	authz.require_portal_access(doc.client)
	if doc.status != "Published":
		frappe.throw(_("Report not found"), frappe.PermissionError)
	audit.record("portal.view_report", client=doc.client, reference=("Monthly Report", doc.name))
	data = serialize(doc, full=True)
	data.pop("review_notes", None)  # internal
	return data


@frappe.whitelist(methods=["POST"])
def acknowledge_report(report: str):
	"""Client approval of a published report (designated approver only)."""
	doc = frappe.get_doc("Monthly Report", report)
	authz.require_portal_access(doc.client, approve=True)
	if doc.status != "Published":
		frappe.throw(_("Only published reports can be approved"))
	doc.client_acknowledged_by = frappe.session.user
	doc.client_acknowledged_on = now_datetime()
	doc.save(ignore_permissions=True)
	audit.record("portal.acknowledge_report", client=doc.client, reference=("Monthly Report", doc.name))
	return {f: doc.get(f) for f in SUMMARY_FIELDS}


@frappe.whitelist(methods=["GET"])
def documents(client: str):
	authz.require_portal_access(client)
	_portal_enabled(client)
	return docs.list_documents_for(client)


@frappe.whitelist(methods=["POST"])
def upload(client: str, title: str, filename: str, content: str, category: str = "Other", period: str | None = None,
           document_request: str | None = None):
	authz.require_portal_access(client)
	_portal_enabled(client)
	return docs.store_document(client, "Client", title, filename, content, category, period, document_request)


@frappe.whitelist(methods=["POST"])
def download(document: str):
	client = frappe.db.get_value("Client Document", document, "client")
	if not client:
		frappe.throw(_("Document not found"), frappe.PermissionError)
	authz.require_portal_access(client)
	return docs.fetch_document(document)
