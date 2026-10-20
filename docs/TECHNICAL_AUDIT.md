# Technical Audit — Noria Ledger (Phase 1)

Date: 2026-10-20 · Scope: upstream selection, compatibility, licensing and the chosen architecture.
Every version below was pulled and run in this repository's stack; "verified" means exercised by the
automated tests listed in [TESTING.md](TESTING.md), not just read from documentation.

## 1. Workspace audit

The repository was empty (no commits) at the start. Everything here is new; there is no legacy code.

## 2. Confirmed upstream versions (pinned)

| Component | Version | Pin | Source | Status |
|---|---|---|---|---|
| Frappe Framework | **16.52.0** | inside the ERPNext image below | github.com/frappe/frappe tag `v16.52.0` | verified |
| ERPNext | **16.51.1** (latest v16 tag on 2026-10-20) | `frappe/erpnext:v16.51.1@sha256:85b63c68a1e7…ca27` | official image built by frappe_docker | verified |
| frappe_docker | `main` @ `df2a3b72` (2026-10-20) | used as the reference for compose/services | github.com/frappe/frappe_docker | reference only |
| Python / Node (in image) | 3.14.8 / 24.22.0 | from base image | — | verified |
| MariaDB | **11.8.9 LTS** | `mariadb:11.8@sha256:f16d7a34…34fa` | official image | verified |
| Redis | **8.10 (trixie)** — the requested image | `redis:8.10-trixie@sha256:2c2dff79…bfd6` | official image | verified |
| Caddy | 2.11.7 | `caddy:2.11-alpine@sha256:d8542f48…f75f` | official image | verified |
| Bun (build stage only) | 1.4 | `oven/bun:1.4-alpine@sha256:629e1741…2373` | official image | verified |
| Frappe HRMS | not installed | — | — | not required for Milestone 1 (payroll is a roadmap module) |

All images are multi-architecture (linux/amd64 + linux/arm64, verified with `docker buildx imagetools inspect`),
so Apple-silicon development runs natively. Digests are the multi-arch index digests; `UPSTREAM_REGISTRY`
lets a pull-through mirror (e.g. `mirror.gcr.io`) serve identical content.

Frontend libraries are locked in `frontend/bun.lock` (React 19, TanStack Router/Query/Table/Form, Tailwind 4,
Radix primitives, Zod 4). The newest major lines of TanStack Table (9), TypeScript (7) and Vite (8) were
deliberately **not** chosen; the selected lines (Table 8.21, TS 5.9, Vite 7) are stable and widely deployed.

## 3. Database decision

Preference order from the brief: PostgreSQL 18 → MariaDB 13 → a stable supported MariaDB.

