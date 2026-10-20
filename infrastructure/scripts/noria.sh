#!/usr/bin/env bash
# Noria Ledger operations entry point.
#
#   ./infrastructure/scripts/noria.sh <command> [args]
#
# Environment selection:
#   NORIA_ENV_FILE   env file to load (default: <repo>/.env)
#   The file's NORIA_ENV (development|staging|production) decides which compose
#   overrides apply and which destructive commands are allowed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${NORIA_ENV_FILE:-$ROOT/.env}"
COMPOSE_DIR="$ROOT/infrastructure/compose"

die() { echo "error: $*" >&2; exit 1; }
info() { echo "==> $*" >&2; }

[[ -f "$ENV_FILE" ]] || die "env file $ENV_FILE not found (cp .env.example .env)"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

NORIA_ENV="${NORIA_ENV:-development}"
[[ -n "${NORIA_HUB_SITE:-}" ]] || die "NORIA_HUB_SITE must be set in $ENV_FILE"

compose_files=(-f "$COMPOSE_DIR/compose.yaml")
case "$NORIA_ENV" in
  development) compose_files+=(-f "$COMPOSE_DIR/compose.dev.yaml") ;;
  staging|production) compose_files+=(-f "$COMPOSE_DIR/compose.prod.yaml") ;;
  *) die "unknown NORIA_ENV=$NORIA_ENV" ;;
esac

dc() { docker compose --env-file "$ENV_FILE" "${compose_files[@]}" "$@"; }
bench_exec() { dc exec -T backend bench "$@"; }

require_non_production() {
  if [[ "$NORIA_ENV" == "production" ]]; then
    die "'$1' is disabled when NORIA_ENV=production"
  fi
}

confirm() {
  local prompt="$1"
  if [[ "${NORIA_ASSUME_YES:-0}" == "1" ]]; then return 0; fi
  read -r -p "$prompt [type 'yes' to continue]: " answer
  [[ "$answer" == "yes" ]] || die "aborted"
}

cmd_init_secrets() {
  local dir="${NORIA_SECRETS_DIR:-$ROOT/secrets}"
  mkdir -p "$dir"
  for name in db_root_password hub_admin_password demo_password; do
    if [[ -s "$dir/$name" ]]; then
      info "$name exists, keeping it"
    else
      require_non_production "generating $name"
      (umask 077; openssl rand -base64 32 | tr -d '/+=\n' | head -c 32 > "$dir/$name")
      info "generated $dir/$name"
    fi
  done
  # Docker secrets from files are bind-mounted with host permissions; the frappe
  # (uid 1000) and mysql users must be able to read them inside the containers.
  chmod 0644 "$dir"/db_root_password "$dir"/hub_admin_password "$dir"/demo_password
}

cmd_build() {
  local version
  version="$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || echo dev)"
  info "building backend image ${NORIA_BACKEND_IMAGE}:${NORIA_TAG} ($version)"
  docker build -f "$ROOT/infrastructure/docker/backend.Dockerfile" \
    --build-arg ERPNEXT_IMAGE="${UPSTREAM_REGISTRY:-docker.io}/frappe/erpnext:v16.51.1@sha256:85b63c68a1e7992179f5448f334916a49b2e47e5e7382fc346039d073bc7ca27" \
    --build-arg NORIA_VERSION="$version" \
    -t "${NORIA_BACKEND_IMAGE}:${NORIA_TAG}" "$ROOT"
  info "building edge image ${NORIA_EDGE_IMAGE}:${NORIA_TAG}"
  local secret_args=()
  if [[ -n "${NORIA_BUILD_EXTRA_CA:-}" ]]; then
    secret_args=(--secret "id=extra_ca,src=${NORIA_BUILD_EXTRA_CA}")
  fi
  docker build -f "$ROOT/infrastructure/docker/edge.Dockerfile" "${secret_args[@]}" \
    --build-arg BUN_IMAGE="${UPSTREAM_REGISTRY:-docker.io}/oven/bun:1.4-alpine@sha256:629e17411f1f129dbec3af78d5af9c9f2a937435c80349437206c6b0b7422373" \
    --build-arg CADDY_IMAGE="${UPSTREAM_REGISTRY:-docker.io}/library/caddy:2.11-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f" \
    --build-arg NORIA_VERSION="$version" \
    -t "${NORIA_EDGE_IMAGE}:${NORIA_TAG}" "$ROOT"
}

