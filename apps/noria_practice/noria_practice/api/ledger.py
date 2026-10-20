"""Accounting operations on a client's books, brokered to its ERPNext site.

`OPERATIONS` is the complete allow-list: every operation names the client-site
endpoint, the minimum client access level and the required module. Anything not
listed cannot be reached from the frontend.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from noria_practice import audit, authz, broker
from noria_practice.constants import LEAD, READ, WRITE
from noria_practice.utils import touch_client

CORE = "core_accounting"
BANK = "bank_reconciliation"

# op: (client-site method, min level, module, is_write)
OPERATIONS = {
	"overview": ("company.overview", READ, CORE, False),
	"chart": ("accounts.chart", READ, CORE, False),
	"postable_accounts": ("accounts.postable", READ, CORE, False),
	"create_account": ("accounts.create", WRITE, CORE, True),
	"parties": ("parties.list_parties", READ, CORE, False),
	"create_party": ("parties.create", WRITE, CORE, True),
	"journals": ("journals.list_entries", READ, CORE, False),
	"journal": ("journals.get", READ, CORE, False),
	"create_journal": ("journals.create", WRITE, CORE, True),
	"record_simple": ("journals.record_simple", WRITE, CORE, True),
	"submit_journal": ("journals.submit", WRITE, CORE, True),
	"delete_draft_journal": ("journals.delete_draft", WRITE, CORE, True),
	# Reversals/cancellations of posted vouchers are controlled: lead level only.
	"reverse_journal": ("journals.reverse", LEAD, CORE, True),
	"cancel_journal": ("journals.cancel", LEAD, CORE, True),
	"invoices": ("invoices.list_invoices", READ, CORE, False),
	"invoice": ("invoices.get", READ, CORE, False),
	"create_invoice": ("invoices.create", WRITE, CORE, True),
	"submit_invoice": ("invoices.submit", WRITE, CORE, True),
	"make_return": ("invoices.make_return", WRITE, CORE, True),
	"cancel_invoice": ("invoices.cancel", LEAD, CORE, True),
	"tax_templates": ("invoices.tax_templates", READ, CORE, False),
	"pay_invoice": ("payments.pay_invoice", WRITE, CORE, True),
	"payments": ("payments.list_payments", READ, CORE, False),
	"cancel_payment": ("payments.cancel", LEAD, CORE, True),
	"bank_accounts": ("banking.accounts", READ, CORE, False),
	"create_bank_account": ("banking.create_account", WRITE, CORE, True),
	"statement_formats": ("banking.formats", READ, BANK, False),
	"import_statement": ("banking.import_statement", WRITE, BANK, True),
	"bank_transactions": ("banking.transactions", READ, BANK, False),
	"match_suggestions": ("banking.suggestions", READ, BANK, False),
	"reconcile": ("banking.reconcile", WRITE, BANK, True),
	"categorize": ("banking.categorize", WRITE, BANK, True),
	"report": ("reports.run", READ, CORE, False),
}

# Fields never echoed into the hub audit log (bulky or sensitive).
_AUDIT_SKIP = {"content", "lines", "items", "vouchers", "mapping"}


@frappe.whitelist(methods=["POST"])
def call(client: str, op: str, args: dict | str | None = None):
	if op not in OPERATIONS:
		frappe.throw(_("Unknown operation"), frappe.PermissionError)
	method, level, module, is_write = OPERATIONS[op]
	access = authz.require_client_access(client, level)
	authz.require_module(access, module)
	if frappe.db.get_value("Client Business", client, "status") in ("Archived", "Suspended") and is_write:
		frappe.throw(_("This client is not active; its books are read-only"))

	args = frappe.parse_json(args) if isinstance(args, str) else (args or {})
	if not isinstance(args, dict):
		frappe.throw(_("args must be an object"))
	args.pop("cmd", None)

	result = broker.call(client, method, args, acting_user=frappe.session.user)

	if is_write:
		touch_client(client)
		ref = (result.get("doctype"), result.get("name")) if isinstance(result, dict) else None
		audit.record(
			f"ledger.{op}",
			client=client,
			firm=access.firm,
			detail={
				"args": {k: v for k, v in args.items() if k not in _AUDIT_SKIP},
				"result": {"doctype": ref[0], "name": ref[1]} if ref else None,
			},
		)
	elif op == "report":
		audit.record("ledger.report", client=client, firm=access.firm, detail={"report": args.get("report")})
	return result


def refresh_client_stats(client: str, touched: bool = False):
	"""Cache headline figures on Client Business so firm dashboards scale to
	hundreds of clients without calling every client site per page view.
	Sole writer of the volatile fields (see utils.touch_client)."""
	values = {"last_activity": now_datetime()} if touched else {}
	try:
		ov = broker.call(client, "company.overview", {}, acting_user="system@noria")
	except Exception:
		frappe.log_error(title=f"Stats refresh failed: {client}")
		ov = None
	if ov is not None:
		values.update({
			"stat_unreconciled": ov.get("unreconciled_bank_transactions") or 0,
			"stat_drafts": ov.get("draft_documents") or 0,
			"stat_overdue_invoices": ov.get("overdue_sales_invoices") or 0,
			"stat_last_posting_date": ov.get("last_posting_date"),
			"stat_cash_and_bank": ov.get("cash_and_bank") or 0,
			"stat_receivables": ov.get("receivables") or 0,
			"stat_payables": ov.get("payables") or 0,
			"stat_updated_on": now_datetime(),
		})
	if values:
		frappe.db.set_value("Client Business", client, values, update_modified=False)


def refresh_all_client_stats():
	for client in frappe.get_all("Client Site", filters={"status": "Active"}, pluck="client"):
		refresh_client_stats(client)
		frappe.db.commit()
