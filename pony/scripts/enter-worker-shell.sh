#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
workfile="${2:?missing workfile}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"
load_project_paths "$(cd "$script_dir/../.." && pwd)"

cd "$AGENIC_PROJECT_ROOT"
exec env PATH="$AGENIC_PROJECT_PONY_BIN_DIR:$PATH" \
  zsh -i -c "export PERSONALITY='${personality}' WORKING_ON='${workfile}'; exec zsh -i"