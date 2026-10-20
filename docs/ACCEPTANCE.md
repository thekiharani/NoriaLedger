# Milestone 1 Acceptance Criteria — Evidence

| Criterion (spec §22) | Status | Evidence |
|---|---|---|
| Docker services start successfully | ✅ | `noria.sh up` waits for health checks; cold start 35.9 s; infra checks 22/22 |
| Frappe and ERPNext are operational | ✅ | Frappe 16.52.0 / ERPNext 16.51.1; ERPNext reports and postings exercised by tests |
| Noria Ledger installs successfully | ✅ | `create-hub` (noria_practice), provisioning (erpnext + noria_ledger) |
| Custom frontend authentication works | ✅ | Playwright login tests; E2E logins; CSRF enforced |
| An accounting firm can be created | ✅ | sign-up / `admin.create_firm`; E2E step 0 |
| Multiple client workspaces can be provisioned | ✅ | 4 demo + E2E clients via the provisioner; 100-site scaling run |
| Accountants have correctly restricted access | ✅ | hub tests (levels, assignments, deactivation, cross-firm), E2E steps 9 & 11 |
| Unrelated ERPNext modules are hidden from normal users | ✅ | normal users never get the desk (Website Users, edge allow-list); client-site desk workspaces hidden + module profile for operators |
| A journal entry can be posted | ✅ | ledger tests, E2E, UI |
| An invoice can be created and posted | ✅ | ledger tests, E2E step 3 |
| Payments can be recorded | ✅ | ledger tests, E2E step 3 |
| Trial balance and P&L reports work | ✅ | ledger tests (balance + GL consistency), E2E steps 6–7, UI |
| Client records are isolated | ✅ | separate DB per client; hub isolation tests; spoofed site header refused at the edge |
| A working client dashboard is available | ✅ | firm dashboard + client workspace overview (live ERPNext figures) + client portal |
| Core automated tests pass | ✅ | see TESTING.md |
| Production images are built successfully | ✅ | `noria.sh build` (backend + edge) |
| Actual image size and resource measurements are recorded | ✅ | OPTIMIZATION_REPORT.md, `measurements/` |
| Documentation accurately reflects implemented functionality | ✅ | docs/; gaps listed in KNOWN_LIMITATIONS.md |

Production readiness is **not** claimed. See DEPLOYMENT.md §6.
