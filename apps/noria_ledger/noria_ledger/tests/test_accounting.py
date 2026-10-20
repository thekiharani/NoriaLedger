"""Ledger-integrity tests for the Noria service API.

Run ONLY on a disposable test client site (site config `noria_test_site: 1`),
created by `noria.sh test ledger`. They post real ERPNext documents.
"""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase

from noria_ledger.api import banking, invoices, journals, payments, reports
from noria_ledger.importers import get_parser
from noria_ledger.importers.base import StatementError
from noria_ledger.service import get_company


def acct(name_fragment: str, **filters) -> str:
	company = get_company()
	rows = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "account_name": ["like", f"%{name_fragment}%"], **filters},
		pluck="name",
	)
	assert rows, f"no account like {name_fragment}"
	return rows[0]


def gl_for(voucher_type: str, voucher_no: str):
	return frappe.get_all(
		"GL Entry",
		filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
		fields=["account", "debit", "credit"],
	)


def assert_balanced(testcase, voucher_type, voucher_no):
	rows = gl_for(voucher_type, voucher_no)
	testcase.assertTrue(rows, f"no GL rows for {voucher_no}")
	debit = sum(Decimal(str(r.debit)) for r in rows)
	credit = sum(Decimal(str(r.credit)) for r in rows)
	testcase.assertEqual(debit, credit, f"{voucher_no} unbalanced: {debit} != {credit}")
	return rows


class NoriaLedgerTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.conf.get("noria_test_site"):
			raise RuntimeError("Refusing to run ledger tests on a site without noria_test_site=1")
		frappe.set_user("Administrator")
		frappe.flags.noria_acting_user = "tester@noria.test"
		cls.cash = acct("Cash", account_type="Cash")
		cls.sales = acct("Sales", root_type="Income")
		cls.admin_exp = acct("Administrative", root_type="Expense")
		cls.date = frappe.utils.nowdate()
		for party_type, field, name in (("Customer", "customer_name", "Test Customer NL"), ("Supplier", "supplier_name", "Test Supplier NL")):
			if not frappe.db.exists(party_type, name):
				doc = frappe.new_doc(party_type)
				doc.set(field, name)
				doc.insert()
		cls.customer = "Test Customer NL"
		cls.supplier = "Test Supplier NL"


class TestJournals(NoriaLedgerTestCase):
	def test_balanced_journal_posts_balanced_gl(self):
		res = journals.create(
			posting_date=self.date,
			lines=[{"account": self.cash, "debit": "1500.10"}, {"account": self.sales, "credit": "1500.10"}],
			submit=True,
		)
		self.assertEqual(res["docstatus"], 1)
		rows = assert_balanced(self, "Journal Entry", res["name"])
		self.assertEqual(Decimal(str(sum(r.debit for r in rows))), Decimal("1500.10"))
		self.assertEqual(frappe.db.get_value("Journal Entry", res["name"], "noria_acting_user"), "tester@noria.test")

	def test_unbalanced_journal_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			journals.create(
				posting_date=self.date,
				lines=[{"account": self.cash, "debit": "100.00"}, {"account": self.sales, "credit": "99.99"}],
			)

	def test_more_than_two_decimals_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			journals.create(
				posting_date=self.date,
				lines=[{"account": self.cash, "debit": "10.005"}, {"account": self.sales, "credit": "10.005"}],
			)

	def test_line_with_both_debit_and_credit_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			journals.create(
				posting_date=self.date,
				lines=[{"account": self.cash, "debit": "5", "credit": "5"}, {"account": self.sales, "credit": "0"}],
			)

	def test_group_account_rejected(self):
		group = frappe.db.get_value("Account", {"company": get_company(), "is_group": 1, "root_type": "Asset"}, "name")
		with self.assertRaises(frappe.ValidationError):
			journals.create(posting_date=self.date, lines=[{"account": group, "debit": "1"}, {"account": self.sales, "credit": "1"}])

	def test_reversal_nets_to_zero(self):
		orig = journals.create(
			posting_date=self.date,
			lines=[{"account": self.admin_exp, "debit": "320.00"}, {"account": self.cash, "credit": "320.00"}],
			submit=True,
		)
		before = self._balance(self.admin_exp)
		rev = journals.reverse(name=orig["name"], posting_date=self.date)
		assert_balanced(self, "Journal Entry", rev["name"])
		self.assertEqual(frappe.db.get_value("Journal Entry", rev["name"], "reversal_of"), orig["name"])
		self.assertEqual(self._balance(self.admin_exp), before - Decimal("320.00"))
		# The original posting is untouched (immutable history).
		self.assertEqual(frappe.db.get_value("Journal Entry", orig["name"], "docstatus"), 1)

	def test_idempotency_key_prevents_duplicates(self):
		args = dict(
			posting_date=self.date,
			lines=[{"account": self.cash, "debit": "42.00"}, {"account": self.sales, "credit": "42.00"}],
			submit=True,
			idempotency_key="test-idem-1",
		)
		first = journals.create(**args)  # service wrapper records the key
		second = journals.create(**args)
		self.assertEqual(first["name"], second["name"])
		self.assertTrue(second.get("idempotent_replay"))

	def _balance(self, account):
		return Decimal(str(frappe.db.sql("select coalesce(sum(debit-credit),0) from `tabGL Entry` where account=%s and is_cancelled=0", account)[0][0]))


