#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

parse_args "$@"
require_docker
ensure_root_env
mkdir -p "$DATA_DIR"

if ! is_rengine_core_running; then
  log "reNgine core is not running — bootstrapping full stack..."
  source "$PROXY_DIR/scripts/bootstrap_rengine.sh"
  bootstrap_rengine_full
  wait_for_db_ready
  wait_for_web_migrations
  prompt_or_hint_username
else
  log "reNgine core already running — starting proxy module only."
fi

source "$PROXY_DIR/scripts/start_proxy_module.sh"
start_proxy_module

wait_for_proxy_file 300
bash "$PROXY_DIR/scripts/sync-once.sh" || log "Sync failed — retry: make sync-once"

if [[ "${URBAN_PROXY_SYNC_WATCH:-true}" == "true" ]]; then
  nohup bash "$PROXY_DIR/scripts/sync-watch.sh" >>"$PROXY_DIR/data/sync-watch.log" 2>&1 &
  log "Background DB sync watcher started (log: proxy/data/sync-watch.log)"
fi

source "$PROXY_DIR/scripts/print_ready.sh"
print_ready_message
