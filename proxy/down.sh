#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

require_docker
ensure_root_env

pkill -f "proxy/scripts/sync-watch.sh" 2>/dev/null || true

log "Stopping urban-proxy-fetcher (reNgine core keeps running)..."
compose stop urban-proxy-fetcher 2>/dev/null || true
compose rm -f urban-proxy-fetcher 2>/dev/null || true
log "Urban proxy module stopped."
