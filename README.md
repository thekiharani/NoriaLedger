# Noria Ledger

Accounting and practice-management SaaS for Kenyan accounting firms, by **Noria Technologies Ltd**.
Firms manage many independent client businesses from one place. Each client's books live in an isolated
ERPNext site, and business owners use a limited client portal.

* **Accounting engine:** ERPNext 16.51.1 / Frappe 16.52.0, unmodified and authoritative for every posting.
* **Custom apps:** `noria_practice` (practice hub) and `noria_ledger` (per-client service API).
* **Frontend:** React + TypeScript + TanStack + Tailwind, served by a Caddy edge.
* **Infrastructure:** Docker Compose based on frappe_docker; MariaDB 11.8 LTS, Redis 8.10.

## Quick start

```bash
cp .env.example .env
./infrastructure/scripts/noria.sh init-secrets
./infrastructure/scripts/noria.sh build && ./infrastructure/scripts/noria.sh up
./infrastructure/scripts/noria.sh create-hub && ./infrastructure/scripts/noria.sh seed
open http://localhost:8080        # demo users: docs/INSTALLATION.md
```

## Documentation

| Document | Contents |
|---|---|
| [docs/TECHNICAL_AUDIT.md](docs/TECHNICAL_AUDIT.md) | Versions, compatibility, database choice, licensing, build strategy |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, tenancy, request flow, security boundaries, workflows |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Local development environment |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment, multi-site upgrades, rollback, readiness checklist |
| [docs/BACKUP_AND_RECOVERY.md](docs/BACKUP_AND_RECOVERY.md) | Encrypted backups and a verified restore procedure |
| [docs/OPTIMIZATION_REPORT.md](docs/OPTIMIZATION_REPORT.md) | Measured image sizes, startup, memory, load and multi-site scaling |
| [docs/SECURITY.md](docs/SECURITY.md) | Controls, gaps, Kenya Data Protection Act notes |
| [docs/KENYA_COMPLIANCE.md](docs/KENYA_COMPLIANCE.md) | Tax/eTIMS/M-PESA status (no automatic KRA filing) |
| [docs/TESTING.md](docs/TESTING.md) | Test suites and recorded results |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | What is not built yet, and the roadmap |

## Status

Milestone 1 (foundation and a real end-to-end accountant/client workflow) is implemented and tested.
It is **not production-ready**; see the readiness checklist in docs/DEPLOYMENT.md.