class TestInvoicesAndPayments(NoriaLedgerTestCase):
	def test_sales_invoice_posting_and_partial_payment(self):
		inv = invoices.create(
			kind="sales",
			party=self.customer,
			posting_date=self.date,
			items=[{"item_name": "Consulting", "qty": 2, "rate": "1250.50", "account": self.sales}],
			submit=True,
		)
		self.assertEqual(inv["grand_total"], 2501.0)
		rows = assert_balanced(self, "Sales Invoice", inv["name"])
		receivable = frappe.db.get_value("Sales Invoice", inv["name"], "debit_to")
		self.assertEqual(sum(r.debit for r in rows if r.account == receivable), 2501.0)

		pay = payments.pay_invoice(kind="sales", invoice=inv["name"], account=self.cash, posting_date=self.date, amount="1000.00")
		assert_balanced(self, "Payment Entry", pay["name"])
		self.assertEqual(frappe.db.get_value("Sales Invoice", inv["name"], "outstanding_amount"), 1501.0)

		with self.assertRaises(frappe.ValidationError):
			payments.pay_invoice(kind="sales", invoice=inv["name"], account=self.cash, amount="2000.00")

	def test_credit_note_reverses_receivable(self):
		inv = invoices.create(kind="sales", party=self.customer, posting_date=self.date,
		                      items=[{"item_name": "Goods", "qty": 1, "rate": "800.00", "account": self.sales}], submit=True)
		cn = invoices.make_return(kind="sales", name=inv["name"], posting_date=self.date)
		self.assertEqual(cn["grand_total"], -800.0)
		assert_balanced(self, "Sales Invoice", cn["name"])
		self.assertEqual(frappe.db.get_value("Sales Invoice", inv["name"], "outstanding_amount"), 0.0)

	def test_purchase_invoice_and_payment(self):
		bill = invoices.create(kind="purchase", party=self.supplier, posting_date=self.date, bill_no="T-1",
		                       items=[{"item_name": "Stationery", "qty": 3, "rate": "100.00", "account": self.admin_exp}], submit=True)
		assert_balanced(self, "Purchase Invoice", bill["name"])
		pay = payments.pay_invoice(kind="purchase", invoice=bill["name"], account=self.cash, posting_date=self.date)
		assert_balanced(self, "Payment Entry", pay["name"])
		self.assertEqual(frappe.db.get_value("Purchase Invoice", bill["name"], "outstanding_amount"), 0.0)

	def test_income_account_enforced_on_sales_lines(self):
		with self.assertRaises(frappe.ValidationError):
			invoices.create(kind="sales", party=self.customer, posting_date=self.date,
			                items=[{"item_name": "Bad", "qty": 1, "rate": "1", "account": self.admin_exp}])


