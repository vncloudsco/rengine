#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_docker
ensure_root_env

if ! service_running web; then
  compose up -d web
fi

log "Disabling proxy via Django ORM (web container)..."
ensure_web_proxy_volume
compose exec -T web python3 /usr/src/urban_proxies/sync_django.py --disable
log "use_proxy=false in scanengine_proxy (same path as Proxy Settings UI)."
