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
log "=== reNgine DB (scanengine_proxy) ==="
pg_user="$(env_get POSTGRES_USER rengine)"
pg_db="$(env_get POSTGRES_DB rengine)"
db_line="$(compose exec -T db psql -U "$pg_user" -d "$pg_db" -t -A -F'|' -c \
  "SELECT use_proxy, COALESCE(length(proxies), 0), COALESCE((length(proxies) - length(replace(proxies, chr(10), ''))), 0) + CASE WHEN proxies IS NOT NULL AND proxies <> '' THEN 1 ELSE 0 END FROM scanengine_proxy ORDER BY id LIMIT 1;" \
  2>/dev/null | tr -d '[:space:]' || true)"

if [[ -z "$db_line" ]]; then
  echo "  (no row in scanengine_proxy — run: make sync-once)"
else
  IFS='|' read -r use_proxy proxy_len proxy_lines <<< "$db_line"
  echo "  use_proxy: ${use_proxy:-unknown}"
  echo "  proxies in DB: ${proxy_lines:-0} lines (${proxy_len:-0} chars)"
fi

echo ""
log "If file has proxies but DB is empty: make sync-once"
log "Sidecar logs: make logs"
