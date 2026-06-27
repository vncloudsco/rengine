#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_docker
ensure_root_env

compose logs --follow --tail=200 urban-proxy-fetcher
