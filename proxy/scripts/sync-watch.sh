#!/usr/bin/env bash
# Background loop: sync proxy file -> reNgine DB when file changes.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

INTERVAL="${SYNC_WATCH_INTERVAL:-60}"
log "Proxy DB sync watcher (every ${INTERVAL}s). Stop with: make down"

last_hash=""
while true; do
  if [[ -f "$PROXY_FILE" ]]; then
    hash="$(sha256sum "$PROXY_FILE" 2>/dev/null | awk '{print $1}' || true)"
    if [[ -n "$hash" && "$hash" != "$last_hash" ]]; then
      if bash "$PROXY_DIR/scripts/sync-once.sh" 2>&1; then
        last_hash="$hash"
      fi
    fi
  fi
  sleep "$INTERVAL"
done