class TestBanking(NoriaLedgerTestCase):
	def test_generic_csv_parser_amount_forms(self):
		rows = get_parser("generic_csv")().parse("Date,Description,Amount\n01/02/2026,In,\"1,000.50\"\n02/02/2026,Out,(20.00)\n")
		self.assertEqual([(str(r.deposit), str(r.withdrawal)) for r in rows], [("1000.50", "0"), ("0", "20.00")])

	def test_mpesa_parser_skips_failed_and_uses_receipt(self):
		csv = (
			"Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance\n"
			"QAB1,2026-03-01 10:00:00,Payment,Completed,500.00,,500.00\n"
			"QAB2,2026-03-01 11:00:00,Payment,Failed,900.00,,500.00\n"
			"QAB3,2026-03-02 09:00:00,Pay Bill,Completed,,-200.00,300.00\n"
		)
		rows = get_parser("mpesa_csv")().parse(csv)
		self.assertEqual([r.transaction_id for r in rows], ["QAB1", "QAB3"])
		self.assertEqual(str(rows[1].withdrawal), "200.00")

	def test_non_mpesa_file_rejected(self):
		with self.assertRaises(StatementError):
			get_parser("mpesa_csv")().parse("Date,Amount\n2026-01-01,5\n")

	def test_import_dedup_and_reconcile(self):
		ba = banking.create_account(bank_name="Test Bank NL", account_name=f"Ops {frappe.generate_hash(length=5)}")
		inv = invoices.create(kind="sales", party=self.customer, posting_date=self.date,
		                      items=[{"item_name": "Svc", "qty": 1, "rate": "700.00", "account": self.sales}], submit=True)
		pe = payments.pay_invoice(kind="sales", invoice=inv["name"], account=ba["gl_account"], posting_date=self.date,
		                          reference_no="EFT-NL-1", reference_date=self.date)
		d = frappe.utils.getdate(self.date).strftime("%d/%m/%Y")
		csv = f"Date,Description,Reference,Money In,Money Out\n{d},EFT,EFT-NL-1,700.00,\n{d},Fee,,,15.00\n{d},Fee,,,15.00\n"
		first = banking.import_statement(bank_account=ba["name"], format="generic_csv", content=csv)
		self.assertEqual((first["created"], first["duplicates"]), (3, 0))  # two identical fees are both real
		again = banking.import_statement(bank_account=ba["name"], format="generic_csv", content=csv)
		self.assertEqual((again["created"], again["duplicates"]), (0, 3))

		txn = frappe.db.get_value("Bank Transaction", {"bank_account": ba["name"], "reference_number": "EFT-NL-1"}, "name")
		suggestions = banking.suggestions(bank_transaction=txn)
		self.assertIn(pe["name"], [s["name"] for s in suggestions])
		res = banking.reconcile(bank_transaction=txn, vouchers=[{"payment_doctype": "Payment Entry", "payment_name": pe["name"], "amount": 700}])
		self.assertEqual(res["status"], "Reconciled")

		fee = frappe.get_all("Bank Transaction", filters={"bank_account": ba["name"], "withdrawal": 15}, pluck="name")[0]
		cat = banking.categorize(bank_transaction=fee, account=self.admin_exp)
		self.assertEqual(cat["status"], "Reconciled")


class TestReports(NoriaLedgerTestCase):
	def test_trial_balance_balances_and_pl_matches_gl(self):
		journals.create(posting_date=self.date, lines=[{"account": self.cash, "debit": "999.00"}, {"account": self.sales, "credit": "999.00"}], submit=True)
		start = frappe.utils.get_first_day(self.date)
		end = frappe.utils.get_last_day(self.date)
		pack = reports.monthly_pack(from_date=str(start), to_date=str(end))
		self.assertTrue(pack["trial_balance_check"]["balanced"])

		gl = frappe.qb.DocType("GL Entry")
		acc = frappe.qb.DocType("Account")
		Sum = frappe.query_builder.functions.Sum
		income = frappe.qb.from_(gl).join(acc).on(gl.account == acc.name).select(Sum(gl.credit) - Sum(gl.debit)).where(
			(acc.root_type == "Income") & (gl.is_cancelled == 0) & (gl.posting_date[start:end]) & (gl.company == get_company())
		).run()[0][0]
		self.assertAlmostEqual(pack["totals"]["total_income"], float(income or 0), places=2)

	def test_disallowed_report_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			reports.run_report("Stock Ledger", self.date, self.date)


class TestServiceAuthorization(IntegrationTestCase):
	def test_non_service_user_denied(self):
		from noria_ledger.api import company

		email = "plain-user@noria.test"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Plain", "user_type": "Website User"}).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				company.overview()
		finally:
			frappe.set_user("Administrator")
