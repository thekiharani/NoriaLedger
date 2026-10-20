"""Server-to-server calls from the hub to a client business site.

The browser never talks to client sites. After `authz` has authorised the user,
the hub calls the client site's `noria_ledger.api.*` endpoint with that site's
service credentials, forwarding the acting user for attribution.

Client sites are addressed through the internal `backend-ledger` gunicorn pool
(`noria_client_site_base_url`, default http://backend-ledger:8000; a pool separate
from the hub's avoids thread-starvation deadlocks) with the Host / X-Frappe-Site-Name header naming the
site; they are not routed by the public edge.
"""

import json
import uuid

import frappe
import requests
from frappe import _

DEFAULT_TIMEOUT = (5, 120)  # connect, read (reports can be slow)


class ClientSiteError(frappe.ValidationError):
	pass


def _site_credentials(client: str) -> dict:
	site = frappe.db.get_value(
		"Client Site", {"client": client, "status": "Active"}, ["name", "site_name", "api_key"], as_dict=True
	)
	if not site:
		frappe.throw(_("This client's accounting workspace is not provisioned yet"), ClientSiteError)
	from frappe.utils.password import get_decrypted_password

	secret = get_decrypted_password("Client Site", site.name, "api_secret", raise_exception=False)
	if not secret:
		frappe.throw(_("Client workspace credentials are missing"), ClientSiteError)
	return {"site_name": site.site_name, "api_key": site.api_key, "api_secret": secret}


def call(client: str, method: str, payload: dict | None = None, acting_user: str | None = None, timeout=DEFAULT_TIMEOUT):
	"""POST to noria_ledger.api.<method> on the client's site and return `message`."""
	if not method.replace(".", "").replace("_", "").isalnum():
		frappe.throw(_("Invalid method"))
	creds = _site_credentials(client)
	base_url = (frappe.conf.get("noria_client_site_base_url") or "http://backend-ledger:8000").rstrip("/")
	request_id = getattr(frappe.local, "noria_request_id", None) or uuid.uuid4().hex
	session = requests.Session()
	session.trust_env = False  # internal call: never route through HTTP(S)_PROXY
	try:
		resp = session.post(
			f"{base_url}/api/method/noria_ledger.api.{method}",
			data=json.dumps(payload or {}, default=str),
			headers={
				"Host": creds["site_name"],
				"X-Frappe-Site-Name": creds["site_name"],
				"Authorization": f"token {creds['api_key']}:{creds['api_secret']}",
				"Content-Type": "application/json",
				"Accept": "application/json",
				"X-Noria-Acting-User": acting_user or frappe.session.user,
				"X-Noria-Request-Id": request_id,
			},
			timeout=timeout,
		)
	except requests.RequestException:
		frappe.log_error(title=f"Client site unreachable: {client}")
		frappe.throw(_("The client's accounting workspace is unavailable. Try again shortly."), ClientSiteError)
	finally:
		session.close()

	try:
		body = resp.json()
	except ValueError:
		body = {}

	if resp.status_code == 200 and "message" in body:
		return body["message"]
	raise_for_client_error(client, method, resp.status_code, body)


def raise_for_client_error(client, method, status, body):
	"""Translate a client-site error into a safe message (never forward tracebacks)."""
	messages = []
	for raw in json.loads(body.get("_server_messages") or "[]") if body.get("_server_messages") else []:
		try:
			msg = json.loads(raw).get("message")
		except (ValueError, AttributeError):
			msg = None
		if msg:
			messages.append(frappe.utils.strip_html(msg))
	if not messages and body.get("exception"):
		# "frappe.exceptions.ValidationError: <message>" — keep the message part only.
		text = str(body["exception"]).split(":", 1)[-1].strip()
		if text and "Traceback" not in text:
			messages.append(frappe.utils.strip_html(text)[:500])
	exc_type = body.get("exc_type") or ""
	if status in (401, 403) and exc_type in ("AuthenticationError", ""):
		frappe.log_error(title=f"Client site auth failed: {client}", message=f"{method} -> {status}")
		frappe.throw(_("The client's accounting workspace rejected the service credentials"), ClientSiteError)
	if exc_type == "DoesNotExistError" or status == 404:
		frappe.throw(messages[0] if messages else _("Record not found"), frappe.DoesNotExistError)
	if status >= 500 and not messages:
		frappe.log_error(title=f"Client site error: {client}", message=f"{method} -> {status}: {str(body)[:2000]}")
		frappe.throw(_("The client's accounting workspace failed to process the request"), ClientSiteError)
	frappe.throw("\n".join(messages) if messages else _("Request failed"), ClientSiteError)