* **PostgreSQL 18 — rejected.** Frappe's PostgreSQL support is beta; ERPNext v16 stable is supported only on
  MariaDB (no upstream CI on Postgres; community reports of query-syntax failures on v16). Ledgers,
  reconciliation and reports are exactly the areas most exposed to such gaps. Sources:
  [Is ERPNext officially supported with PostgreSQL?](https://discuss.frappe.io/t/is-erpnext-officially-supported-with-postgresql/163329),
  [Postgres support](https://discuss.frappe.io/t/postgres-support/162440).
* **MariaDB 13 — rejected.** The image exists, but 13.0 is a *rolling* (non-LTS) release that reaches end of life on
  2026-12-31 ([endoflife: MariaDB 13.0](https://endoflife.ai/mariadb/13.0)); unsuitable for financial production data.
* **MariaDB 11.8 LTS — chosen.** It is the version used by the official frappe_docker stack and offered on Frappe
  Cloud ([forum](https://discuss.frappe.io/t/mariadb-11-8-lts-option-on-frappe-cloud-vector-search-support/161088)).
  MariaDB 12.3 LTS (supported to 2029) is the next candidate once Frappe/ERPNext validate it.

**Finding — `innodb_snapshot_isolation`.** MariaDB 11.8 enables it by default. A long transaction that updates a row
changed by another committed transaction fails with error 1020 ("Record has changed since last read") instead of
silently overwriting. We hit this in our own code (a hub request updating `Client Business` while the stats job
updated the same row) and fixed it by giving volatile fields a single writer (`noria_practice.utils.touch_client`).
We keep the setting **on** (safer: no lost updates). Some community deployments turn it off; if ERPNext core ever shows
1020 errors under load, the trade-off must be re-evaluated deliberately, not by default.

## 4. Redis

`redis:8.10-trixie` exists for amd64/arm64 and works with Frappe's RQ workers and cache. Two instances, as in
frappe_docker: `redis-cache` (no persistence, `allkeys-lru`, bounded memory) and `redis-queue` (AOF persistence,
`noeviction`, also used for realtime pub/sub).

## 5. Licensing

| Component | License | Notes for Noria |
|---|---|---|
| Frappe Framework | MIT | — |
| ERPNext | GPL-3.0 | Running ERPNext as a hosted service does not trigger GPL source distribution. **Distributing** images or code that include ERPNext to third parties does. Noria apps import ERPNext modules (`noria_ledger`). See open question below. |
| frappe_docker | MIT | Compose structure derived from it. |
| MariaDB server | GPL-2.0 | Used unmodified as a separate service. |
| Redis 8 | Tri-license RSALv2 / SSPLv1 / AGPLv3 | Used unmodified as an internal backing service. Have legal confirm the chosen license option for a SaaS. Valkey (BSD) is a drop-in alternative if required. |
| Caddy | Apache-2.0 | — |
| React, TanStack, Tailwind, Radix, Zod, Sonner | MIT | — |
| lucide-react | ISC | — |
| Playwright (dev only) | Apache-2.0 | — |

**Open question for the business (not decided here):** the Noria apps are marked "Proprietary" in their package
metadata. That is compatible with operating them as a SaaS. If Noria ever ships the backend image or the apps to
customers or partners (on-premise installs, white-label), `noria_ledger` — which imports and extends GPL ERPNext —
would likely have to be offered under GPL-compatible terms. Obtain legal advice before any such distribution.

Upstream notices are preserved: the upstream images and apps are unmodified; nothing was removed from ERPNext.

## 6. Image build options evaluated

| Option | What it is | Verdict |
|---|---|---|
| Official image as-is | `frappe/erpnext` | Lacks our apps. |
| Official **layered** build (`images/layered/Containerfile`) | Rebuilds the whole bench (`bench init` + apps from git, via `APPS_JSON` secret) | Rebuilds Frappe/ERPNext every release; needs git access for private apps; same final size. |
| Official **custom** build (`images/custom`) | Full build from base OS | Most control, most maintenance. |
| **Thin layer on the pinned official image (chosen)** | `FROM frappe/erpnext:v16.51.1@sha256:…` + copy two apps, register them on the venv path (`.pth`), link assets | No network at build time, no tokens, upstream layers shared/cached in the registry, ~1.5 MB per release. |

The chosen approach keeps upstream byte-identical (easy upgrades: bump the pinned tag/digest and rebuild).
Private app sources come from the build context, so no repository tokens enter build args or image metadata.
The edge image is a true multi-stage build: Bun compiles the SPA, and the runtime is Caddy + static files only
(no Node/Bun in runtime).

## 7. Multi-site support (verified)

Frappe resolves the site per request from `Host` / `X-Frappe-Site-Name`; one backend image and one set of worker
processes serve all sites, each with its own database and `sites/<site>/` files. Verified with 1 hub + up to N client
sites in this stack (see [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md)). Background workers and the scheduler are
multi-site aware (jobs carry their site).

## 8. Chosen architecture (summary)

* **Tenancy:** one hub site (practice management, `noria_practice`) + **one Frappe site/database per client
  business** (`erpnext` + `noria_ledger`), all on shared infrastructure.
* **Authentication:** **hub-brokered** (decided with the product owner). Users have accounts only on the hub; the hub
  authorizes every request and calls the client site server-to-server with that site's service credentials,
  forwarding the acting user. No cross-site cookies; client sites are not routed by the public edge.
* **Apps:** two Frappe apps (decided with the product owner): `noria_practice` (hub) and `noria_ledger` (client sites).
* **ERPNext:** unmodified and authoritative for all accounting; reached only through its document controllers and
  report engine.

Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## 9. ERPNext accounting dependencies observed

* Setup wizard (`frappe.desk.page.setup_wizard.setup_wizard.setup_complete`) creates the company, fiscal year,
  chart of accounts and — for country Kenya — a `Kenya Tax` template (VAT 16 %) from ERPNext's
  `country_wise_tax.json`. That rate is upstream data, not Noria code, and must be verified per client.
* Invoices accept service lines without Item masters (item name + UOM + account).
* Credit notes default to `update_outstanding_for_self = 1` in v16 (standalone credit). Noria sets it to 0 when a
  note is raised against a specific invoice so the invoice's outstanding is reduced (covered by a test).
* Bank matching (`get_linked_payments`) only searches vouchers inside a supplied date range; Noria passes ±60 days.
* Creating the `Bank` master requires System Manager in ERPNext; Noria creates only that reference record with
  `ignore_permissions` instead of granting the service user System Manager.
