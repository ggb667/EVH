#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
workfile="${2:?missing workfile}"
initial_prompt="${3-}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"
load_project_paths "$(cd "$script_dir/../.." && pwd)"
repo_codex_pony="$(pony_bin_path codex-pony)"

export PERSONALITY="$personality"
export WORKING_ON="$workfile"

echo "PERSONALITY=$PERSONALITY"
echo "WORKING_ON=$WORKING_ON"
pwd

if [[ -n "$initial_prompt" ]]; then
  echo "INITIAL_PROMPT=provided"
  exec "$repo_codex_pony" "$initial_prompt"
fi

exec "$repo_codex_pony"