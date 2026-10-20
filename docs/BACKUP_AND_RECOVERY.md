# Backup and Recovery

## What to back up

| Item | How | Notes |
|---|---|---|
| Every site's database + public + private files | `bench --site <site> backup --with-files` (`noria.sh backup all`); in production `backup-cron` does this every 6 h (`NORIA_BACKUP_INTERVAL_SECONDS`) | Encrypted with GPG because `encrypt_backup` is enabled on every site. Output: `sites/<site>/private/backups/*-enc.*` |
| `sites/*/site_config.json` and `sites/common_site_config.json` | copy to a secret store on every change (new client site, credential rotation) | Contain DB passwords and **`backup_encryption_key`**. Without the key, backups cannot be decrypted. |
| `secrets/` (DB root, hub admin) | secret manager | — |
| MariaDB volume snapshots (optional) | storage-level snapshots, taken with the DB stopped or via `mariadb-backup` | Faster full-server recovery; per-site restore still uses site backups. |

Copy backups **off the host** (object storage with versioning and retention, e.g. 30 daily + 12 monthly; financial
records in Kenya are generally kept for years — confirm the retention period with legal/tax advisers). Frappe keeps
only a few local backups (`backup_limit`).

## Restore one client site (verified procedure)

This is the exact procedure exercised by `tests/infra/check_stack.sh`. That check restores a client backup into a
scratch site and compares GL row counts, debit and credit totals, and private file counts.

```bash
# inside the provisioner (holds the DB root password); use ABSOLUTE paths
noria.sh compose run --rm -T provisioner bash
KEY=<backup_encryption_key of the source site>
B=/home/frappe/frappe-bench/sites/<site>/private/backups/<timestamp>-<site_underscored>
bench --site <target-site> restore $B-database-enc.sql.gz \
  --with-public-files $B-files-enc.tar --with-private-files $B-private-files-enc.tar \
  --db-root-password "$(cat $NORIA_DB_ROOT_PASSWORD_FILE)" --encryption-key "$KEY" --force
bench --site <target-site> migrate          # if restoring into a newer code version
```

Finding from testing: relative backup paths fail for encrypted file archives ("Invalid path"); always pass absolute
paths.

To restore **in place** (disaster recovery of a client), restore onto the same site name. The hub's `Client Site`
record (service credentials) stays valid when the restored database contains the same service user secret. If the
backup predates a credential rotation, run `noria_ledger.provisioning.rotate_service_credentials` and update the
hub record.

## Restore the hub

Same procedure for the hub site. Client sites are independent, so a hub restore never touches books. After
restoring an older hub backup, reconcile `Client Site` records with existing client sites (any site provisioned
after the backup must be re-attached).

## Full-server recovery

1. New host, same Compose project and env file; restore `secrets/` and the site configs.
2. `noria.sh up` (empty volumes) → create each site and restore it from backup (script the loop over sites).
3. Run `tests/infra/check_stack.sh` and spot-check books (trial balance per client) before reopening.

## Offboarding and deletion

`clients.archive` ends the engagement; when no firm serves the client any longer, it queues a full backup on the
provisioner. **Databases are never dropped automatically.** Deletion after the retention period is a manual operator
procedure: final backup → `bench drop-site <site> --no-backup` (archives the site directory) → remove archives
after confirmation → record it in the audit log.
