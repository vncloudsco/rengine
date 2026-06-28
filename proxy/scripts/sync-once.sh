#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_docker
ensure_root_env
mkdir -p "$DATA_DIR"

if [[ ! -f "$PROXY_FILE" ]]; then
  log_error "Proxy file not found: $PROXY_FILE"
  log "Run 'make up' first or wait for fetch to complete."
  exit 1
fi

log "Syncing proxies via Django ORM (web container)..."
ensure_web_proxy_volume

run_sync_django

log "Sync complete. Hard-refresh Proxy Settings in reNgine UI (Ctrl+F5)."
