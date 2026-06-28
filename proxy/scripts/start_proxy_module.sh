#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

start_proxy_module() {
  prepare_sync_script
  log "Starting urban-proxy-fetcher..."
  compose up -d --build urban-proxy-fetcher

  log "Recreating web + celery to apply proxy volume mounts..."
  compose up -d --force-recreate web celery
}
