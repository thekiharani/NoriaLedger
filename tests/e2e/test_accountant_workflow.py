#!/usr/bin/env python3
"""End-to-end accountant workflow through the public edge (real stack, no mocks).

Steps (spec §18): create client -> configure chart of accounts -> record income
and expenses -> import a bank statement -> reconcile -> trial balance -> profit &
loss -> monthly report -> internal review -> publish to the client portal.

Requires: a running stack (noria.sh up), hub site with NORIA_ALLOW_FIRM_SIGNUP=1.
Only the Python standard library is used. A fresh firm and client are created on
every run (unique tag), so the script does not depend on demo data.

    python3 tests/e2e/test_accountant_workflow.py [--base-url http://localhost:8080]
"""

import argparse
import base64
import http.cookiejar
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

RESULTS: list[dict] = []


class Client:
	def __init__(self, base: str):
		self.base = base.rstrip("/")
		self.jar = http.cookiejar.CookieJar()
		self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
		self.csrf = None

	def _req(self, method, path, payload=None, expect_error=False):
		url = f"{self.base}/api/method/{path}"
		data = None
		headers = {"Accept": "application/json"}
		if method == "GET" and payload:
			url += "?" + urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in payload.items()})
		elif method == "POST":
			data = json.dumps(payload or {}).encode()
			headers["Content-Type"] = "application/json"
			if self.csrf:
				headers["X-Frappe-CSRF-Token"] = self.csrf
		req = urllib.request.Request(url, data=data, headers=headers, method=method)
		try:
			with self.opener.open(req, timeout=300) as resp:
				body = json.loads(resp.read() or b"{}")
				if expect_error:
					raise AssertionError(f"{path} unexpectedly succeeded")
				return body.get("message")
		except urllib.error.HTTPError as e:
			body = e.read()
			if expect_error:
				return e.code
			raise AssertionError(f"{method} {path} -> HTTP {e.code}: {body[:600]!r}") from None

	def login(self, user, pwd):
		self._req("POST", "login", {"usr": user, "pwd": pwd})
		boot = self._req("GET", "noria_practice.api.session.bootstrap")
		self.csrf = boot["csrf_token"]
		return boot

	def hub(self, method, payload=None, get=False, expect_error=False):
		return self._req("GET" if get else "POST", f"noria_practice.api.{method}", payload, expect_error)

	def ledger(self, client, op, **args):
		return self.hub("ledger.call", {"client": client, "op": op, "args": args})