cmd_up() { dc up -d --wait "$@"; }
cmd_down() { dc down "$@"; }
cmd_ps() { dc ps "$@"; }
cmd_logs() { dc logs -f --tail=200 "$@"; }

# Create the hub (practice management) site. Runs in a one-off provisioner
# container: the only service holding the DB root password.
cmd_create_hub() {
  if dc exec -T backend test -d "sites/$NORIA_HUB_SITE"; then
    info "hub site $NORIA_HUB_SITE already exists"
  else
    info "creating hub site $NORIA_HUB_SITE"
    dc run --rm --no-deps -T provisioner bash -euc '
      bench new-site "$0" \
        --mariadb-user-host-login-scope=% \
        --db-root-password "$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")" \
        --admin-password "$(cat "$NORIA_HUB_ADMIN_PASSWORD_FILE")" \
        --install-app noria_practice' "$NORIA_HUB_SITE"
  fi
  cmd_configure_hub
}

# Push environment-derived settings into the hub site config (idempotent).
cmd_configure_hub() {
  bench_exec --site "$NORIA_HUB_SITE" set-config noria_client_site_suffix "${NORIA_CLIENT_SITE_SUFFIX}"
  bench_exec --site "$NORIA_HUB_SITE" set-config -p noria_allow_firm_signup "${NORIA_ALLOW_FIRM_SIGNUP:-0}"
  bench_exec --site "$NORIA_HUB_SITE" set-config noria_client_site_base_url "http://backend-ledger:8000"
  bench_exec --site "$NORIA_HUB_SITE" enable-scheduler
  if [[ "$NORIA_ENV" != "production" ]]; then
    bench_exec --site "$NORIA_HUB_SITE" set-config -p allow_tests 1
  fi
  bench_exec use "$NORIA_HUB_SITE"
}

cmd_migrate() {
  info "migrating all sites (hub + client sites)"
  bench_exec --site all migrate "$@"
}

cmd_seed() {
  require_non_production "seed"
  info "seeding demo data (provisions demo client sites; takes several minutes)"
  local secrets_dir="${NORIA_SECRETS_DIR:-$ROOT/secrets}"
  [[ -s "$secrets_dir/demo_password" ]] || die "missing $secrets_dir/demo_password (run init-secrets)"
  # Runs on a one-off provisioner container: demo seeding provisions client sites.
  dc run --rm --no-deps -T \
    -v "$secrets_dir/demo_password:/run/secrets/demo_password:ro" \
    -e NORIA_DEMO_PASSWORD_FILE=/run/secrets/demo_password -e NORIA_ENV="$NORIA_ENV" \
    provisioner bench --site "$NORIA_HUB_SITE" execute noria_practice.demo.seed.run
  info "demo users share the password in $secrets_dir/demo_password"
}

cmd_test() {
  local target="${1:-all}"
  case "$target" in
    hub|all)
      info "noria_practice unit/integration tests on $NORIA_HUB_SITE"
      bench_exec --site "$NORIA_HUB_SITE" run-tests --app noria_practice
      ;;&
    ledger|all)
      ensure_ledger_test_site
      info "noria_ledger tests on $LEDGER_TEST_SITE (disposable test site)"
      bench_exec --site "$LEDGER_TEST_SITE" run-tests --app noria_ledger
      ;;&
    e2e|all)
      info "end-to-end API workflow through the public edge"
      python3 "$ROOT/tests/e2e/test_accountant_workflow.py"
      ;;
    hub|ledger) ;;
    *) die "unknown test target $target (hub|ledger|e2e|all)" ;;
  esac
}

