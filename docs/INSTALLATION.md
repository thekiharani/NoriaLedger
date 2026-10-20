# Installation — Local Development

Tested on Linux x86_64 (Docker 29.9, 4 vCPU, 16 GB RAM). All images are multi-arch, so macOS on Apple silicon
works with Docker Desktop. Recommended resources: 4 CPUs, 8 GB RAM for Docker, and 15 GB of disk (each client
site uses about 100 MB of database).

## Prerequisites

* Docker Engine 24+ with Compose v2 and BuildKit
* Bash, `openssl`, `curl`, Python 3.10+ (for E2E/perf scripts)
* Bun 1.2+ (only for frontend hot-reload development)

## First run

```bash
cp .env.example .env                 # development settings
./infrastructure/scripts/noria.sh init-secrets   # secrets/db_root_password, hub_admin_password, demo_password
./infrastructure/scripts/noria.sh build          # backend + edge images
./infrastructure/scripts/noria.sh up             # starts and waits for health checks
./infrastructure/scripts/noria.sh create-hub     # hub site (~45 s), idempotent
./infrastructure/scripts/noria.sh seed           # demo firms + 4 provisioned client sites (~10 min)
```

Open <http://localhost:8080>. All demo users share the password in `secrets/demo_password`:

| User | Role |
|---|---|
| `amina@wanjiru.demo` | Firm Admin, Wanjiru & Associates (3 clients) |
| `brian@wanjiru.demo`, `cate@wanjiru.demo` | Accountants (assigned clients only) |
| `david@wanjiru.demo` | Reviewer |
| `esther@wanjiru.demo` | Staff (no client assignments → sees no clients) |
| `peter@otieno.demo` | Independent accountant (1 client) |
| `owner@savanna.demo`, `finance@kilele.demo`, `mama@mboga.demo` | Client portal users |

Operator desk (Frappe UI, System Managers only) is bound to <http://127.0.0.1:8081>. Log in as Administrator
with `secrets/hub_admin_password`, using `Host: hub.noria.localhost`. Add `127.0.0.1 hub.noria.localhost` to
`/etc/hosts` to reach it in a browser.

### Behind a TLS-intercepting proxy

If image builds fail with certificate errors, set `NORIA_BUILD_EXTRA_CA=/path/to/ca.pem` in `.env`. It is passed
as a BuildKit secret and never stored in the image. If Docker Hub rate-limits pulls, set
`UPSTREAM_REGISTRY=mirror.gcr.io`; images are pinned by digest, so the content is identical.

## Day-to-day commands

| Task | Command |
|---|---|
| Start / stop | `noria.sh up` / `noria.sh down` |
| Status / logs | `noria.sh ps` / `noria.sh logs backend` |
| Python changes | picked up live: `apps/*` are bind-mounted and gunicorn runs with `--reload`. Restart workers after changing job code: `noria.sh compose restart queue-short queue-long provisioner` |
| DocType / hook changes | `noria.sh migrate` |
| Frontend hot reload | `cd frontend && bun install && bun run dev` → <http://localhost:5173> (proxies `/api` to the edge) |
| Rebuild images | `noria.sh build && noria.sh up` |
| Shell / bench | `noria.sh shell`, `noria.sh bench --site hub.noria.localhost console` |
| Tests | see [TESTING.md](TESTING.md) |
| Backups | `noria.sh backup [site|all]` |
| Reset (destructive) | `noria.sh reset` — refuses when `NORIA_ENV=production` and asks for confirmation |

## Repository layout

```
apps/noria_practice/     hub app (Frappe app layout)
apps/noria_ledger/       client-site app (Frappe app layout)
frontend/                React SPA (+ e2e Playwright specs)
infrastructure/docker/   backend.Dockerfile, edge.Dockerfile
infrastructure/compose/  compose.yaml (+ dev / prod overrides)
infrastructure/caddy/    Caddyfile (public edge)
infrastructure/scripts/  noria.sh (all operations)
tests/e2e, tests/infra, tests/perf
docs/                    this documentation
measurements/            recorded measurement outputs
```
