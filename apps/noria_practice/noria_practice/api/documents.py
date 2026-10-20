"""Document requests and client documents (firm side + shared helpers).

Files live on the client's own site (`noria_ledger.api.documents`); the hub keeps
metadata and brokers uploads/downloads after authorization.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from noria_practice import audit, authz, broker
from noria_practice.constants import READ, WRITE
from noria_practice.utils import period_bounds, touch_client, user_names

MODULE = "document_management"
CATEGORIES = ("Bank Statement", "Receipt", "Invoice", "Tax Document", "Payroll", "Engagement Letter", "Report", "Other")
DOC_FIELDS = ["name", "title", "client", "category", "period", "document_request", "status", "file_name", "content_type",
              "file_size", "content_hash", "uploaded_by", "uploaded_by_side", "review_note", "creation"]
REQ_FIELDS = ["name", "title", "client", "firm", "category", "period", "status", "due_date", "requested_by", "notes",
              "response_note", "creation"]


def store_document(client: str, side: str, title: str, filename: str, content: str, category: str = "Other",
                   period: str | None = None, document_request: str | None = None) -> dict:
	if category not in CATEGORIES:
		frappe.throw(_("Invalid category"))
	if period:
		period_bounds(period)
	if document_request:
		req = frappe.db.get_value("Document Request", document_request, ["client", "status"], as_dict=True)
		if not req or req.client != client:
			frappe.throw(_("Document request not found"), frappe.PermissionError)
		if req.status in ("Accepted", "Cancelled"):
			frappe.throw(_("This request is already closed"))
	meta = frappe.get_doc(
		{"doctype": "Client Document", "title": title, "client": client, "category": category, "period": period,
		 "document_request": document_request, "status": "Pending Review", "uploaded_by": frappe.session.user,
		 "uploaded_by_side": side}
	).insert(ignore_permissions=True)
	stored = broker.call(
		client,
		"documents.upload",
		{"title": title, "filename": filename, "content": content, "category": category, "period": period,
		 "hub_document": meta.name},
	)
	meta.db_set(
		{
			"site_document": stored["name"],
			"stored_on_site": frappe.db.get_value("Client Site", client, "site_name"),
			"file_name": stored["file_name"],
			"content_type": stored["content_type"],
			"file_size": stored["file_size"],
			"content_hash": stored["content_hash"],
		}
	)
	if document_request:
		frappe.db.set_value("Document Request", document_request, "status", "Uploaded")
	touch_client(client)
	audit.record("document.upload", client=client, reference=("Client Document", meta.name),
	             detail={"side": side, "sha256": stored["content_hash"], "size": stored["file_size"]})
	return {f: meta.get(f) for f in DOC_FIELDS}


def fetch_document(doc_name: str) -> dict:
	meta = frappe.get_doc("Client Document", doc_name)
	data = broker.call(meta.client, "documents.download", {"name": meta.site_document})
	audit.record("document.download", client=meta.client, reference=("Client Document", meta.name))
	return {"file_name": data["file_name"], "content_type": data["content_type"], "content": data["content"]}


def list_documents_for(client: str, status: str | None = None):
	filters = {"client": client}
	if status:
		filters["status"] = status
	rows = frappe.get_all("Client Document", filters=filters, fields=DOC_FIELDS, order_by="creation desc", limit=500)
	names = user_names([r.uploaded_by for r in rows])
	for r in rows:
		r["uploaded_by_name"] = names.get(r.uploaded_by)
	return rows


def list_requests_for(client: str, open_only: bool = False):
	filters = {"client": client}
	if open_only:
		filters["status"] = ["in", ["Requested", "Uploaded", "Rejected"]]
	return frappe.get_all("Document Request", filters=filters, fields=REQ_FIELDS, order_by="creation desc", limit=500)


@frappe.whitelist(methods=["GET"])
def documents(client: str, status: str | None = None):
	access = authz.require_client_access(client, READ)
	authz.require_module(access, MODULE)
	return list_documents_for(client, status)


@frappe.whitelist(methods=["GET"])
def requests(client: str | None = None, open_only: bool = True):
	if client:
		access = authz.require_client_access(client, READ)
		authz.require_module(access, MODULE)
		return list_requests_for(client, frappe.utils.sbool(open_only))
	clients = list(authz.accessible_clients())
	if not clients:
		return []
	filters = {"client": ["in", clients]}
	if frappe.utils.sbool(open_only):
		filters["status"] = ["in", ["Requested", "Uploaded", "Rejected"]]
	return frappe.get_all("Document Request", filters=filters, fields=REQ_FIELDS, order_by="due_date asc", limit=1000)


@frappe.whitelist(methods=["POST"])
def create_request(client: str, title: str, category: str = "Other", period: str | None = None,
                   due_date: str | None = None, notes: str | None = None):
	access = authz.require_client_access(client, WRITE)
	authz.require_module(access, MODULE)
	if category not in CATEGORIES:
		frappe.throw(_("Invalid category"))
	if period:
		period_bounds(period)
	doc = frappe.get_doc(
		{"doctype": "Document Request", "title": title, "client": client, "firm": access.firm, "category": category,
		 "period": period, "due_date": getdate(due_date) if due_date else None, "notes": notes,
		 "status": "Requested", "requested_by": frappe.session.user}
	).insert(ignore_permissions=True)
	audit.record("document.request", client=client, firm=access.firm, reference=("Document Request", doc.name))
	return {f: doc.get(f) for f in REQ_FIELDS}


@frappe.whitelist(methods=["POST"])
def update_request(request: str, status: str, response_note: str | None = None):
	doc = frappe.get_doc("Document Request", request)
	access = authz.require_client_access(doc.client, WRITE)
	if access.firm != doc.firm:
		frappe.throw(_("Request not found"), frappe.PermissionError)
	if status not in ("Accepted", "Rejected", "Cancelled", "Requested"):
		frappe.throw(_("Invalid status"))
	doc.status = status
	doc.response_note = response_note
	doc.save(ignore_permissions=True)
	audit.record("document.request_update", client=doc.client, firm=doc.firm, reference=("Document Request", doc.name), detail={"status": status})
	return {f: doc.get(f) for f in REQ_FIELDS}


@frappe.whitelist(methods=["POST"])
def upload(client: str, title: str, filename: str, content: str, category: str = "Other", period: str | None = None,
           document_request: str | None = None):
	access = authz.require_client_access(client, WRITE)
	authz.require_module(access, MODULE)
	return store_document(client, "Firm", title, filename, content, category, period, document_request)


@frappe.whitelist(methods=["POST"])
def review(document: str, status: str, review_note: str | None = None):
	meta = frappe.get_doc("Client Document", document)
	access = authz.require_client_access(meta.client, WRITE)
	authz.require_module(access, MODULE)
	if status not in ("Accepted", "Rejected", "Pending Review"):
		frappe.throw(_("Invalid status"))
	meta.status = status
	meta.review_note = review_note
	meta.save(ignore_permissions=True)
	if meta.document_request and status in ("Accepted", "Rejected"):
		frappe.db.set_value("Document Request", meta.document_request, {"status": status, "response_note": review_note})
	audit.record("document.review", client=meta.client, firm=access.firm, reference=("Client Document", meta.name), detail={"status": status})
	return {f: meta.get(f) for f in DOC_FIELDS}


@frappe.whitelist(methods=["POST"])
def download(document: str):
	meta = frappe.db.get_value("Client Document", document, ["client"], as_dict=True)
	if not meta:
		frappe.throw(_("Document not found"), frappe.PermissionError)
	access = authz.require_client_access(meta.client, READ)
	authz.require_module(access, MODULE)
	return fetch_document(document)

