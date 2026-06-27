#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

require_docker
ensure_root_env

log "Stopping full reNgine stack and proxy module..."
cd "$ROOT_DIR"
make down
log "All services stopped."
