"""Client documents stored as private files on the client's own site.

Keeps each client's documents inside that client's site (separate storage and
backups). Only the hub service user can reach these endpoints; downloads are
logged on both the hub and the client site.
"""

import base64
import hashlib
import mimetypes
import os

import frappe
from frappe import _

from noria_ledger.service import service_endpoint

MAX_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".csv", ".xlsx", ".xls", ".doc", ".docx", ".txt", ".zip"}
# Leading bytes for formats where a mismatched extension is a red flag.
MAGIC = {
	".pdf": (b"%PDF",),
	".png": (b"\x89PNG",),
	".jpg": (b"\xff\xd8\xff",),
	".jpeg": (b"\xff\xd8\xff",),
	".xlsx": (b"PK",),
	".docx": (b"PK",),
	".zip": (b"PK",),
}


def _safe_filename(filename: str) -> str:
	name = os.path.basename((filename or "").replace("\\", "/")).strip()
	name = "".join(c for c in name if c.isalnum() or c in "._- ()")[:140]
	if not name or name.startswith("."):
		frappe.throw(_("Invalid file name"))
	return name


@frappe.whitelist(methods=["POST"])
@service_endpoint("documents.upload", write=True)
def upload(title: str, filename: str, content: str, category: str | None = None, period: str | None = None,
           hub_document: str | None = None, idempotency_key: str | None = None):
	name = _safe_filename(filename)
	ext = os.path.splitext(name)[1].lower()
	if ext not in ALLOWED_EXTENSIONS:
		frappe.throw(_("File type {0} is not allowed").format(ext or "(none)"))
	try:
		data = base64.b64decode(content, validate=True)
	except Exception:
		frappe.throw(_("File content must be base64 encoded"))
	if not data:
		frappe.throw(_("The file is empty"))
	if len(data) > MAX_BYTES:
		frappe.throw(_("Files are limited to 20 MB"))
	if ext in MAGIC and not data.startswith(MAGIC[ext]):
		frappe.throw(_("The file content does not match its {0} extension").format(ext))
	digest = hashlib.sha256(data).hexdigest()

	doc = frappe.get_doc(
		{
			"doctype": "Noria Document",
			"title": title[:140],
			"category": category,
			"period": period,
			"hub_document": hub_document,
			"file_name": name,
			"content_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
			"file_size": len(data),
			"content_hash": digest,
			"uploaded_by": frappe.flags.noria_acting_user,
		}
	).insert(ignore_permissions=True)
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": name,
			"is_private": 1,
			"attached_to_doctype": "Noria Document",
			"attached_to_name": doc.name,
			"content": data,
		}
	).save(ignore_permissions=True)
	doc.db_set("file", f.file_url)
	return {"doctype": "Noria Document", "name": doc.name, "content_hash": digest, "file_size": len(data),
	        "content_type": doc.content_type, "file_name": name}


@frappe.whitelist(methods=["POST"])
@service_endpoint("documents.download", write=True)
def download(name: str):
	"""Return the file as base64. Declared `write` so every download is logged."""
	doc = frappe.get_doc("Noria Document", name)
	file_name = frappe.db.get_value("File", {"attached_to_doctype": "Noria Document", "attached_to_name": doc.name}, "name")
	if not file_name:
		raise frappe.DoesNotExistError
	content = frappe.get_doc("File", file_name).get_content()
	if isinstance(content, str):
		content = content.encode()
	if hashlib.sha256(content).hexdigest() != doc.content_hash:
		frappe.throw(_("Stored file failed its integrity check"))
	return {"doctype": "Noria Document", "name": doc.name, "file_name": doc.file_name, "content_type": doc.content_type,
	        "content": base64.b64encode(content).decode()}
