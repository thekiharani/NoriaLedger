"""Hub tests: authorization, cross-tenant isolation, entitlements and workflows.

Client sites are not contacted: `noria_practice.broker.call` is mocked, and the
tests assert it is never reached when authorization or entitlements fail.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from noria_practice import authz
from noria_practice.api import clients, documents, firm, ledger, messages, monthly_reports, portal, session, tasks
from noria_practice.api.session import create_firm_with_admin
from noria_practice.constants import READ
from noria_practice.practice.tasks import generate_for_firm
from noria_practice.provisioning import client_site_name, company_abbr

PW = "Tst-" + frappe.generate_hash(length=16)
ALL = ("bank_reconciliation", "practice_management", "document_management", "client_portal", "advanced_reporting", "tax_compliance")

FAKE_PACK = {
	"trial_balance": {"report": "Trial Balance", "columns": [], "rows": []},
	"profit_and_loss": {"report": "Profit and Loss Statement", "columns": [], "rows": []},
	"balance_sheet": {"report": "Balance Sheet", "columns": [], "rows": []},
	"totals": {"total_income": 1000.0, "total_expense": 400.0, "net_profit": 600.0},
	"trial_balance_check": {"balanced": True, "closing_debit": 1.0, "closing_credit": 1.0},
	"currency": "KES",
}


def as_user(user):
	frappe.set_user(user)


class PracticeTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		tag = frappe.generate_hash(length=6)
		cls.tag = tag
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

		a = create_firm_with_admin(f"Alpha {tag}", "Accounting Firm", "Alice Admin", f"alice-{tag}@alpha.test", PW, modules=ALL)
		b = create_firm_with_admin(f"Beta {tag}", "Accounting Firm", "Bob Admin", f"bob-{tag}@beta.test", PW, modules=())
		cls.firm_a, cls.admin_a = a["firm"], a["user"]
		cls.firm_b, cls.admin_b = b["firm"], b["user"]

		as_user(cls.admin_a)
		cls.acct = f"acc-{tag}@alpha.test"
		cls.reviewer = f"rev-{tag}@alpha.test"
		cls.readonly = f"ro-{tag}@alpha.test"
		cls.unassigned = f"un-{tag}@alpha.test"
		firm.add_member(cls.firm_a, cls.acct, "Ann Accountant", "Accountant", password=PW)
		firm.add_member(cls.firm_a, cls.reviewer, "Rita Reviewer", "Reviewer", password=PW)
		firm.add_member(cls.firm_a, cls.readonly, "Remy Readonly", "Staff", password=PW)
		firm.add_member(cls.firm_a, cls.unassigned, "Uma Unassigned", "Accountant", password=PW)

		cls.client_a = clients.create(firm=cls.firm_a, business_name=f"Alpha Client {tag}", fiscal_year_start="2026-01-01",
		                              services=list(ALL), provision=False)["name"]
		cls.client_a2 = clients.create(firm=cls.firm_a, business_name=f"Alpha Second {tag}", fiscal_year_start="2026-07-01",
		                               services=["practice_management"], provision=False)["name"]
		clients.assign(cls.client_a, cls.acct, "Lead Accountant")
		clients.assign(cls.client_a, cls.reviewer, "Reviewer")
		clients.assign(cls.client_a, cls.readonly, "Read Only")
		cls.owner = f"owner-{tag}@client.test"
		clients.invite_portal_user(cls.client_a, cls.owner, "Olive Owner", "Owner", True, password=PW)

		as_user(cls.admin_b)
		cls.client_b = clients.create(firm=cls.firm_b, business_name=f"Beta Client {tag}", fiscal_year_start="2026-01-01",
		                              provision=False)["name"]
		frappe.set_user("Administrator")
		# Pretend sites exist so broker paths are reachable (the broker itself is mocked).
		for c in (cls.client_a, cls.client_a2, cls.client_b):
			frappe.db.set_value("Client Business", c, "provisioning_status", "Ready")

	def tearDown(self):
		frappe.set_user("Administrator")


class TestAuthorization(PracticeTestCase):
	def test_firm_admin_sees_only_own_firms_clients(self):
		as_user(self.admin_a)
		visible = {c["name"] for c in clients.list_clients()}
		self.assertIn(self.client_a, visible)
		self.assertIn(self.client_a2, visible)
		self.assertNotIn(self.client_b, visible)

	def test_cross_firm_access_denied(self):
		as_user(self.admin_b)
		with self.assertRaises(frappe.PermissionError):
			clients.get(self.client_a)
		with patch("noria_practice.broker.call") as call:
			with self.assertRaises(frappe.PermissionError):
				ledger.call(self.client_a, "overview")
			call.assert_not_called()

	def test_accountant_sees_only_assigned_clients(self):
		as_user(self.acct)
		self.assertEqual({c["name"] for c in clients.list_clients()}, {self.client_a})
		as_user(self.unassigned)
		self.assertEqual(clients.list_clients(), [])
		with self.assertRaises(frappe.PermissionError):
			authz.require_client_access(self.client_a, READ)

	def test_read_only_cannot_post(self):
		as_user(self.readonly)
		self.assertEqual(authz.require_client_access(self.client_a, READ).level, READ)
		with patch("noria_practice.broker.call") as call:
			with self.assertRaises(frappe.PermissionError):
				ledger.call(self.client_a, "create_journal", {"posting_date": "2026-09-01", "lines": []})
			call.assert_not_called()

	def test_reversal_requires_lead_level(self):
		as_user(self.reviewer)
		with patch("noria_practice.broker.call") as call:
			with self.assertRaises(frappe.PermissionError):
				ledger.call(self.client_a, "reverse_journal", {"name": "X"})
			call.assert_not_called()
		as_user(self.acct)  # Lead Accountant
		with patch("noria_practice.broker.call", return_value={"doctype": "Journal Entry", "name": "JV-1"}) as call:
			ledger.call(self.client_a, "reverse_journal", {"name": "X"})
			call.assert_called_once()
			self.assertEqual(call.call_args.kwargs["acting_user"], self.acct)

	def test_unknown_operation_rejected(self):
		as_user(self.admin_a)
		with self.assertRaises(frappe.PermissionError):
			ledger.call(self.client_a, "frappe.client.get_list", {})

	def test_deactivated_member_loses_access_immediately(self):
		as_user(self.admin_a)
		member = frappe.db.get_value("Firm Member", {"firm": self.firm_a, "user": self.unassigned}, "name")
		clients.assign(self.client_a, self.unassigned, "Accountant")
		as_user(self.unassigned)
		self.assertIsNotNone(authz.client_access(self.client_a))
		as_user(self.admin_a)
		firm.update_member(self.firm_a, member, status="Inactive")
		as_user(self.unassigned)
		self.assertIsNone(authz.client_access(self.client_a))

	def test_cannot_remove_last_firm_admin(self):
		as_user(self.admin_b)
		member = frappe.db.get_value("Firm Member", {"firm": self.firm_b, "user": self.admin_b}, "name")
		with self.assertRaises(frappe.ValidationError):
			firm.update_member(self.firm_b, member, firm_role="Accountant")

	def test_assign_requires_firm_membership(self):
		as_user(self.admin_a)
		with self.assertRaises(frappe.ValidationError):
			clients.assign(self.client_a, self.admin_b, "Accountant")

	def test_ended_engagement_revokes_access(self):
		as_user(self.admin_a)
		temp = clients.create(firm=self.firm_a, business_name=f"Temp {self.tag}", fiscal_year_start="2026-01-01", provision=False)["name"]
		self.assertIsNotNone(authz.client_access(temp))
		result = clients.archive(temp, reason="test")
		self.assertTrue(result["client_archived"])
		self.assertIsNone(authz.client_access(temp))

	def test_multi_firm_engagement_is_explicit(self):
		as_user(self.admin_b)
		self.assertIsNone(authz.client_access(self.client_a))
		as_user(self.admin_a)
		with self.assertRaises(frappe.PermissionError):
			from noria_practice.api import admin

			admin.grant_engagement(self.client_a, self.firm_b)
		frappe.set_user("Administrator")
		from noria_practice.api import admin

		admin.grant_engagement(self.client_a, self.firm_b)
		as_user(self.admin_b)
		self.assertEqual(authz.client_access(self.client_a).firm, self.firm_b)


class TestPortalIsolation(PracticeTestCase):
	def test_portal_user_limited_to_own_client(self):
		as_user(self.owner)
		self.assertEqual(clients.list_clients(), [])
		with self.assertRaises(frappe.PermissionError):
			clients.get(self.client_a)
		with self.assertRaises(frappe.PermissionError):
			portal.overview(self.client_b)
		overview = portal.overview(self.client_a)
		self.assertEqual(overview["client"], self.client_a)

	def test_portal_user_cannot_call_ledger(self):
		as_user(self.owner)
		with patch("noria_practice.broker.call") as call:
			with self.assertRaises(frappe.PermissionError):
				ledger.call(self.client_a, "overview")
			call.assert_not_called()

	def test_firm_staff_cannot_become_portal_users(self):
		as_user(self.admin_a)
		with self.assertRaises(frappe.ValidationError):
			clients.invite_portal_user(self.client_a, self.acct, "Ann", "Owner")

	def test_messages_both_sides(self):
		as_user(self.acct)
		messages.send(self.client_a, "Please send statements")
		as_user(self.owner)
		messages.send(self.client_a, "Sent!")
		sides = [m["sender_side"] for m in messages.list_messages(self.client_a)]
		self.assertEqual(sides[-2:], ["Firm", "Client"])
		with self.assertRaises(frappe.PermissionError):
			messages.list_messages(self.client_b)


class TestEntitlements(PracticeTestCase):
	def test_module_not_in_subscription_blocks_backend(self):
		# Firm B has only core accounting: bank reconciliation must be refused server-side.
		as_user(self.admin_b)
		with patch("noria_practice.broker.call") as call:
			with self.assertRaises(frappe.PermissionError):
				ledger.call(self.client_b, "import_statement", {"bank_account": "x", "format": "generic_csv", "content": ""})
			call.assert_not_called()
			ledger.call(self.client_b, "overview")  # core accounting allowed
			call.assert_called_once()

	def test_engagement_services_narrow_firm_modules(self):
		as_user(self.admin_a)
		modules = authz.client_modules(self.client_a2, self.firm_a)
		self.assertIn("practice_management", modules)
		self.assertIn("core_accounting", modules)
		self.assertNotIn("bank_reconciliation", modules)

	def test_bulk_modules_match_single_lookup(self):
		as_user(self.admin_a)
		pairs = [(self.client_a, self.firm_a), (self.client_a2, self.firm_a)]
		bulk = authz.client_modules_bulk(pairs)
		for client, firm in pairs:
			self.assertEqual(bulk[client], authz.client_modules(client, firm))

	def test_services_outside_subscription_rejected(self):
		as_user(self.admin_b)
		with self.assertRaises(frappe.ValidationError):
			clients.create(firm=self.firm_b, business_name="X", fiscal_year_start="2026-01-01", services=["client_portal"], provision=False)

	def test_signup_disabled_without_config(self):
		frappe.set_user("Guest")
		with patch.dict(frappe.local.conf, {"noria_allow_firm_signup": 0}):
			with self.assertRaises(frappe.PermissionError):
				session.signup_firm("F", "N", f"n-{self.tag}@x.test", PW)


class TestMonthlyReportWorkflow(PracticeTestCase):
	def test_prepare_review_publish_and_portal_visibility(self):
		as_user(self.acct)
		with patch("noria_practice.broker.call", return_value=FAKE_PACK) as call:
			rep = monthly_reports.prepare(self.client_a, "2026-09", accountant_notes="September")
			self.assertEqual(call.call_args.args[1], "reports.monthly_pack")
			self.assertEqual(call.call_args.args[2], {"from_date": "2026-09-01", "to_date": "2026-09-30"})
		self.assertEqual(rep["net_profit"], 600.0)
		monthly_reports.submit_for_review(rep["name"])

		# Preparer cannot approve own report (segregation of duties).
		with self.assertRaises(frappe.ValidationError):
			monthly_reports.approve(rep["name"])
		# Read-only staff cannot approve.
		as_user(self.readonly)
		with self.assertRaises(frappe.PermissionError):
			monthly_reports.approve(rep["name"])

		as_user(self.owner)
		self.assertEqual(portal.reports(self.client_a), [])
		with self.assertRaises(frappe.PermissionError):
			portal.report(rep["name"])

		as_user(self.reviewer)
		monthly_reports.approve(rep["name"], review_notes="ok")
		with self.assertRaises(frappe.PermissionError):  # publishing needs lead level
			monthly_reports.publish(rep["name"])
		as_user(self.acct)
		published = monthly_reports.publish(rep["name"])
		self.assertEqual(published["status"], "Published")

		as_user(self.owner)
		self.assertEqual([r.name for r in portal.reports(self.client_a)], [rep["name"]])
		data = portal.report(rep["name"])
		self.assertNotIn("review_notes", data)
		portal.acknowledge_report(rep["name"])
		self.assertEqual(frappe.db.get_value("Monthly Report", rep["name"], "client_acknowledged_by"), self.owner)

	def test_unbalanced_trial_balance_blocks_preparation(self):
		as_user(self.acct)
		bad = {**FAKE_PACK, "trial_balance_check": {"balanced": False}}
		with patch("noria_practice.broker.call", return_value=bad):
			with self.assertRaises(frappe.ValidationError):
				monthly_reports.prepare(self.client_a, "2026-08")

	def test_cross_firm_cannot_read_report(self):
		as_user(self.acct)
		with patch("noria_practice.broker.call", return_value=FAKE_PACK):
			rep = monthly_reports.prepare(self.client_a, "2026-07")
		as_user(self.admin_b)
		with self.assertRaises(frappe.PermissionError):
			monthly_reports.get(rep["name"])


class TestTasksAndDocuments(PracticeTestCase):
	def test_recurring_generation_respects_modules_and_is_idempotent(self):
		frappe.set_user("Administrator")
		created = generate_for_firm(self.firm_a, "2026-06")
		by_client = {}
		for name in created:
			t = frappe.get_doc("Practice Task", name)
			by_client.setdefault(t.client, set()).add(t.template)
		self.assertIn("Monthly Bank Reconciliation", by_client[self.client_a])
		self.assertIn("VAT Return", by_client[self.client_a])
		self.assertNotIn("Monthly Bank Reconciliation", by_client[self.client_a2])  # module not engaged
		# Fiscal year of client_a2 starts in July -> June is its year end.
		self.assertIn("Year-End Closing", by_client[self.client_a2])
		self.assertNotIn("Year-End Closing", by_client[self.client_a])
		self.assertEqual(generate_for_firm(self.firm_a, "2026-06"), [])
		lead_task = frappe.get_all("Practice Task", filters={"client": self.client_a, "period": "2026-06"}, pluck="assigned_to")
		self.assertTrue(all(u == self.acct for u in lead_task))

	def test_reviewed_task_needs_review_step(self):
		as_user(self.acct)
		t = tasks.create(self.client_a, "Close books", "Bookkeeping", reviewer=self.reviewer, assigned_to=self.acct)["name"]
		tasks.update(t, status="In Progress")
		with self.assertRaises(frappe.ValidationError):
			tasks.update(t, status="Done")
		tasks.update(t, status="In Review")
		as_user(self.reviewer)
		self.assertEqual(tasks.update(t, status="Done")["status"], "Done")

	def test_document_request_upload_review(self):
		as_user(self.acct)
		req = documents.create_request(self.client_a, "Bank statement", "Bank Statement", "2026-09")
		stored = {"name": "ND-1", "file_name": "s.csv", "content_type": "text/csv", "file_size": 3, "content_hash": "abc"}
		as_user(self.owner)
		with patch("noria_practice.broker.call", return_value=stored) as call:
			doc = portal.upload(self.client_a, "Statement", "s.csv", "YWJj", "Bank Statement", "2026-09", req["name"])
			self.assertEqual(call.call_args.args[1], "documents.upload")
		self.assertEqual(frappe.db.get_value("Document Request", req["name"], "status"), "Uploaded")
		as_user(self.acct)
		documents.review(doc["name"], "Accepted")
		self.assertEqual(frappe.db.get_value("Document Request", req["name"], "status"), "Accepted")
		as_user(self.admin_b)
		with self.assertRaises(frappe.PermissionError):
			documents.download(doc["name"])

	def test_audit_trail_records_actions(self):
		as_user(self.admin_a)
		clients.get(self.client_a)
		self.assertTrue(frappe.db.exists("Noria Audit Event", {"client": self.client_a, "action": "client.view", "user": self.admin_a}))


class TestProvisioningHelpers(IntegrationTestCase):
	def test_site_names_are_safe_and_unique_per_client(self):
		name = client_site_name("CLT-00042", "Mama Mboga & Sons (Kenya) Ltd!")
		self.assertTrue(name.startswith("mama-mboga-sons-kenya-ltd-clt-00042."))
		self.assertRegex(name, r"^[a-z0-9.-]+$")
		self.assertEqual(company_abbr("Savanna Coffee Roasters Ltd"), "SCRL")


class TestEdgeOfAuth(IntegrationTestCase):
	def test_guest_cannot_use_product_api(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.AuthenticationError):
				clients.list_clients()
		finally:
			frappe.set_user("Administrator")

	def test_hub_doctypes_not_readable_by_noria_users(self):
		frappe.set_user("Administrator")
		user = frappe.get_all("Has Role", filters={"role": "Noria Practice User", "parenttype": "User"}, pluck="parent", limit=1)
		if not user:
			self.skipTest("no practice users")
		frappe.set_user(user[0])
		try:
			self.assertFalse(frappe.has_permission("Client Business", "read"))
			self.assertFalse(frappe.has_permission("Client Site", "read"))
		finally:
			frappe.set_user("Administrator")

