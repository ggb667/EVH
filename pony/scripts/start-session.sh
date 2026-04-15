#!/usr/bin/env bash
set -euo pipefail
project_root="/home/ggb66/dev/EVH"
resolver="$project_root/pony/scripts/resolve-system-root.sh"
source_root="$("$resolver" "$project_root")"
export AGENIC_PONY_SOURCE_ROOT="$source_root"
exec "$source_root/pony/scripts/start-session.sh" "${1:?missing personality}" "$project_root"