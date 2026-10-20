"""Service-API plumbing shared by every `noria_ledger.api.*` endpoint.

Only the hub's service user (role "Noria Service", token auth) may call these
endpoints. The hub forwards the real Noria user in `X-Noria-Acting-User`; it is
recorded on created documents and in the Noria Activity Log, so every posting on
a client site is attributable to a person.
"""

import functools
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import frappe
from frappe import _

from noria_ledger.constants import SERVICE_ROLE

ACTING_USER_HEADER = "X-Noria-Acting-User"
REQUEST_ID_HEADER = "X-Noria-Request-Id"
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}$")


def _acting_user_from_request() -> str | None:
	value = frappe.get_request_header(ACTING_USER_HEADER) if getattr(frappe.local, "request", None) else None
	if value and not _EMAIL_RE.match(value):
		frappe.throw(_("Invalid acting user header"), frappe.ValidationError)
	return value


def require_service_caller():
	if frappe.session.user == "Guest":
		raise frappe.AuthenticationError
	roles = frappe.get_roles()
	if SERVICE_ROLE not in roles and "System Manager" not in roles:
		frappe.throw(_("Only the Noria service may call this endpoint"), frappe.PermissionError)


def service_endpoint(action: str | None = None, write: bool = False):
	"""Decorate a whitelisted function as a Noria service endpoint.

	* checks the caller is the service user (or a System Manager, for operators/tests)
	* binds the acting user for document stamping
	* for write endpoints: requires an acting user and writes an activity log row
	"""

	def decorator(fn):
		name = action or fn.__name__

		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			require_service_caller()
			acting_user = _acting_user_from_request() or frappe.flags.noria_acting_user
			if write and not acting_user and frappe.session.user != "Administrator":
				frappe.throw(_("{0} header is required").format(ACTING_USER_HEADER))
			frappe.flags.noria_acting_user = acting_user
			try:
				result = fn(*args, **kwargs)
			finally:
				frappe.flags.noria_acting_user = None
			if write and not (isinstance(result, dict) and result.get("idempotent_replay")):
				ref = result if isinstance(result, dict) else {}
				log_activity(
					name,
					acting_user,
					reference_doctype=ref.get("doctype"),
					reference_name=ref.get("name"),
					idempotency_key=kwargs.get("idempotency_key"),
					details={k: v for k, v in kwargs.items() if k not in ("content", "cmd")},
				)
			return result

		return wrapper

	return decorator


def stamp_acting_user(doc, method=None):
	"""doc_events hook: record the requesting Noria user on tracked documents."""
	acting_user = frappe.flags.noria_acting_user
	if acting_user and doc.meta.has_field("noria_acting_user") and not doc.get("noria_acting_user"):
		doc.noria_acting_user = acting_user


def log_activity(action, acting_user, reference_doctype=None, reference_name=None, idempotency_key=None, details=None, status="Success"):
	frappe.get_doc(
		{
			"doctype": "Noria Activity Log",
			"action": action,
			"status": status,
			"acting_user": acting_user,
			"service_user": frappe.session.user,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"idempotency_key": idempotency_key or None,
			"request_id": frappe.get_request_header(REQUEST_ID_HEADER) if getattr(frappe.local, "request", None) else None,
			"details": json.dumps(details or {}, default=str)[:10000],
		}
	).insert(ignore_permissions=True)


def find_idempotent_result(idempotency_key: str | None):
	"""Return the reference created by an earlier call with the same key, if any."""
	if not idempotency_key:
		return None
	if len(idempotency_key) > 120:
		frappe.throw(_("Idempotency key is too long"))
	row = frappe.db.get_value(
		"Noria Activity Log",
		{"idempotency_key": idempotency_key},
		["reference_doctype", "reference_name"],
		as_dict=True,
	)
	if row and row.reference_doctype and row.reference_name:
		return row
	return None


def to_decimal(value, field: str = "amount") -> Decimal:
	"""Parse a monetary input exactly (no binary floats), 2 decimal places."""
	if value in (None, ""):
		return Decimal("0.00")
	try:
		amount = Decimal(str(value))
	except InvalidOperation:
		frappe.throw(_("{0} must be a number").format(field))
	if not amount.is_finite():
		frappe.throw(_("{0} must be a finite number").format(field))
	quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	if quantized != amount:
		frappe.throw(_("{0} cannot have more than 2 decimal places").format(field))
	return quantized


def parse_json_arg(value, name: str):
	if isinstance(value, str):
		try:
			return json.loads(value)
		except ValueError:
			frappe.throw(_("{0} must be valid JSON").format(name))
	return value


def posting_date_filter(from_date: str | None, to_date: str | None):
	if from_date and to_date:
		return ["between", [from_date, to_date]]
	if from_date:
		return [">=", from_date]
	if to_date:
		return ["<=", to_date]
	return None


def get_company() -> str:
	company = frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw(_("This client site has no default company; setup is incomplete"))
	return company


def doc_summary(doc, **extra) -> dict:
	if doc.meta.is_submittable:
		status = doc.get("status") or {0: "Draft", 1: "Submitted", 2: "Cancelled"}[doc.docstatus]
	else:
		status = doc.get("status") or "Saved"
	return {"doctype": doc.doctype, "name": doc.name, "docstatus": doc.docstatus, "status": status, **extra}
