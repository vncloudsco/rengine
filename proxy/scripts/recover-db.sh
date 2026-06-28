#!/usr/bin/env bash
# Reset broken PostgreSQL state after duplicate migration runs.
# Usage: bash scripts/recover-db.sh [-y]

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_docker
ensure_root_env
detect_compose_project_name

VOLUME="${COMPOSE_PROJECT_NAME}_postgres_data"

log "Stops stack and deletes PostgreSQL volume: $VOLUME"
log "All reNgine DB data will be lost."
if [[ "${1:-}" != "-y" ]]; then
  read -r -p "Continue? (y/N): " answer || true
  case "${answer:-}" in
    y|Y|yes|YES|Yes) ;;
    *) log "Aborted."; exit 0 ;;
  esac
fi

cd "$ROOT_DIR"
make down 2>/dev/null || compose down 2>/dev/null || true

if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  docker volume rm "$VOLUME"
  log "Removed volume $VOLUME"
else
  log "Volume $VOLUME not found."
fi

log "Done. Run: make up"
