#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

require_docker
ensure_root_env
mkdir -p "$DATA_DIR"

if [[ ! -f "$PROXY_FILE" ]]; then
  log_error "Proxy file not found: $PROXY_FILE"
  log "Run 'make up' first or wait for fetch to complete."
  exit 1
fi

if service_running urban-proxy-fetcher; then
  compose exec -T urban-proxy-fetcher python3 /app/sync_proxies_to_db.py --force
else
  compose run --rm --no-deps \
    -e POSTGRES_HOST=db \
    urban-proxy-fetcher \
    python3 /app/sync_proxies_to_db.py --file /data/proxies_curl.txt --force
fi

log "Sync complete."
