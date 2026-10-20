"""Monthly management reports: prepare -> internal review -> approve -> publish.

Figures are snapshots of ERPNext's own Trial Balance, P&L and Balance Sheet taken
from the client site at preparation time, so what the reviewer approves is
exactly what the client sees.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from noria_practice import audit, authz, broker
from noria_practice.constants import LEAD, READ, REVIEW, WRITE
from noria_practice.utils import period_bounds, user_names

SUMMARY_FIELDS = ["name", "client", "firm", "period", "from_date", "to_date", "status", "prepared_by", "reviewed_by",
                  "published_by", "published_on", "currency", "total_income", "total_expense", "net_profit",
                  "snapshot_taken_on", "client_acknowledged_by", "client_acknowledged_on"]


def _get(report: str, level: int):
	doc = frappe.get_doc("Monthly Report", report)
	access = authz.require_client_access(doc.client, level)
	if access.firm != doc.firm:
		frappe.throw(_("Report not found"), frappe.PermissionError)
	return doc, access


def serialize(doc, full: bool = False) -> dict:
	data = {f: doc.get(f) for f in SUMMARY_FIELDS}
	data["accountant_notes"] = doc.accountant_notes
	data["client_name"] = frappe.db.get_value("Client Business", doc.client, "business_name")
	names = user_names([doc.prepared_by, doc.reviewed_by, doc.published_by])
	data["prepared_by_name"] = names.get(doc.prepared_by)
	data["reviewed_by_name"] = names.get(doc.reviewed_by)
	if full:
		data["review_notes"] = doc.review_notes
		for key in ("trial_balance", "profit_and_loss", "balance_sheet"):
			value = doc.get(key)
			data[key] = json.loads(value) if isinstance(value, str) and value else value
	return data


@frappe.whitelist(methods=["GET"])
def list_reports(client: str | None = None, status: str | None = None, period: str | None = None):
	if client:
		authz.require_client_access(client, READ)
		allowed = {client: None}
	else:
		allowed = authz.accessible_clients()
	if not allowed:
		return []
	filters = {"client": ["in", list(allowed)]}
	if status:
		filters["status"] = status
	if period:
		filters["period"] = period
	rows = frappe.get_all("Monthly Report", filters=filters, fields=SUMMARY_FIELDS, order_by="period desc, modified desc", limit=500)
	clients = dict(frappe.get_all("Client Business", filters={"name": ["in", list({r.client for r in rows}) or [""]]},
	                              fields=["name", "business_name"], as_list=True))
	for r in rows:
		r["client_name"] = clients.get(r.client)
	return rows


@frappe.whitelist(methods=["GET"])
def get(report: str):
	doc, _access = _get(report, READ)
	return serialize(doc, full=True)


@frappe.whitelist(methods=["POST"])
def prepare(client: str, period: str, accountant_notes: str | None = None):
	"""Create (or refresh a draft of) the report for a period from live ERPNext data."""
	access = authz.require_client_access(client, WRITE)
	authz.require_module(access, "core_accounting")
	start, end = period_bounds(period)
	existing = frappe.db.get_value("Monthly Report", {"client": client, "firm": access.firm, "period": period}, "name")
	doc = frappe.get_doc("Monthly Report", existing) if existing else frappe.new_doc("Monthly Report")
	if existing and doc.status not in ("Draft", "Withdrawn"):
		frappe.throw(_("The {0} report is {1}; withdraw it before preparing it again").format(period, doc.status))

	pack = broker.call(client, "reports.monthly_pack", {"from_date": str(start), "to_date": str(end)})
	if not pack["trial_balance_check"]["balanced"]:
		frappe.throw(_("The trial balance does not balance; resolve this before preparing the report"))

	doc.update(
		{
			"client": client,
			"firm": access.firm,
			"period": period,
			"from_date": start,
			"to_date": end,
			"status": "Draft",
			"prepared_by": frappe.session.user,
			"reviewed_by": None,
			"currency": pack.get("currency"),
			"total_income": pack["totals"]["total_income"],
			"total_expense": pack["totals"]["total_expense"],
			"net_profit": pack["totals"]["net_profit"],
			"trial_balance": json.dumps(pack["trial_balance"], default=str),
			"profit_and_loss": json.dumps(pack["profit_and_loss"], default=str),
			"balance_sheet": json.dumps(pack["balance_sheet"], default=str),
			"snapshot_taken_on": now_datetime(),
		}
	)
	if accountant_notes is not None:
		doc.accountant_notes = accountant_notes
	doc.save(ignore_permissions=True)
	audit.record("report.prepare", client=client, firm=access.firm, reference=("Monthly Report", doc.name), detail={"period": period})
	return serialize(doc)


@frappe.whitelist(methods=["POST"])
def submit_for_review(report: str, accountant_notes: str | None = None):
	doc, access = _get(report, WRITE)
	if doc.status != "Draft":
		frappe.throw(_("Only draft reports can be submitted for review"))
	if accountant_notes is not None:
		doc.accountant_notes = accountant_notes
	doc.status = "In Review"
	doc.save(ignore_permissions=True)
	audit.record("report.submit_for_review", client=doc.client, firm=doc.firm, reference=("Monthly Report", doc.name))
	return serialize(doc)


def _segregation_check(doc, firm):
	"""Reviewer must differ from preparer, except for single-person practices."""
	if doc.prepared_by == frappe.session.user:
		if frappe.db.get_value("Accounting Firm", firm, "firm_type") != "Independent Accountant":
			frappe.throw(_("A report must be reviewed by someone other than its preparer"))


@frappe.whitelist(methods=["POST"])
def approve(report: str, review_notes: str | None = None):
	doc, access = _get(report, REVIEW)
	if doc.status != "In Review":
		frappe.throw(_("Only reports in review can be approved"))
	_segregation_check(doc, access.firm)
	doc.status = "Approved"
	doc.reviewed_by = frappe.session.user
	doc.review_notes = review_notes
	doc.save(ignore_permissions=True)
	audit.record("report.approve", client=doc.client, firm=doc.firm, reference=("Monthly Report", doc.name))
	return serialize(doc)


@frappe.whitelist(methods=["POST"])
def request_changes(report: str, review_notes: str):
	doc, access = _get(report, REVIEW)
	if doc.status != "In Review":
		frappe.throw(_("Only reports in review can be sent back"))
	doc.status = "Draft"
	doc.review_notes = review_notes
	doc.save(ignore_permissions=True)
	audit.record("report.request_changes", client=doc.client, firm=doc.firm, reference=("Monthly Report", doc.name))
	return serialize(doc)


@frappe.whitelist(methods=["POST"])
def publish(report: str):
	doc, access = _get(report, LEAD)
	authz.require_module(access, "client_portal")
	if doc.status != "Approved":
		frappe.throw(_("Only approved reports can be published"))
	doc.status = "Published"
	doc.published_by = frappe.session.user
	doc.published_on = now_datetime()
	doc.save(ignore_permissions=True)
	audit.record("report.publish", client=doc.client, firm=doc.firm, reference=("Monthly Report", doc.name))
	return serialize(doc)


@frappe.whitelist(methods=["POST"])
def withdraw(report: str, reason: str | None = None):
	doc, access = _get(report, LEAD)
	if doc.status not in ("In Review", "Approved", "Published"):
		frappe.throw(_("Nothing to withdraw"))
	doc.status = "Withdrawn"
	doc.review_notes = "\n".join(filter(None, [doc.review_notes, f"Withdrawn: {reason or ''}"]))
	doc.save(ignore_permissions=True)
	audit.record("report.withdraw", client=doc.client, firm=doc.firm, reference=("Monthly Report", doc.name), detail={"reason": reason})
	return serialize(doc)