def step(name):
	def deco(fn):
		def run(*a, **kw):
			t0 = time.time()
			try:
				out = fn(*a, **kw)
				RESULTS.append({"step": name, "ok": True, "seconds": round(time.time() - t0, 2)})
				print(f"  PASS  {name}  ({time.time() - t0:.1f}s)")
				return out
			except Exception as e:
				RESULTS.append({"step": name, "ok": False, "seconds": round(time.time() - t0, 2), "error": str(e)[:800]})
				print(f"  FAIL  {name}: {e}")
				raise
		return run
	return deco


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--base-url", default="http://localhost:8080")
	ap.add_argument("--results", default=None, help="write JSON results here")
	ap.add_argument("--provision-timeout", type=int, default=900)
	args = ap.parse_args()

	tag = secrets.token_hex(3)
	pwd = "E2e-" + secrets.token_urlsafe(18)
	admin_email, reviewer_email, owner_email = f"admin-{tag}@e2e.test", f"reviewer-{tag}@e2e.test", f"owner-{tag}@e2e-client.test"
	today = date.today()
	# Work in the previous month so the monthly report covers a closed period.
	first_this = today.replace(day=1)
	prev_end = date.fromordinal(first_this.toordinal() - 1)
	period = f"{prev_end.year:04d}-{prev_end.month:02d}"
	d = lambda day: f"{period}-{day:02d}"  # noqa: E731
	ctx: dict = {}
	admin = Client(args.base_url)

	print(f"E2E run {tag} against {args.base_url} (period {period})")

	@step("0. firm sign-up + login")
	def signup():
		admin.hub("session.signup_firm", {"firm_name": f"E2E Accountants {tag}", "full_name": "E2E Admin", "email": admin_email, "password": pwd})
		boot = admin.login(admin_email, pwd)
		ctx["firm"] = boot["firms"][0]["firm"]
		admin.hub("firm.add_member", {"firm": ctx["firm"], "email": reviewer_email, "full_name": "E2E Reviewer", "firm_role": "Reviewer", "password": pwd})

	@step("1. create client (isolated ERPNext site provisioned)")
	def create_client():
		res = admin.hub("clients.create", {
			"firm": ctx["firm"], "business_name": f"E2E Traders {tag}", "kra_pin": "P05" + str(secrets.randbelow(10**7)).zfill(7) + "Z",
			"fiscal_year_start": f"{prev_end.year}-01-01", "vat_registered": True,
			"services": ["bank_reconciliation", "practice_management", "document_management", "client_portal", "advanced_reporting"],
		})
		ctx["client"] = res["name"]
		deadline = time.time() + args.provision_timeout
		while time.time() < deadline:
			c = admin.hub("clients.get", {"client": ctx["client"]}, get=True)
			if c["provisioning_status"] == "Ready":
				ctx["provision_seconds"] = round(time.time() - (deadline - args.provision_timeout), 1)
				return
			if c["provisioning_status"] == "Failed":
				raise AssertionError(f"provisioning failed: {c.get('provisioning_error')}")
			time.sleep(5)
		raise AssertionError("provisioning timed out")

	@step("2. configure chart of accounts")
	def configure_coa():
		chart = admin.ledger(ctx["client"], "chart")["accounts"]
		indirect = next(a["name"] for a in chart if a["is_group"] and a["account_name"] == "Indirect Expenses")
		res = admin.ledger(ctx["client"], "create_account", parent_account=indirect, account_name="Internet and Data", account_number="5299")
		ctx["internet"] = res["name"]
		post = admin.ledger(ctx["client"], "postable_accounts")
		pick = lambda root, frag, at=None: next(a["name"] for a in post if a["root_type"] == root and frag in a["account_name"] and (at is None or a["account_type"] == at))  # noqa: E731
		ctx["sales"], ctx["cash"] = pick("Income", "Sales"), pick("Asset", "Cash", "Cash")
		assert ctx["internet"] in [a["name"] for a in post]

	@step("3. record income and expenses")
	def record():
		c = ctx["client"]
		admin.ledger(c, "create_party", party_type="Customer", party_name=f"Buyer {tag}")
		taxes = admin.ledger(c, "tax_templates", kind="sales")
		inv = admin.ledger(c, "create_invoice", kind="sales", party=f"Buyer {tag}", posting_date=d(3), due_date=d(28),
		                   taxes_and_charges=taxes[0]["name"] if taxes else None,
		                   items=[{"item_name": "Wholesale goods", "qty": 10, "rate": "1500.00", "account": ctx["sales"]}],
		                   submit=True, idempotency_key=f"e2e-{tag}-si")
		ctx["invoice"], ctx["invoice_total"] = inv["name"], inv["grand_total"]
		replay = admin.ledger(c, "create_invoice", kind="sales", party=f"Buyer {tag}", posting_date=d(3),
		                      items=[{"item_name": "dup", "qty": 1, "rate": "1"}], submit=True, idempotency_key=f"e2e-{tag}-si")
		assert replay["name"] == inv["name"] and replay.get("idempotent_replay"), "idempotent replay failed"
		admin.ledger(c, "record_simple", kind="expense", posting_date=d(5), amount="2999.00", cash_account=ctx["cash"],
		             category_account=ctx["internet"], description="Fibre internet", idempotency_key=f"e2e-{tag}-exp")
		bank = admin.ledger(c, "create_bank_account", bank_name=f"E2E Bank {tag}", account_name="Main", account_number="0011")
		ctx["bank_account"], ctx["bank_gl"] = bank["name"], bank["gl_account"]
		pay = admin.ledger(c, "pay_invoice", kind="sales", invoice=ctx["invoice"], account=ctx["bank_gl"], posting_date=d(12),
		                   reference_no=f"EFT-{tag}", reference_date=d(12), idempotency_key=f"e2e-{tag}-rcpt")
		ctx["receipt"] = pay["name"]

	@step("4. import bank statement")
	def import_statement():
		day = lambda n: f"{n:02d}/{prev_end.month:02d}/{prev_end.year}"  # noqa: E731
		csv = "\n".join([
			"Date,Description,Reference,Money In,Money Out",
			f"{day(12)},EFT Buyer {tag},EFT-{tag},\"{ctx['invoice_total']:,.2f}\",",
			f"{day(20)},Account maintenance fee,,,250.00",
		])
		res = admin.ledger(ctx["client"], "import_statement", bank_account=ctx["bank_account"], format="generic_csv",
		                   content=base64.b64encode(csv.encode()).decode(), encoding="base64", idempotency_key=f"e2e-{tag}-stmt")
		assert (res["created"], res["duplicates"]) == (2, 0), res
		again = admin.ledger(ctx["client"], "import_statement", bank_account=ctx["bank_account"], format="generic_csv",
		                     content=base64.b64encode(csv.encode()).decode(), encoding="base64")
		assert (again["created"], again["duplicates"]) == (0, 2), f"duplicate detection failed: {again}"

	@step("5. reconcile transactions")
	def reconcile():
		c = ctx["client"]
		lines = admin.ledger(c, "bank_transactions", bank_account=ctx["bank_account"], status="Unreconciled")
		receipt_line = next(t for t in lines if t["reference_number"] == f"EFT-{tag}")
		fee_line = next(t for t in lines if t["withdrawal"] == 250)
		sug = admin.ledger(c, "match_suggestions", bank_transaction=receipt_line["name"])
		assert ctx["receipt"] in [s["name"] for s in sug], f"receipt not suggested: {sug}"
		r = admin.ledger(c, "reconcile", bank_transaction=receipt_line["name"],
		                 vouchers=[{"payment_doctype": "Payment Entry", "payment_name": ctx["receipt"], "amount": ctx["invoice_total"]}])
		assert r["status"] == "Reconciled", r
		post = admin.ledger(c, "postable_accounts", root_type="Expense")
		charges = next(a["name"] for a in post if "Bank Charges" in a["account_name"] or "Administrative" in a["account_name"])
		r2 = admin.ledger(c, "categorize", bank_transaction=fee_line["name"], account=charges, remark="Bank fee")
		assert r2["status"] == "Reconciled", r2
		left = admin.ledger(c, "bank_transactions", bank_account=ctx["bank_account"], status="Unreconciled")
		assert left == [], left

	@step("6. trial balance")
	def trial_balance():
		tb = admin.ledger(ctx["client"], "report", report="Trial Balance", from_date=d(1), to_date=prev_end.isoformat())
		rows = [r for r in tb["rows"] if r.get("account") and not str(r["account"]).startswith("'")]
		dr = round(sum(float(r.get("closing_debit") or 0) for r in rows), 2)
		cr = round(sum(float(r.get("closing_credit") or 0) for r in rows), 2)
		assert dr == cr and dr > 0, f"trial balance not balanced: {dr} vs {cr}"
		ctx["tb_total"] = dr

	@step("7. profit and loss")
	def profit_and_loss():
		pl = admin.ledger(ctx["client"], "report", report="Profit and Loss Statement", from_date=d(1), to_date=prev_end.isoformat(),
		                  options={"periodicity": "Monthly"})
		income = next(r for r in pl["rows"] if str(r.get("account", "")).strip("'") in ("Total Income (Credit)",))
		assert round(float(income["total"]), 2) == 15000.00, f"income {income['total']} != 15000 (net of VAT)"
		ctx["pl_income"] = float(income["total"])

	@step("8. prepare monthly report")
	def prepare():
		rep = admin.hub("monthly_reports.prepare", {"client": ctx["client"], "period": period, "accountant_notes": "E2E close"})
		assert rep["total_income"] == 15000.0, rep
		assert round(rep["net_profit"], 2) == round(15000.0 - 2999.0 - 250.0, 2), rep
		ctx["report"] = rep["name"]

	@step("9. submit for internal review + approve")
	def review():
		admin.hub("monthly_reports.submit_for_review", {"report": ctx["report"]})
		code = admin.hub("monthly_reports.approve", {"report": ctx["report"]}, expect_error=True)
		assert code == 417, f"preparer self-approval should be refused, got {code}"
		reviewer = Client(args.base_url)
		reviewer.login(reviewer_email, pwd)
		code = reviewer.hub("ledger.call", {"client": ctx["client"], "op": "overview"}, expect_error=True)
		assert code == 403, f"unassigned reviewer must not reach the books (got {code})"
		admin.hub("clients.assign", {"client": ctx["client"], "user": reviewer_email, "assignment_role": "Reviewer"})
		rep = reviewer.hub("monthly_reports.approve", {"report": ctx["report"], "review_notes": "Looks right"})
		assert rep["status"] == "Approved", rep

	@step("10. publish to client portal + client approval")
	def publish():
		admin.hub("clients.invite_portal_user", {"client": ctx["client"], "email": owner_email, "full_name": "E2E Owner",
		                                         "contact_role": "Owner", "can_approve": True, "password": pwd})
		owner = Client(args.base_url)
		owner.login(owner_email, pwd)
		assert owner.hub("portal.reports", {"client": ctx["client"]}, get=True) == [], "draft visible on portal"
		rep = admin.hub("monthly_reports.publish", {"report": ctx["report"]})
		assert rep["status"] == "Published"
		published = owner.hub("portal.reports", {"client": ctx["client"]}, get=True)
		assert [r["name"] for r in published] == [ctx["report"]]
		owner.hub("portal.acknowledge_report", {"report": ctx["report"]})
		assert owner.hub("ledger.call", {"client": ctx["client"], "op": "overview"}, expect_error=True) == 403

	@step("11. isolation: another firm cannot see this client")
	def isolation():
		other = Client(args.base_url)
		other_email = f"other-{tag}@e2e.test"
		other.hub("session.signup_firm", {"firm_name": f"Other {tag}", "full_name": "Other", "email": other_email, "password": pwd})
		other.login(other_email, pwd)
		assert other.hub("clients.list_clients", get=True) == []
		assert other.hub("clients.get", {"client": ctx["client"]}, get=True, expect_error=True) == 403
		assert other.hub("ledger.call", {"client": ctx["client"], "op": "chart"}, expect_error=True) == 403
		anon = Client(args.base_url)
		assert anon._req("GET", "noria_ledger.api.company.overview", expect_error=True) == 404  # client-site API not routed

	ok = True
	try:
		for fn in (signup, create_client, configure_coa, record, import_statement, reconcile, trial_balance, profit_and_loss,
		           prepare, review, publish, isolation):
			fn()
	except Exception:
		ok = False
	summary = {"run": tag, "ok": ok, "client": ctx.get("client"), "provision_seconds": ctx.get("provision_seconds"),
	           "period": period, "steps": RESULTS}
	if args.results:
		with open(args.results, "w") as fh:
			json.dump(summary, fh, indent=2)
	print(("ALL STEPS PASSED" if ok else "E2E FAILED") + f" ({sum(r['ok'] for r in RESULTS)}/{len(RESULTS)})")
	return 0 if ok else 1


if __name__ == "__main__":
	sys.exit(main())
