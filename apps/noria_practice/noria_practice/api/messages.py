import frappe
from frappe import _

from noria_practice import audit, authz
from noria_practice.constants import READ
from noria_practice.utils import touch_client, user_names

MAX_LEN = 4000


def _side_for(client: str) -> tuple[str, str | None]:
	access = authz.client_access(client)
	if access:
		return "Firm", access.firm
	authz.require_portal_access(client)
	return "Client", None


@frappe.whitelist(methods=["GET"])
def list_messages(client: str, limit: int = 200):
	_side_for(client)
	rows = frappe.get_all("Client Message", filters={"client": client},
	                      fields=["name", "sender", "sender_side", "message", "creation"],
	                      order_by="creation desc", limit=min(int(limit), 500))
	names = user_names([r.sender for r in rows])
	for r in rows:
		r["sender_name"] = names.get(r.sender)
	return list(reversed(rows))


@frappe.whitelist(methods=["POST"])
def send(client: str, message: str):
	side, firm = _side_for(client)
	if side == "Firm":
		authz.require_client_access(client, READ)
	text = (message or "").strip()
	if not text:
		frappe.throw(_("Message is empty"))
	if len(text) > MAX_LEN:
		frappe.throw(_("Messages are limited to {0} characters").format(MAX_LEN))
	doc = frappe.get_doc({"doctype": "Client Message", "client": client, "sender": frappe.session.user,
	                      "sender_side": side, "firm": firm, "message": text}).insert(ignore_permissions=True)
	touch_client(client)
	audit.record("message.send", client=client, firm=firm, reference=("Client Message", doc.name))
	return {"name": doc.name, "sender_side": side, "creation": doc.creation}
