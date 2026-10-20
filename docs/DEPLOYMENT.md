# Production Deployment, Upgrades and Rollback

> Passing the Milestone 1 acceptance tests does **not** make this production-ready. See the checklist in §6.

## 1. Topology (single host, the supported starting point)

One Linux VM (4 vCPU / 16 GB for tens of clients; see [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md)) runs the
Compose stack with `NORIA_ENV=production` (selects `compose.prod.yaml`: memory limits, scheduled backups).
Persistent volumes: `db-data`, `sites`, `logs`, `redis-queue-data`, `caddy-data`. For larger fleets, move MariaDB
to a managed or dedicated server (`db_host` in the configurator) and scale `backend-ledger` / workers horizontally
on additional hosts that share the `sites` volume (NFS or similar) — not yet exercised here.

## 2. Build and release

```bash
NORIA_TAG=2026.10.1 ./infrastructure/scripts/noria.sh build
docker tag noria-ledger/backend:2026.10.1 registry.example.com/noria/backend:2026.10.1
docker push registry.example.com/noria/backend:2026.10.1      # also the edge image
```

* Tags are immutable releases. Never deploy `latest`. Record the resulting digests in the release notes and
  deploy by digest.
* Upstream pins (ERPNext image digest, MariaDB, Redis, Caddy, Bun) change only through a reviewed commit.
* Scan images before release (`trivy image …`), see SECURITY.md.

## 3. First production install

```bash
# on the server, outside the repo checkout
cat > /etc/noria/production.env <<EOF
NORIA_ENV=production
COMPOSE_PROJECT_NAME=noria
NORIA_BACKEND_IMAGE=registry.example.com/noria/backend
NORIA_EDGE_IMAGE=registry.example.com/noria/edge
NORIA_TAG=2026.10.1
NORIA_PULL_POLICY=missing
NORIA_SITE_ADDRESS=ledger.example.co.ke      # Caddy obtains TLS certificates automatically
NORIA_HTTP_PORT=80
NORIA_HTTPS_PORT=443
NORIA_HUB_SITE=hub.ledger.internal
NORIA_CLIENT_SITE_SUFFIX=ledger.internal
NORIA_ALLOW_FIRM_SIGNUP=0
NORIA_SECRETS_DIR=/etc/noria/secrets          # db_root_password, hub_admin_password (0640, root:docker)
EOF
export NORIA_ENV_FILE=/etc/noria/production.env
noria.sh up && noria.sh create-hub
```

Then, as Administrator on the hub (desk on the loopback port, via SSH tunnel), configure outgoing email (invitations
and password resets), enable 2FA policy, and create firms via `noria_practice.api.admin.create_firm`.

## 4. Upgrades across many sites

A release can contain (a) new Noria code, (b) a new pinned Frappe/ERPNext version, or both. Each changes the
schema of **every** site, so treat it as a database migration across the fleet.

1. **Rehearse** on staging with a restored copy of production (`backup-cron` output): `noria.sh migrate`, then run
   `noria.sh test` (hub + ledger), the E2E script and the infra checks against staging.
2. **Announce a maintenance window.** Put the edge in maintenance (scale `edge` to a maintenance page) so no
   writes happen during migration.
3. **Back up every site** with files: `noria.sh backup all`. Copy the backups **and `sites/*/site_config.json`**
   (they contain the DB passwords and backup encryption keys) off-host.
4. **Deploy images** (change `NORIA_TAG`, `noria.sh up`). The configurator rewrites `apps.txt`; containers restart.
5. **Migrate:** `noria.sh migrate` runs `bench --site all migrate` sequentially. Measure the per-site time during
   rehearsal (OPTIMIZATION_REPORT records it). For large fleets, migrate the hub first, then client sites in
   batches. A failed site does not block the others; record it and retry.
6. **Verify:** infra checks + a smoke E2E on a test client; then reopen the edge.

## 5. Rollback

Switching back to the previous image is **not** a rollback once `migrate` has run: schemas and patch history have
moved forward. Rollback means:

1. Stop the stack (`noria.sh down`).
2. Restore every affected site from the pre-upgrade backups (database + public/private files, with each site's
   `backup_encryption_key`), see [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
3. Start the previous image tag.

Any data written after the backup is lost, which is why the maintenance window blocks writes. If only Noria app code
changed without schema changes, an image-only rollback is possible. Confirm this from the release notes; never
assume it.

## 6. Production readiness checklist

| Item | Status |
|---|---|
| Acceptance tests (hub, ledger, E2E, infra, UI) green | ✅ in this environment |
| HTTPS with automatic certificates | ✅ supported (needs a real domain) |
| Encrypted per-site backups + restore test | ✅ (infra checks) — off-site copy & retention: ❌ to configure |
| Secrets outside images / env files | ✅ Docker secrets |
| Outgoing email (invites, password reset, notifications) | ❌ configure SMTP on the hub |
| MFA policy and test | ❌ |
| Vulnerability scan of images | ❌ not run here |
| Monitoring & alerting (metrics, logs, error tracking) | ⚠️ Caddy metrics + JSON logs exist; no collector/alerts yet (see §7) |
| Load test at target fleet size on production hardware | ⚠️ measured on dev VM only |
| Independent penetration test | ❌ |
| DPA / ODPC registration, privacy notice | ❌ business/legal |
| eTIMS / payment integrations | ❌ not implemented |
| Upgrade rehearsal between two upstream versions | ❌ |

## 7. Observability (current state and plan)

* **Logs:** every container logs to `json-file` with rotation (20 MB × 5). Caddy logs are JSON. Frappe logs go to
  the `logs` volume. Plan: ship with Vector/Fluent Bit to Loki or a managed service.
* **Metrics:** Caddy exposes Prometheus metrics on the container's admin endpoint (`:2019/metrics`, loopback);
  `docker stats` for resources; `noria_practice.ops` probes for queue health. Plan: Prometheus + node/cAdvisor +
  MariaDB exporter + Redis exporter, with alerts on health checks, queue backlog, failed jobs and disk.
* **Errors:** Frappe `Error Log` per site (provisioning and broker failures are logged there). Plan: Sentry
  (Frappe supports a Sentry DSN via site config).
* **Health:** compose health checks on db, redis, backend, backend-ledger and edge; `tests/infra/check_stack.sh`
  can be used as a synthetic check.
