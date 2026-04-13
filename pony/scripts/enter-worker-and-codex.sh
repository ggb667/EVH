#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
workfile="${2:?missing workfile}"
rootdir="${3:?missing rootdir}"
initial_prompt="${4-}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"
load_project_paths "$(cd "$script_dir/../.." && pwd)"
repo_codex_pony="$(pony_bin_path codex-pony)"

resolve_path() {
  local path="${1:-}"
  printf '%s\n' "$path"
}

dirty_fix_first_prompt() {
  local cleanup_prompt=""
  cleanup_prompt="Coordinator preflight detected a dirty worktree in ${rootdir}. First, inspect and reconcile or put away the pending local changes in that repo. Do not ignore them or defer that cleanup. After the worktree is in a deliberate state, continue with normal Twilight coordination behavior."
  if [[ -n "$initial_prompt" ]]; then
    printf '%s\n\n%s\n' "$cleanup_prompt" "$initial_prompt"
  else
    printf '%s\n' "$cleanup_prompt"
  fi
}

workfile="$(resolve_path "$workfile")"
rootdir="$(resolve_path "$rootdir")"

export PERSONALITY="$personality"
export WORKING_ON="$workfile"

if [[ ! -f "$workfile" ]]; then
  echo "ERROR: workfile not found: $workfile" >&2
  exit 1
fi

cd "$rootdir"
preflight_result="$(
  "$(pony_script_path worker-preflight.sh)" \
    "$PERSONALITY" \
    "$WORKING_ON" \
    "$PWD"
)"

profile=""
prompt="$initial_prompt"

case "$preflight_result" in
  READY_NO_LLM)
    profile=""
    ;;
  BLOCKED_DIRTY_FIX_FIRST)
    if [[ "$PERSONALITY" == 'TWILIGHT_SPARKLE' || "$PERSONALITY" == 'PRINCESS_CELESTIA_SOL_INVICTUS' ]]; then
      profile='twi_coordinator'
      prompt="$(dirty_fix_first_prompt)"
    else
      echo 'Only Twilight may continue from BLOCKED_DIRTY_FIX_FIRST.'
      exit 0
    fi
    ;;
  ESCALATE_MINI)
    profile='worker_mini'
    ;;
  ESCALATE_TWI)
    if [[ "$PERSONALITY" == 'TWILIGHT_SPARKLE' || "$PERSONALITY" == 'PRINCESS_CELESTIA_SOL_INVICTUS' ]]; then
      profile='twi_coordinator'
    else
      echo 'Preflight: ESCALATE_TWI. Worker Codex not launched.'
      exit 0
    fi
    ;;
  *)
    echo "Preflight error: unexpected result '$preflight_result'."
    exit 1
    ;;
esac

if [[ -n "$profile" ]]; then
  exec "$repo_codex_pony" -p "$profile" "$prompt"
fi

exec "$repo_codex_pony" "$prompt"