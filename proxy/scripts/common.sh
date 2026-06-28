#!/usr/bin/env bash
# Shared helpers for the Urban proxy module.

set -euo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
DATA_DIR="$PROXY_DIR/data"
PROXY_FILE="$DATA_DIR/proxies_curl.txt"
COMPOSE_FILES=(-f "$ROOT_DIR/docker-compose.yml" -f "$PROXY_DIR/docker-compose.yml")

NON_INTERACTIVE=false

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  DOCKER_COMPOSE=()
fi

detect_compose_project_name() {
  if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]]; then
    return
  fi
  local from_env
  from_env="$(env_get COMPOSE_PROJECT_NAME "")"
  if [[ -n "$from_env" ]]; then
    COMPOSE_PROJECT_NAME="$from_env"
    export COMPOSE_PROJECT_NAME
    return
  fi
  local folder
  folder="$(basename "$ROOT_DIR")"
  folder="${folder// /}"
  folder="$(echo "$folder" | tr '[:upper:]' '[:lower:]')"
  COMPOSE_PROJECT_NAME="${folder:-rengine}"
  export COMPOSE_PROJECT_NAME
}

# Read KEY=value from .env without sourcing (safe for passwords with @ & $ etc.)
env_get() {
  local key="$1"
  local default="${2:-}"
  local line value
  line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s' "$default"
    return
  fi
  value="${line#*=}"
  printf '%s' "$value"
}

compose() {
  detect_compose_project_name
  if [[ ! -f "$ENV_FILE" ]]; then
    log_error "Missing $ENV_FILE"
    exit 1
  fi
  export COMPOSE_PROJECT_NAME
  "${DOCKER_COMPOSE[@]}" --project-directory "$ROOT_DIR" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"
}

log() {
  echo "[urban-proxy] $*"
}

log_error() {
  echo "[urban-proxy] ERROR: $*" >&2
}

usage() {
  cat <<'EOF'
Urban Proxy module for reNgine

Usage:
  ./up.sh [-n] [-h]     Start reNgine (if needed) + Urban proxy sidecar
  ./down.sh             Stop Urban proxy sidecar only
  ./down-all.sh         Stop full reNgine stack + proxy module

Make equivalents (from proxy/):
  make up | down | down-all | logs | status | disable | sync-once | help

Options:
  -n    Non-interactive (skip prompts)
  -h    Show this help
EOF
}

parse_args() {
  while getopts nh opt; do
    case "$opt" in
      n) NON_INTERACTIVE=true ;;
      h) usage; exit 0 ;;
      ?) usage; exit 1 ;;
    esac
  done
}

require_docker() {
  if [[ ${#DOCKER_COMPOSE[@]} -eq 0 ]]; then
    log_error "Docker Compose not found. Install Docker Desktop or docker-compose."
    log_error "See https://rengine.wiki for setup instructions."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    log_error "Docker is not running. Start Docker and try again."
    exit 1
  fi
}

ensure_root_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log_error "Missing $ENV_FILE"
    log "Create .env in the reNgine root (copy from .env.example if available)."
    log "Required: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, DOMAIN_NAME, ..."
    exit 1
  fi
}

service_running() {
  local service="$1"
  local id
  id="$(compose ps -q "$service" 2>/dev/null || true)"
  if [[ -z "$id" ]]; then
    return 1
  fi
  local status
  status="$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || echo "unknown")"
  [[ "$status" == "running" ]]
}

is_rengine_core_running() {
  service_running db && service_running web && service_running celery
}

superuser_exists() {
  service_running web || return 1
  compose exec -T web python3 manage.py shell -c \
    "from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_superuser=True).exists())" \
    2>/dev/null | grep -q "True"
}

wait_for_db_ready() {
  local i pg_user
  pg_user="$(env_get POSTGRES_USER postgres)"
  log "Waiting for PostgreSQL..."
  for i in $(seq 1 60); do
    if compose exec -T db pg_isready -U "$pg_user" >/dev/null 2>&1; then
      log "PostgreSQL is ready."
      return 0
    fi
    sleep 2
  done
  log_error "PostgreSQL did not become ready in time."
  exit 1
}

wait_for_web_migrations() {
  log "Waiting for web entrypoint migrations (NOT running make migrate — avoids race)..."
  sleep 20
  local i
  for i in $(seq 1 120); do
    if ! service_running web; then
      sleep 2
      continue
    fi
    if compose exec -T web python3 manage.py migrate --check >/dev/null 2>&1; then
      log "Database migrations are up to date."
      return 0
    fi
    sleep 3
  done
  log "Migration check timed out (web may still be migrating)."
  log "If UI fails, run: bash scripts/recover-db.sh && make up"
  return 0
}

wait_for_proxy_file() {
  local timeout="${1:-300}"
  local i=0
  log "Waiting for proxy file (up to ${timeout}s)..."
  while [[ $i -lt $timeout ]]; do
    if [[ -s "$PROXY_FILE" ]]; then
      local count
      count="$(grep -cE '^https?://' "$PROXY_FILE" 2>/dev/null || echo 0)"
      if [[ "$count" -gt 0 ]]; then
        log "Proxy file ready: $count entries in $PROXY_FILE"
        return 0
      fi
    fi
    sleep 5
    i=$((i + 5))
  done
  log "Proxy file not ready yet — sidecar may still be fetching. Check: make logs"
}

load_env_domain() {
  DOMAIN_NAME="$(env_get DOMAIN_NAME localhost)"
  export DOMAIN_NAME
}
