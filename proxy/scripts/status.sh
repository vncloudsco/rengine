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
log "=== reNgine DB (via Django ORM) ==="
if service_running web; then
  django_status="$(compose exec -T web python3 -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reNgine.settings')
import django
django.setup()
from scanEngine.models import Proxy
p = Proxy.objects.first()
print(f'table={Proxy._meta.db_table}')
print(f'rows={Proxy.objects.count()}')
if p:
    lines = [x for x in (p.proxies or '').splitlines() if x.strip()]
    print(f'use_proxy={p.use_proxy}')
    print(f'proxy_lines={len(lines)}')
else:
    print('use_proxy=false')
    print('proxy_lines=0')
" 2>/dev/null || echo "error=could not query Django")"
  echo "$django_status" | sed 's/^/  /'
else
  echo "  web not running"
fi

echo ""
log "If file has proxies but Django rows=0: make sync-once"
log "Sidecar logs: make logs"
