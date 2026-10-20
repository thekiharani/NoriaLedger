#!/usr/bin/env bash
# Infrastructure checks against a running stack (non-production):
# container health, DB + Redis connectivity, background jobs, migrations,
# application startup through the edge, and an encrypted backup -> restore
# round trip of a client site with ledger checksums compared.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
N="$ROOT/infrastructure/scripts/noria.sh"
set -a; source "${NORIA_ENV_FILE:-$ROOT/.env}"; set +a
[[ "${NORIA_ENV:-development}" != "production" ]] || { echo "refusing in production"; exit 1; }

pass=0; fail=0
ok() { echo "  PASS  $*"; pass=$((pass+1)); }
ko() { echo "  FAIL  $*"; fail=$((fail+1)); }
check() { local name="$1"; shift; if "$@" >/tmp/noria-check.out 2>&1; then ok "$name"; else ko "$name"; tail -5 /tmp/noria-check.out; fi; }
bexec() { "$N" compose exec -T backend "$@"; }

echo "Infrastructure checks (${COMPOSE_PROJECT_NAME})"

for svc in db redis-cache redis-queue backend edge; do
  check "container healthy: $svc" bash -c "[[ \$(docker inspect -f '{{.State.Health.Status}}' \$($N compose ps -q $svc)) == healthy ]]"
done
for svc in queue-short queue-long scheduler websocket provisioner; do
  check "container running: $svc" bash -c "[[ \$(docker inspect -f '{{.State.Status}}' \$($N compose ps -q $svc)) == running ]]"
done

check "database connectivity (hub)" bexec bench --site "$NORIA_HUB_SITE" mariadb -e "select 1"
check "redis cache ping" bash -c "$N compose exec -T redis-cache redis-cli ping | grep -q PONG"
check "redis queue ping" bash -c "$N compose exec -T redis-queue redis-cli ping | grep -q PONG"
check "edge serves SPA" bash -c "curl -fsS http://localhost:${NORIA_HTTP_PORT:-8080}/ | grep -q '<div id=\"root\">'"
check "edge -> hub API" bash -c "curl -fsS http://localhost:${NORIA_HTTP_PORT:-8080}/api/method/noria_practice.api.session.bootstrap | grep -q allow_signup"
check "edge blocks non-allow-listed API" bash -c "[[ \$(curl -s -o /dev/null -w '%{http_code}' http://localhost:${NORIA_HTTP_PORT:-8080}/api/resource/User) == 404 ]]"

# Background job round trip: enqueue on the short queue, wait for a worker to run it.
marker="noria-infra-$(date +%s)"
for q in short long; do
  bexec bench --site "$NORIA_HUB_SITE" execute noria_practice.ops.enqueue_probe --kwargs "{\"marker\": \"$marker-$q\", \"queue\": \"$q\"}" >/dev/null
  check "background worker executes '$q' queue jobs" bash -c "for i in \$(seq 1 30); do $N compose exec -T backend bench --site $NORIA_HUB_SITE execute noria_practice.ops.read_probe --args '[\"$marker-$q\"]' 2>/dev/null | grep -q done && exit 0; sleep 1; done; exit 1"
done

check "migrations run cleanly (hub)" bexec bench --site "$NORIA_HUB_SITE" migrate

# Backup -> restore round trip of a client site.
# Prefer a seeded client site that holds documents (private files).
site="$(bexec bash -c "for s in \$(ls sites | grep '\\.${NORIA_CLIENT_SITE_SUFFIX}\$' | grep -vE '^(ledger-test|restore-check|devtest)\\.'); do n=\$(ls sites/\$s/private/files 2>/dev/null | wc -l); echo \"\$n \$s\"; done | sort -rn | head -1 | cut -d' ' -f2" | tr -d '\r')"
if [[ -z "$site" ]]; then
  ko "backup/restore: no client site found (run seed)"
else
  restore_site="restore-check.${NORIA_CLIENT_SITE_SUFFIX}"
  checksum_sql="select count(*), round(sum(debit),2), round(sum(credit),2) from \`tabGL Entry\` where is_cancelled=0"
  before="$(bexec bench --site "$site" mariadb -N -e "$checksum_sql" | tr -s '[:space:]' ' ')"
  bexec bench --site "$site" backup --with-files >/tmp/noria-backup.out 2>&1
  # Absolute paths: bench restore decrypts file archives relative to another cwd.
  bdir="/home/frappe/frappe-bench/sites/$site/private/backups"
  db_file="$(bexec bash -c "ls -t $bdir/*-database*.sql.gz | head -1" | tr -d '\r')"
  pub_file="$(bexec bash -c "ls -t $bdir/*-files*.tar | grep -v private | head -1" | tr -d '\r')"
  priv_file="$(bexec bash -c "ls -t $bdir/*-private-files*.tar | head -1" | tr -d '\r')"
  key="$(bexec python3 -c "import json; print(json.load(open('/home/frappe/frappe-bench/sites/$site/site_config.json')).get('backup_encryption_key', ''))" | tr -d '\r')"
  if [[ "$db_file" == *"-enc"* || "$db_file" == *enc* ]]; then ok "backup is encrypted ($db_file)"; else ko "backup not encrypted ($db_file)"; fi
  "$N" compose run --rm --no-deps -T -e SRC_DB="$db_file" -e SRC_PUB="$pub_file" -e SRC_PRIV="$priv_file" -e ENC_KEY="$key" provisioner bash -euc '
    if [ -d "sites/$0" ]; then bench drop-site "$0" --db-root-password "$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")" --no-backup --force >/dev/null; fi
    bench new-site "$0" --mariadb-user-host-login-scope=% --db-root-password "$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")" --admin-password "$(openssl rand -hex 12)" >/dev/null
    bench --site "$0" restore "$SRC_DB" --with-public-files "$SRC_PUB" --with-private-files "$SRC_PRIV" \
      --db-root-password "$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")" ${ENC_KEY:+--encryption-key "$ENC_KEY"} --force >/dev/null' "$restore_site" >/tmp/noria-restore.out 2>&1 || { ko "restore command"; tail -20 /tmp/noria-restore.out; }
  after="$(bexec bench --site "$restore_site" mariadb -N -e "$checksum_sql" 2>/dev/null | tr -s '[:space:]' ' ')"
  if [[ -n "$before" && "$before" == "$after" ]]; then ok "restore verified: GL rows/debits/credits match ($before)"; else ko "restore mismatch: before='$before' after='$after'"; fi
  files_before="$(bexec bash -c "ls sites/$site/private/files 2>/dev/null | wc -l")"
  files_after="$(bexec bash -c "ls sites/$restore_site/private/files 2>/dev/null | wc -l")"
  [[ "$files_before" == "$files_after" ]] && ok "private files restored ($files_after)" || ko "private files mismatch $files_before vs $files_after"
  "$N" compose run --rm --no-deps -T provisioner bash -euc 'bench drop-site "$0" --db-root-password "$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")" --no-backup --force >/dev/null' "$restore_site" || true
fi

echo "infra checks: $pass passed, $fail failed"
[[ $fail -eq 0 ]]
