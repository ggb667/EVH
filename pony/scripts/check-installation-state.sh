#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
resolver="$project_root/pony/scripts/resolve-system-root.sh"
unset AGENIC_PONY_SOURCE_ROOT
source_root="$("$resolver" "$project_root")"
export AGENIC_PONY_SOURCE_ROOT="$source_root"
exec "$source_root/pony/scripts/check-installation-state.sh" "$project_root"