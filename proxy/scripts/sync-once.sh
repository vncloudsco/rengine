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
if ! service_running web; then
  compose up -d web
fi

auto_enable="$(env_get AUTO_ENABLE_PROXY true)"

compose exec -T web env \
  PROXY_FILE=/usr/src/urban_proxies/proxies_curl.txt \
  AUTO_ENABLE_PROXY="$auto_enable" \
  python3 /usr/src/urban_proxies/sync_django.py

log "Sync complete. Hard-refresh Proxy Settings in reNgine UI (Ctrl+F5)."
