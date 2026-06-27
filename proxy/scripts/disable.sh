#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_docker
ensure_root_env

if service_running urban-proxy-fetcher; then
  compose exec -T urban-proxy-fetcher python3 /app/sync_proxies_to_db.py --disable
else
  log "Sidecar not running — disabling via one-off container..."
  compose run --rm --no-deps urban-proxy-fetcher python3 /app/sync_proxies_to_db.py --disable
fi

log "use_proxy set to false in scanengine_proxy."
