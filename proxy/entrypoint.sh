#!/bin/sh
set -e

OUTPUT="${PROXY_OUTPUT:-/data/proxies_curl.txt}"
WORKERS="${WORKERS:-20}"
INTERVAL="${INTERVAL_MIN:-25}"

exec python3 /app/fetch_urban_proxies.py \
  --watch \
  -o "$OUTPUT" \
  --workers "$WORKERS" \
  --interval "$INTERVAL"