LEDGER_TEST_SITE="ledger-test.${NORIA_CLIENT_SITE_SUFFIX:-ledger.internal}"

# Ledger tests post real ERPNext documents, so they only ever run on a dedicated
# disposable client site flagged with noria_test_site=1 — never on client books.
ensure_ledger_test_site() {
  require_non_production "ledger tests"
  if ! dc exec -T backend test -d "sites/$LEDGER_TEST_SITE"; then
    info "creating disposable ledger test site $LEDGER_TEST_SITE"
    dc run --rm --no-deps -T provisioner bash -euc '
      bench new-site "$0" --mariadb-user-host-login-scope=% \
        --db-root-password "$(cat "$NORIA_DB_ROOT_PASSWORD_FILE")" \
        --admin-password "$(openssl rand -hex 16)" \
        --install-app erpnext --install-app noria_ledger >/dev/null' "$LEDGER_TEST_SITE"
    bench_exec --site "$LEDGER_TEST_SITE" execute noria_ledger.provisioning.bootstrap \
      --kwargs '{"company_name": "Noria Test Co", "company_abbr": "NTC", "fy_start_date": "2026-01-01"}' >/dev/null
  fi
  bench_exec --site "$LEDGER_TEST_SITE" set-config -p allow_tests 1
  bench_exec --site "$LEDGER_TEST_SITE" set-config -p noria_test_site 1
}

cmd_bench() { dc exec backend bench "$@"; }
cmd_shell() { dc exec "${1:-backend}" bash; }

cmd_backup() {
  local site="${1:-all}"
  info "backing up $site (database + files, encrypted if backup_encryption_key is set)"
  if [[ "$site" == "all" ]]; then
    bench_exec --site all backup --with-files
  else
    bench_exec --site "$site" backup --with-files
  fi
  info "backups are in the sites volume under <site>/private/backups"
}

cmd_reset() {
  require_non_production "reset"
  confirm "This DELETES all containers AND volumes (databases, sites, files) of project '${COMPOSE_PROJECT_NAME}'."
  dc down -v --remove-orphans
}

usage() {
  sed -n '2,9p' "$0"
  cat <<EOF
Commands:
  init-secrets         generate local secret files (non-production only)
  build                build backend + edge images
  up [svc...]          start the stack and wait for health
  down                 stop the stack (keeps volumes)
  ps | logs [svc]      status / follow logs
  create-hub           create + configure the hub site (idempotent)
  configure-hub        re-apply hub site config from the env file
  migrate              bench migrate on all sites
  seed                 load demo firms/clients/data (non-production only)
  test [hub|ledger|e2e|all]
  bench <args>         run bench in the backend container
  shell [svc]          interactive shell
  backup [site|all]    site backups with files
  reset                DESTRUCTIVE: remove containers + volumes (non-production, confirm)
EOF
}

command="${1:-help}"; shift || true
case "$command" in
  init-secrets) cmd_init_secrets "$@" ;;
  build) cmd_build "$@" ;;
  up) cmd_up "$@" ;;
  down) cmd_down "$@" ;;
  ps) cmd_ps "$@" ;;
  logs) cmd_logs "$@" ;;
  create-hub) cmd_create_hub "$@" ;;
  configure-hub) cmd_configure_hub "$@" ;;
  migrate) cmd_migrate "$@" ;;
  seed) cmd_seed "$@" ;;
  test) cmd_test "$@" ;;
  bench) cmd_bench "$@" ;;
  shell) cmd_shell "$@" ;;
  backup) cmd_backup "$@" ;;
  reset) cmd_reset "$@" ;;
  compose) dc "$@" ;;
  help|-h|--help) usage ;;
  *) usage; exit 1 ;;
esac
