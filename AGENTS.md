# AGENTS.md — working on Noria Ledger

## Non-negotiables
* Never modify, fork or delete ERPNext/Frappe code. Extend through `apps/noria_ledger` / `apps/noria_practice`.
* Never write ledger tables (GL Entry, Payment Ledger Entry, …) directly. Use ERPNext document controllers
  (insert/submit/cancel, `make_reverse_journal_entry`, `get_payment_entry`, bank reconciliation tool) and reports.
* Every hub endpoint must authorize via `noria_practice/authz.py` (`require_client_access`, `require_module`, …)
  before reading data or calling the broker. Menu visibility is never authorization.
* New accounting operations: add the client-site endpoint (`noria_ledger/api`, decorated with `service_endpoint`)
  **and** an entry in `noria_practice/api/ledger.py::OPERATIONS` with level + module. Write ops accept
  `idempotency_key`.
* Money: parse with `service.to_decimal` (≤ 2 dp); the frontend uses integer cents (`lib/format.ts`).
* Volatile `Client Business` fields (`last_activity`, `stat_*`) are written only by the stats job
  (`utils.touch_client`). Do not write them in requests (MariaDB snapshot-isolation conflicts).
* Do not hard-code tax rates or statutory deadlines; they belong in ERPNext templates or Task Templates.
* No secrets in code, `.env` or images. Use `secrets/` (git-ignored) or a secret manager.

## Commands
* Stack: `infrastructure/scripts/noria.sh {build|up|down|create-hub|migrate|seed|test|backup|logs}`
* Tests: `noria.sh test hub`, `noria.sh test ledger` (disposable site), `python3 tests/e2e/test_accountant_workflow.py`,
  `tests/infra/check_stack.sh`, `cd frontend && bun run test && bun run build`
* DocType changes: edit the JSON under `apps/<app>/<app>/<module>/doctype/…`, then `noria.sh migrate`.

## Layout
See README.md and docs/ARCHITECTURE.md.
