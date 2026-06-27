#!/bin/sh
set -e

OUTPUT="${PROXY_OUTPUT:-/data/proxies_curl.txt}"
WORKERS="${WORKERS:-20}"
INTERVAL="${INTERVAL_MIN:-25}"

python3 /app/sync_proxies_to_db.py --watch --file "$OUTPUT" &
SYNC_PID=$!

cleanup() {
  kill "$SYNC_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

exec python3 /app/fetch_urban_proxies.py \
  --watch \
  -o "$OUTPUT" \
  --workers "$WORKERS" \
  --interval "$INTERVAL"
