#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_docker
ensure_root_env
load_env_domain

echo ""
log "=== reNgine core ==="
for svc in db web celery celery-beat redis proxy; do
  if service_running "$svc"; then
    echo "  $svc: running"
  else
    echo "  $svc: not running"
  fi
done

echo ""
log "=== Urban proxy module ==="
if service_running urban-proxy-fetcher || docker ps --format '{{.Names}}' | grep -q '^rengine-urban-proxy$'; then
  echo "  urban-proxy-fetcher: running"
else
  echo "  urban-proxy-fetcher: not running"
fi

if [[ -f "$PROXY_FILE" ]]; then
  count="$(grep -cE '^https?://' "$PROXY_FILE" 2>/dev/null || echo 0)"
  echo "  proxies in file: $count ($PROXY_FILE)"
else
  echo "  proxies in file: (file not found yet)"
fi

echo ""
log "Use 'make logs' for sidecar output."
