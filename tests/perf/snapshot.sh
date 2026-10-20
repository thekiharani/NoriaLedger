#!/usr/bin/env bash
# Resource snapshot of a running stack: sites, container memory/CPU, DB size and
# table-cache pressure, queue backlog. Usage: tests/perf/snapshot.sh [label]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
N="$ROOT/infrastructure/scripts/noria.sh"
set -a; source "${NORIA_ENV_FILE:-$ROOT/.env}"; set +a
label="${1:-snapshot}"
root_pw="$(cat "${NORIA_SECRETS_DIR:-$ROOT/secrets}/db_root_password")"
echo "## $label — $(date -u +%FT%TZ)"
echo "client sites: $("$N" compose exec -T backend bash -c "ls sites | grep -c '\\.${NORIA_CLIENT_SITE_SUFFIX}\$'")"
echo; echo "### containers"
docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' | sed "s/${COMPOSE_PROJECT_NAME}-//" | sort
echo; echo "### database"
"$N" compose exec -T db mariadb -uroot -p"$root_pw" -N -e "
  select concat('schemas: ', count(distinct table_schema), '  tables: ', count(*), '  data+index MB: ', round(sum(data_length+index_length)/1048576)) from information_schema.tables where table_schema like '\\_%';
  show global status where Variable_name in ('Open_tables','Opened_tables','Threads_connected','Max_used_connections','Open_files');
  show global variables where Variable_name in ('table_open_cache','table_definition_cache','innodb_buffer_pool_size','max_connections');"
echo "on-disk: $("$N" compose exec -T db du -sh /var/lib/mysql | cut -f1)"
echo; echo "### queues"
"$N" compose exec -T redis-queue redis-cli --scan --pattern 'rq:queue:*' | while read -r q; do echo "$q $("$N" compose exec -T redis-queue redis-cli llen "$q")"; done
