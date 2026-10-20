# Production Image & Runtime Optimization Report

All figures were **measured** on 2026-10-20. Raw outputs are in `measurements/`.

**Environment:** cloud VM, 4 vCPU, 15.7 GiB RAM, Linux 6.18, Docker 29.9.1 (containerd snapshotter); stack in
`NORIA_ENV=staging` mode (production compose override, images baked, no auto-reload); gunicorn 2 workers × 4
threads for each of `backend` and `backend-ledger`. The load generator ran **on the same VM**, so throughput
ceilings are pessimistic. Re-run on production hardware before capacity planning.

## 1. Images

| Image | Compressed (registry content) | Uncompressed (on disk) | Noria-owned layers |
|---|---|---|---|
| `noria-ledger/backend` | **972 MB** | 4.39 GB | 3 layers, ≈ 1.5 MB (apps 0.76 MB + .pth/asset links) |
| upstream `frappe/erpnext:v16.51.1` (base) | 986 MB (multi-arch index incl. attestations) | 4.40 GB | — |
| `noria-ledger/edge` | **25.1 MB** | 93.9 MB | SPA 0.82 MB + Caddyfile |
| `mariadb:11.8` / `redis:8.10-trixie` | 108 MB / 57.6 MB | 458 MB / 213 MB | — |

* The 700 MB–1 GB compressed target for the backend is **met (972 MB)**, without removing anything from upstream.
* Where the space goes (measured inside the image): `apps/` 1.0 GB (of which `frappe/node_modules` 390 MB),
  Python venv 718 MB (largest: pyarrow 152 MB, google-api-client 93 MB, typst 77 MB, duckdb 56 MB),
  `/usr` 1.2 GB (Chromium headless shell 289 MB, used for PDF rendering), Node via nvm 217 MB.
* **Why no further reduction:** layers are additive, so deleting upstream files in our layer would not shrink the image.
  Real savings (pruning `node_modules` to runtime deps, dropping unused Python extras) need a full custom bench build.
  That would give up byte-identical upstream layers (supportability, cache sharing) and risk PDF/socket.io/report
  features. Not worth it at 972 MB. Candidates if ever needed, with their risk:
  prune `frappe/node_modules` to production deps (~300 MB, risk: socketio/build tooling);
  remove Chromium (289 MB, breaks v16 PDF).
* Build time: backend ≈ 1 s on a warm cache (no network); edge ≈ 20 s.
* Optimization rules applied: multi-stage edge build with no Bun/Node at runtime; `.dockerignore`; pinned digests; no
  package installs at startup; same backend image for all Frappe services; non-root runtime (`frappe`,
  uid 1000; Caddy official image); no test data in images.

## 2. Startup

| Measurement | Result |
|---|---|
| Cold start (existing volumes) `noria.sh up` → all health checks green | **35.9 s** |
| First API response after healthy | 0.03 s |
| New client site, standard provisioning (new-site + setup wizard + service user) | **~131 s** (E2E run), 97 s new-site + 25 s bootstrap measured separately |
| New site cloned from a template (`--source-sql`), benchmark tooling only | **15.7–16.0 s mean** over 90 sites |
| `bench migrate` with no pending changes, per client site | 7.4–9.2 s |

## 3. Idle resources by fleet size (production mode)

| Container | 10 client sites | 50 client sites | 100 client sites |
|---|---|---|---|
| db (MariaDB) | 374 MiB | 688 MiB¹ | 905 MiB¹ / 733 MiB² |
| backend (hub pool) | 227 MiB | 249 MiB | 278 MiB |
| backend-ledger (client-site pool) | 321 MiB | 546 MiB¹ | 714 MiB¹ |
| queue-short / queue-long / scheduler | 69 / 68 / 114 MiB | 71 / 72 / 115 MiB | 71 / 80 / 117 MiB |
| redis-cache / redis-queue | 15 / 8 MiB | 47 / 7 MiB | 148 / 8 MiB |
| websocket / edge / admin nginx | 24 / 16 / 5 MiB | 24 / 16 / 5 MiB | 23 / 18 / 5 MiB |
| **Total (approx.)** | **≈ 1.4 GiB** | **≈ 1.9 GiB** | **≈ 2.5 GiB** |
| DB on disk / tables | 1.3 GB / 7,912 | 5.3 GB / 38,432 | **11 GB / 76,582** |

¹ after a load run that touched every site (per-site metadata caches in gunicorn and Redis grow with the number of
*active* sites). ² with table caches = 20,000. Directly after bulk-creating 50/100 sites, MariaDB showed 1.83/1.87 GiB
(import residue in the buffer pool and dictionary); restarting brought it back to the values above.

**Per-site marginal cost:** ≈ 100–110 MB of database disk, ≈ 760 tables, and ≈ 4–5 MiB of worker/cache memory once a
site has been used. CPU at idle is ≈ 0 **unless the scheduler runs** (next section).

## 4. Scheduler load (important for capacity)

With the scheduler enabled on all 100 client sites, Frappe/ERPNext's own periodic jobs ran **835 jobs per 6 minutes**
(≈ 2.3 jobs/s). The two RQ workers averaged **61 % CPU each (peaks 98 %)** with no user traffic. The `default` queue
built a backlog of ~500 jobs per wave, draining at ~3 jobs/s, so each wave took about 3 minutes
(`measurements/scheduler-*.txt`). Implications:

* Background capacity, not web capacity, is the first limit as client count grows. Plan **≈ 1 worker process per
  ~50 active client sites** and scale `queue-short`/`queue-long` replicas (`docker compose up --scale`) as the fleet
  grows. Keep the user-facing `short` queue on dedicated workers so Noria's own jobs are not delayed by the backlog.
