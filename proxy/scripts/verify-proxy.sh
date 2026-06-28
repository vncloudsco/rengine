#!/usr/bin/env bash
# Verify where reNgine stores proxy config and that Urban module sync matches it.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_docker
ensure_root_env

echo ""
log "=== 1. Source of truth (Django model) ==="
compose exec -T web python3 <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reNgine.settings")
import django
django.setup()
from scanEngine.models import Proxy

print(f"model=scanEngine.models.Proxy")
print(f"db_table={Proxy._meta.db_table}")
print(f"db={Proxy.objects.db}")
print(f"row_count={Proxy.objects.count()}")
row = Proxy.objects.first()
if row:
    lines = [x for x in (row.proxies or "").splitlines() if x.strip()]
    print(f"use_proxy={row.use_proxy}")
    print(f"proxy_lines={len(lines)}")
    if lines:
        print(f"sample={lines[0][:80]}...")
else:
    print("use_proxy=(no row)")
    print("proxy_lines=0")
PY

echo ""
log "=== 2. PostgreSQL direct check (same table Django uses) ==="
pg_user="$(env_get POSTGRES_USER rengine)"
pg_db="$(env_get POSTGRES_DB rengine)"
table="$(compose exec -T web python3 -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','reNgine.settings'); import django; django.setup(); from scanEngine.models import Proxy; print(Proxy._meta.db_table)" 2>/dev/null | tr -d '\r')"

if compose exec -T db psql -U "$pg_user" -d "$pg_db" -t -c "SELECT to_regclass('public.${table}');" 2>/dev/null | grep -q "${table}"; then
  compose exec -T db psql -U "$pg_user" -d "$pg_db" -c \
    "SELECT id, use_proxy, COALESCE(length(proxies),0) AS chars,
            CASE WHEN proxies IS NULL OR proxies='' THEN 0
                 ELSE array_length(regexp_split_to_array(proxies, E'\\n'), 1) END AS lines
     FROM ${table} ORDER BY id LIMIT 1;"
else
  echo "  Table public.${table} does not exist yet."
fi

echo ""
log "=== 3. Urban module file (NOT read by reNgine scans) ==="
if [[ -f "$PROXY_FILE" ]]; then
  count="$(grep -cE '^https?://' "$PROXY_FILE" 2>/dev/null || echo 0)"
  echo "  file=$PROXY_FILE"
  echo "  lines=$count"
else
  echo "  file missing: $PROXY_FILE"
fi

echo ""
log "=== 4. Scan runtime (celery uses get_random_proxy -> Proxy model) ==="
compose exec -T celery python3 <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reNgine.settings")
import django
django.setup()
from reNgine.common_func import get_random_proxy

p = get_random_proxy()
print(f"get_random_proxy()={'(empty - proxy disabled or no list)' if not p else p[:80]+'...'}")
PY

echo ""
log "=== Summary ==="
cat <<'EOF'
  reNgine UI + scans read/write: scanEngine.models.Proxy (PostgreSQL)
  Scan tools NEVER read: proxy/data/proxies_curl.txt
  Urban module must run: make sync-once  (sync_django.py -> Proxy.save())
  Required format per line: http://user:pass@host:port
  Scan uses proxy only when: use_proxy=true AND proxies field non-empty
EOF
