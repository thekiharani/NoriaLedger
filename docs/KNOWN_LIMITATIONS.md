# Known Limitations and Roadmap

Status as of Milestone 1 (2026-10-20). "Implemented" items are covered by the tests in [TESTING.md](TESTING.md).

## Implemented in Milestone 1

* Multi-site Docker stack (hub + one ERPNext site per client), custom backend and edge images, provisioner.
* Firms (incl. independent accountants), members and roles, clients, engagements (multi-firm, explicit), assignments,
  onboarding checklist, offboarding (archive + backup), entitlements at firm and engagement level.
* Bookkeeping via ERPNext: chart of accounts, journals (draft/post/reverse/cancel), income/expense recording,
  customers/suppliers, sales invoices, bills, credit/debit notes, receipts/payments, tax templates.
* Banking: bank accounts, CSV and M-PESA CSV import with duplicate detection, ERPNext matching suggestions,
  reconciliation, categorisation, unreconciled dashboard figures.
* Reports from ERPNext: trial balance, P&L, balance sheet, cash flow, general ledger, AR/AP ageing, bank
  reconciliation statement; CSV export; browser print-to-PDF.
* Monthly management report workflow with internal review, segregation of duties, publication and client approval.
* Practice management: recurring task templates (monthly/quarterly/annual, statutory with verification notes), work
  queue, review step, workload view.
* Documents: requests, uploads (firm + client), review, secure logged downloads, stored per client site.
* Client portal: status, published reports, document requests/uploads, messages, report approval.
* Audit trails on the hub and the client sites; encrypted backups; verified restore.

## Not implemented (roadmap, in suggested order)

| Area | Gap | Notes |
|---|---|---|
| Firm billing | No invoicing of firm fees (retainers only recorded on engagements and summed on the dashboard) | Plan: a dedicated **firm site** per accounting firm (ERPNext) so firm billing uses the same engine but stays separate from client books |
| Timesheets & engagement profitability | missing | depends on firm billing |
| Opening balances wizard | journals can record them; no guided import | — |
| Period closing | ERPNext Period Closing Voucher not exposed; no accounting-period locking UI | high priority for year-end |
| Approval workflow for postings | drafts can be posted by Accountant level; no Frappe Workflow states (review/approve) on vouchers | the monthly-report review exists |
| Accounting dimensions / cost centres in UI | ERPNext supports them; Noria UI does not expose them | — |
| Period comparisons, expense analysis, tax summaries | not in UI | ERPNext reports exist |
| Server-side PDF / Excel exports | only CSV + browser print | v16 renders PDF with Chromium; add a report-pack PDF |
| Bank formats | generic CSV + one M-PESA CSV layout; no PDF statements, no OFX/MT940 | parsers are pluggable |
| M-PESA layout validation | needs real customer exports | see KENYA_COMPLIANCE.md |
| eTIMS, Daraja payments, KRA filing | not implemented (no specifications/credentials) | see KENYA_COMPLIANCE.md |
| Payroll (HRMS) | entitlement only | — |
| AI assistance | entitlement only | human-in-the-loop design in ARCHITECTURE.md |
| Notifications | no email/SMS on task assignment, document requests or published reports | needs SMTP config |
| S3-compatible document storage | files are on the sites volume | Frappe S3 apps or a storage abstraction |
| Central identity (OIDC) | hub-brokered sessions only | an OIDC provider can front the hub later |
| Template-based provisioning | standard provisioning takes ~130 s per client; cloning from a pre-installed template measured ~16 s per site | needs a "pre-setup-wizard" template + setup wizard to stay correct per client |
| Client ownership transfer between firms | additional engagements require a platform operator (`admin.grant_engagement`) | portal-owner-driven consent flow planned |
| Frontend bundle | vendor chunks split (app chunk 116 kB / 30 kB gzip; total ≈ 795 kB / 235 kB gzip) | route-level lazy loading would cut first-load size further |
| Accessibility audit | semantic HTML, labels, focus states, keyboard row navigation — no formal WCAG audit | — |

## Operational limitations

* Benchmarks were run on a 4 vCPU / 16 GB development VM, not production hardware.
* Image vulnerability scanning was not available in the build environment.
* The scheduler runs per-site jobs for every client site. With hundreds of sites, scheduled job volume grows
  linearly. Monitor the queue backlog (see OPTIMIZATION_REPORT.md).
* MariaDB 11.8 `innodb_snapshot_isolation` stays on. Watch for error 1020 under load (TECHNICAL_AUDIT §3).

## Decisions still open for the business

1. Licensing of the Noria apps if they are ever distributed (TECHNICAL_AUDIT §5).
2. Redis license option (RSAL/SSPL/AGPL) or a switch to Valkey.
3. Hosting region and data-protection roles (controller vs processor) for ODPC registration.
4. Commercial plans that map to the module entitlements.
