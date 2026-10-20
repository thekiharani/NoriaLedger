#!/usr/bin/env bash
# Scale a NON-PRODUCTION stack to N benchmark client sites for measurements.
#
#   tests/perf/scale_sites.sh <total-benchmark-sites>
#   tests/perf/scale_sites.sh --remove      # drop all bench-* sites + hub records
#
# Sites are cloned from one bootstrapped template (bench new-site --source-sql),
# then each gets its own rotated service-user secret and is attached to the hub
# under the firm given by BENCH_FIRM (default: first firm). Idempotent: existing
# bench-NNN sites are kept. Prints per-site creation time.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
N="$ROOT/infrastructure/scripts/noria.sh"
set -a; source "${NORIA_ENV_FILE:-$ROOT/.env}"; set +a
[[ "${NORIA_ENV:-development}" != "production" ]] || { echo "refusing in production"; exit 1; }
total="${1:?usage: scale_sites.sh <n>|--remove}"
suffix="${NORIA_CLIENT_SITE_SUFFIX:-ledger.internal}"
template="bench-template.$suffix"
tsql="/home/frappe/frappe-bench/sites/bench-template.sql.gz"
bexec() { "$N" compose exec -T backend "$@"; }

if [[ "$total" == "--remove" ]]; then
  sites="$(bexec bash -c "ls sites | grep -E '^bench-([0-9]+|template)\\.'" | tr -d '\r')"
  # shellcheck disable=SC2086
  "$N" compose run --rm --no-deps -T provisioner bash -euc '
    root="$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")"
    for s in "$@"; do bench drop-site "$s" --db-root-password "$root" --no-backup --force >/dev/null 2>&1 && echo "dropped $s"; done
    rm -rf archived/sites/bench-* sites/bench-template.sql.gz' _ $sites | grep -c dropped
  bexec bench --site "$NORIA_HUB_SITE" execute noria_practice.ops.remove_benchmark_clients
  exit 0
fi

if ! bexec bash -c "gzip -t $tsql" 2>/dev/null; then
  if ! bexec test -d "sites/$template"; then
  echo "creating template site $template"
  "$N" compose run --rm --no-deps -T provisioner bash -euc '
    bench new-site "$0" --mariadb-user-host-login-scope=% --db-root-password "$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")" \
      --admin-password "$(openssl rand -hex 12)" --install-app erpnext --install-app noria_ledger >/dev/null' "$template"
  bexec bench --site "$template" execute noria_ledger.provisioning.bootstrap \
    --kwargs '{"company_name": "Bench Template Co", "company_abbr": "BTC", "fy_start_date": "2026-01-01"}' >/dev/null
  fi
  # Plain dump of the template database (site backups are encrypted by design).
  db_name="$(bexec python3 -c "import json; print(json.load(open('sites/$template/site_config.json'))['db_name'])" | tr -d '\r')"
  "$N" compose exec -T db sh -c "mariadb-dump -uroot -p\"\$(cat /run/secrets/db_root_password)\" --single-transaction --quick $db_name" \
    | gzip | "$N" compose exec -T backend bash -c "cat > $tsql"
fi

firm="${BENCH_FIRM:-$(bexec bench --site "$NORIA_HUB_SITE" mariadb -N -e "select name from \`tabAccounting Firm\` order by creation limit 1" | tr -d '\r')}"
for i in $(seq -f "%03g" 1 "$total"); do
  site="bench-$i.$suffix"
  if bexec test -d "sites/$site" && bexec bench --site "$site" mariadb -e "select 1 from tabCompany limit 1" >/dev/null 2>&1; then continue; fi
  t0=$(date +%s.%N)
  "$N" compose run --rm --no-deps -T provisioner bash -euc '
    root="$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")"
    [ -d "sites/$0" ] && bench drop-site "$0" --db-root-password "$root" --no-backup --force >/dev/null 2>&1 || true
    bench new-site "$0" --source-sql "$1" --mariadb-user-host-login-scope=% \
      --db-root-password "$root" --admin-password "$(openssl rand -hex 12)" >/dev/null' "$site" "$tsql" 2>&1 | grep -vE "Container|Linking" || true
  creds="$(bexec bench --site "$site" execute noria_ledger.provisioning.rotate_service_credentials \
            --kwargs '{"service_user": "noria-service@bench-template.'"$suffix"'"}' | tail -1)"
  args="$(python3 -c 'import json,sys; c=json.loads(sys.argv[1]); print(json.dumps({"firm": sys.argv[2], "site_name": sys.argv[3], **c}))' "$creds" "$firm" "$site")"
  bexec bench --site "$NORIA_HUB_SITE" execute noria_practice.ops.register_benchmark_client --kwargs "$args" >/dev/null
  echo "$site created in $(echo "$(date +%s.%N) - $t0" | bc | cut -c1-5)s"
done
echo "benchmark sites: $(bexec bash -c "ls sites | grep -c '^bench-[0-9]'")"