* Never disable ERPNext's scheduled jobs to save resources (overdue statuses, auto-repeat and depreciation depend on
  them).

**Defect found and fixed by this measurement:** new client sites ran **no scheduled jobs for ~2.5 hours** after
provisioning. Job types are created during `bench new-site` in Frappe's default time zone (Asia/Kolkata); the setup
wizard then switches to Africa/Nairobi, which leaves their timestamps in the future. Bootstrap now anchors never-run
jobs to "now" (`noria_ledger.provisioning.reset_scheduler_clock`), and the hub's time zone is set explicitly.

## 5. Request latency and throughput (through the edge)

`tests/perf/load.py`, 15 s per level, 4 logged-in demo users. "Ledger" scenarios are hub → `backend-ledger` →
ERPNext, with a random client per request (each user only targets clients it is authorised for).

**10 client sites** (`load-sites9.json` for hub scenarios, `load-ledger-sites9.json` for ledger scenarios):

| Scenario | c=1 p50 / p95 | c=5 rps | c=10 p50 / p95 / rps | c=25 p95 / rps | errors |
|---|---|---|---|---|---|
| Practice dashboard (hub only) | 14 / 18 ms | 168 | 56 / 92 ms / 167 | 172 ms / 174 | 0 |
| Client list (hub only) | 30 / 38 ms | 114 | 78 / 134 ms / 119 | 275 ms / 115 | 0 |
| Ledger overview (GL aggregates) | 33 / 41 ms | 80 | 102 / 170 ms / 92 | 413 ms / 90 | 0 |
| Journal list | 22 / 27 ms | 103 | 82 / 144 ms / 114 | 259 ms / 119 | 0 |
| Trial balance (ERPNext report) | 51 / 61 ms | 49 | 166 / 242 ms / 58 | 706 ms / 54 | 0 |
| Profit & loss (ERPNext report) | 46 / 56 ms | 58 | 149 / 213 ms / 65 | 580 ms / 66 | 0 |

The ledger-scenario rows in `load-sites9.json` show ~50 % errors. They are **invalid**: a benchmark bug sent requests
for clients those users may not access, and the hub correctly answered 403. They were re-measured in
`load-ledger-sites9.json`.

**50 and 100 client sites** (hub user sees ~46 / ~96 clients):

| Scenario | 50 sites c=1 p50/p95 | 50 sites c=10 p95 | 100 sites c=1 p50/p95 | 100 sites c=10 p95 / p99 |
|---|---|---|---|---|
| Dashboard | 17 / 22 ms | 92 ms | 19 / 26 ms | 100 / 126 ms |
| Client list | 162 / 192 ms → **15 / 20 ms after fix** | 449 → **109 ms** | 19 / 26 ms | 95 / 108 ms |
| Ledger overview | 33 / 57 ms | 183 ms | 38 / 60 ms | 170 / 217 ms |
| Trial balance | 75 / 330 ms | 337 ms | 95 / 340 ms | 352 / **1,009 ms** |
| Trial balance, table caches raised | — | — | **72 / 95 ms** | 319 / **371 ms** |

Interpretation:

* Saturation on this VM is ≈ 90–120 req/s for ledger operations and ≈ 170 req/s for hub-only pages, reached at
  concurrency ≈ 10. For accounting users (a few requests per minute each), that is roughly hundreds of concurrent
  users per VM. Validate on target hardware.
* Latency is largely independent of fleet size for hub pages. Ledger p95/p99 grows when requests hop across many
  cold sites, which is MariaDB table-cache churn (next section).

## 6. Optimizations made (before → after, measured)

| Change | Why | Before | After |
|---|---|---|---|
| Separate `backend-ledger` gunicorn pool for hub → client-site calls | With one shared pool, hub threads waiting on broker calls starved the client-site requests: gunicorn timeouts under load | requests timed out (120 s) at c=25 | 0 errors at c=25 |
| Bulk entitlement lookup in client list (`authz.client_modules_bulk`) | N+1 queries (3 per client) | 162 ms p50 at 46 clients | 15 ms p50 |
| MariaDB table caches sized for the fleet (`table_open_cache`, `table_definition_cache` 10,000, `open_files_limit` 65,535) | 76k tables vs. a 2,000-entry cache: 80k table opens within minutes | TB p95 340 ms, p99 1,009 ms (100 sites) | TB p95 95 ms, p99 371 ms; DB memory unchanged |
| Volatile `Client Business` fields written only by one deduplicated job | Snapshot-isolation conflicts (error 1020) under concurrency | request failures in seed | none observed |
| Cached per-client statistics (`stat_*`) for dashboards | Avoid calling every client site per page view | — | dashboard 19 ms p50 at 100 clients |
| Frontend vendor chunk split | Cacheable vendor code across releases | 1 × 772 kB JS | app chunk 116 kB (30 kB gzip) + vendor chunks |
| Edge: zstd/gzip compression, immutable asset caching | bandwidth | — | enabled |

Note: in this VM the container `nofile` limit is 20,000, so MariaDB capped `table_open_cache` at ≈ 9,835. On hosts
with Docker's usual limit (1,048,576) the configured 10,000 applies.

## 7. Recommended production starting configuration

| Fleet | VM | Settings |
|---|---|---|
| ≤ 25 clients | 4 vCPU / 8 GB | defaults |
| ~100 clients | 4–8 vCPU / 16 GB | `innodb_buffer_pool_size` 2–4 GB, table caches 10,000+, 2–3 replicas of each queue worker, `backend-ledger` 3 workers |
| 300+ clients | split DB to a dedicated server | table caches ≥ 30,000; more worker replicas or hosts; consider template-based provisioning |

Not measured yet: real data volumes per client (thousands of vouchers per month), MFA/login storms, backups of
100+ sites (duration and I/O), and multi-host deployments.
