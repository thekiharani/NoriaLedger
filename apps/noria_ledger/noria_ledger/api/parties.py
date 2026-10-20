import frappe
from frappe import _

from noria_ledger.service import doc_summary, service_endpoint

PARTY_DOCTYPES = {"Customer": "customer_name", "Supplier": "supplier_name"}


def _validate_party_type(party_type: str):
	if party_type not in PARTY_DOCTYPES:
		frappe.throw(_("party_type must be Customer or Supplier"))


@frappe.whitelist(methods=["GET", "POST"])
@service_endpoint("parties.list")
def list_parties(party_type: str, search: str | None = None, limit: int = 200):
	_validate_party_type(party_type)
	name_field = PARTY_DOCTYPES[party_type]
	filters = {"disabled": 0}
	or_filters = None
	if search:
		or_filters = {name_field: ["like", f"%{search}%"], "tax_id": ["like", f"%{search}%"]}
	return frappe.get_all(
		party_type,
		filters=filters,
		or_filters=or_filters,
		fields=["name", f"{name_field} as party_name", "tax_id", "email_id", "mobile_no"],
		order_by=f"{name_field} asc",
		limit=min(int(limit), 1000),
	)


@frappe.whitelist(methods=["POST"])
@service_endpoint("parties.create", write=True)
def create(
	party_type: str,
	party_name: str,
	tax_id: str | None = None,
	email_id: str | None = None,
	mobile_no: str | None = None,
	idempotency_key: str | None = None,
):
	_validate_party_type(party_type)
	doc = frappe.new_doc(party_type)
	doc.set(PARTY_DOCTYPES[party_type], party_name.strip())
	doc.tax_id = tax_id
	doc.email_id = email_id
	doc.mobile_no = mobile_no
	if party_type == "Customer":
		doc.customer_type = "Company"
	else:
		doc.supplier_type = "Company"
	doc.insert()
	return doc_summary(doc, party_name=party_name)
