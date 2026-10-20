# Testing

All results below were produced in this repository's stack on 2026-10-20. Commands are reproducible.

| Suite | Command | Scope | Result |
|---|---|---|---|
| Ledger integration (Frappe) | `noria.sh test ledger` | journals (balanced/unbalanced/decimals/group accounts), reversals, idempotency, sales & purchase invoices, partial payments, over-payment rejection, credit notes, bank import dedup + matching + reconciliation + categorisation, M-PESA/CSV parsers, TB balance and P&L ↔ GL consistency, report allow-list, service-only access | **18/18 pass** |
| Hub integration (Frappe) | `noria.sh test hub` | firm/client isolation, assignment levels, read-only, lead-only reversals, unknown ops, deactivation, last-admin protection, multi-firm engagement, portal isolation, messages, entitlements (firm + engagement), sign-up gating, monthly report review/segregation/publish/portal visibility, unbalanced TB refusal, recurring tasks (module- and fiscal-year-aware, idempotent), review flow, document request/upload/review, audit trail, guest access, bulk entitlement lookup | **30/30 pass** |
| End-to-end workflow | `python3 tests/e2e/test_accountant_workflow.py` | spec §18 steps 1–10 over HTTP through the edge on a freshly provisioned client, plus cross-firm isolation | **12/12 steps pass** (re-run on final code; `measurements/e2e-run.json`) |
| Infrastructure | `tests/infra/check_stack.sh` | container health, DB/Redis connectivity, short+long queue job execution, migrations, edge routing/allow-list, encrypted backup → restore with GL checksum + private files comparison | **22/22 pass** |
| UI (Playwright) | `cd frontend && NORIA_DEMO_PASSWORD=… bunx playwright test` | login, dashboard, clients, client workspace tabs, P&L run, cross-firm denial, portal published report and redirect | **3/3 pass** |
| Frontend unit (Vitest) | `cd frontend && bun run test` | exact cents arithmetic, periods, CSV formula-injection escaping | **5/5 pass** |
| Typecheck / build | `cd frontend && bun run build` | TS strict + production bundle | pass |

Notes:

* Ledger tests post real ERPNext documents and refuse to run unless the site has `noria_test_site: 1`.
  `noria.sh test ledger` creates the disposable `ledger-test.<suffix>` site for this purpose.
* Hub tests roll back per test class; the hub's demo data was verified unchanged after a run.
* E2E creates a new firm and client every run (signup is rate-limited to 5 per hour per IP).
* Not yet automated: MFA flow, load-based regression thresholds, upgrade (migrate) tests between two pinned
  upstream versions, period closing voucher, multi-currency.
