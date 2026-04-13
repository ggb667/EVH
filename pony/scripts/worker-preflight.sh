#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
workfile="${2:?missing workfile}"
rootdir="${3:?missing rootdir}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"
load_project_paths "$(cd "$script_dir/../.." && pwd)"
registry_file="$(pony_assignment_registry_path)"
pwd_now="$(pwd -P)"

trim_block() {
  sed -e 's/^[[:space:]-]*//' -e 's/[[:space:]]*$//' | sed '/^$/d'
}

field_block() {
  local key="$1"
  local file="$2"
  awk -v key="$key" '
    index($0, key ":") == 1 {
      sub("^" key ": ?", "", $0)
      print
      capture = 1
      next
    }
    capture && /^[A-Z_]+:/ { exit }
    capture { print }
  ' "$file"
}

normalize_field() {
  tr '[:upper:]' '[:lower:]' | trim_block
}

field_is_empty() {
  local value
  value="$(printf '%s\n' "$1" | normalize_field)"
  [[ -z "$value" || "$value" == "none" || "$value" == "no decision needed." || "$value" == "no decision needed" || "$value" == "n/a" ]]
}

status_indicates_ready_no_llm() {
  local status_value="$1"
  local next_step="$2"
  local blockers="$3"
  local normalized_status
  local combined

  normalized_status="$(printf '%s\n' "$status_value" | normalize_field)"
  case "$normalized_status" in
    waiting|hold|blocked|done|awaiting_review|awaiting\ review)
      return 0
      ;;
  esac
  if [[ -n "$normalized_status" ]]; then
    return 1
  fi

  combined="$(printf '%s\n%s\n%s\n' "$status_value" "$next_step" "$blockers" | normalize_field)"
  [[ "$combined" == *"no immediate action"* ]] && return 0
  [[ "$combined" == *"await merge review"* || "$combined" == *"await review"* ]] && return 0
  [[ "$combined" == *"wait for twilight review"* || "$combined" == *"wait for post-approval"* ]] && return 0
  [[ "$combined" == *"already landed on \`main\`"* || "$combined" == *"already landed on main"* ]] && return 0
  return 1
}

update_field() {
  local key="$1"
  local value="$2"
  local file="$3"
  local tmp

  tmp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, key ":") == 1 {
      print key ": " value
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) {
        print key ": " value
      }
    }
  ' "$file" >"$tmp"
  mv "$tmp" "$file"
}

set_status_context() {
  local status_file="$1"
  local branch_value="$2"
  local worktree_value="$3"
  local verified_value="$4"

  [[ -n "$status_file" && -f "$status_file" ]] || return 0
  update_field "BRANCH" "$branch_value" "$status_file"
  update_field "WORKTREE" "$worktree_value" "$status_file"
  update_field "BRANCH_VERIFIED" "$verified_value" "$status_file"
}

set_push_status() {
  local status_file="$1"
  local push_status_value="$2"
  [[ -n "$status_file" && -f "$status_file" ]] || return 0
  update_field "PUSH_STATUS" "$push_status_value" "$status_file"
}

set_unambiguous_hold() {
  local status_file="$1"
  local blockers="$2"
  local next_step="$3"

  [[ -n "$status_file" && -f "$status_file" ]] || return 0
  update_field "STATUS" "HOLD" "$status_file"
  update_field "BLOCKERS" "$blockers" "$status_file"
  update_field "NEXT_STEP" "$next_step" "$status_file"
}

assignment_row="$(
  python3 - "$registry_file" "$personality" "$rootdir" "$workfile" <<'PY'
import csv
import sys
from pathlib import Path

registry_path, personality, rootdir, workfile = sys.argv[1:]
rows = list(csv.DictReader(Path(registry_path).open(), delimiter='\t')) if Path(registry_path).exists() else []

matches = [row for row in rows if row['personality'] == personality and row['worktree'] == rootdir and row['workfile'] == workfile]
if not matches:
    matches = [row for row in rows if row['personality'] == personality and row['workfile'] == workfile]
if not matches:
    matches = [row for row in rows if row['personality'] == personality]
if len(matches) == 1:
    row = matches[0]
    print("\t".join([
        row['assignment_id'],
        row['worker_label'],
        row['branch'],
        row['worktree'],
        row['workfile'],
        row['promptfile'],
    ]))
PY
)"

worker_slug="$(worker_slug_for_personality "$personality" || true)"
status_file=""
expected_branch=""
expected_worktree="$rootdir"
is_coordinator=0
status_branch=""
status_worktree=""

if [[ -n "$worker_slug" ]]; then
  status_file="$(pony_worker_status_path "$worker_slug")"
  if [[ "$worker_slug" == "twi" || "$worker_slug" == "celestia" ]]; then
    is_coordinator=1
  fi
fi

if [[ -n "$assignment_row" ]]; then
  IFS=$'\t' read -r assignment_id worker_label expected_branch expected_worktree expected_workfile expected_promptfile <<<"$assignment_row"
fi

if [[ -n "$status_file" && -f "$status_file" ]]; then
  status_branch="$(field_block "BRANCH" "$status_file" | trim_block | head -n 1)"
  status_worktree="$(field_block "WORKTREE" "$status_file" | trim_block | head -n 1)"
fi

if [[ "$rootdir" == "$AGENIC_PROJECT_ROOT" ]] && [[ -n "$status_worktree" && "$status_worktree" == "$rootdir" ]]; then
  expected_worktree="$rootdir"
  if [[ -n "$status_branch" ]]; then
    expected_branch="$status_branch"
  fi
fi

if [[ -n "$expected_worktree" ]] && [[ ! -d "$expected_worktree" ]] && [[ "$rootdir" == "$AGENIC_PROJECT_ROOT" ]]; then
  expected_worktree="$rootdir"
  expected_branch=""
fi

if [[ ! -f "$workfile" || ! -d "$rootdir" || -z "$status_file" || ! -f "$status_file" ]]; then
  printf 'ESCALATE_TWI\n'
  exit 0
fi

if [[ "$pwd_now" != "$expected_worktree" ]]; then
  set_status_context "$status_file" "${expected_branch:-unknown}" "$pwd_now" "no"
  if (( ! is_coordinator )); then
    set_unambiguous_hold \
      "$status_file" \
      "preflight: expected worktree $expected_worktree but found $pwd_now" \
      "return to $expected_worktree before launching Codex, then retry preflight"
  fi
  printf 'ESCALATE_TWI\n'
  exit 0
fi

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  set_status_context "$status_file" "${expected_branch:-unknown}" "$pwd_now" "no"
  printf 'ESCALATE_TWI\n'
  exit 0
fi

git_branch="$(git branch --show-current 2>/dev/null || true)"
git_status="$(git status --short 2>/dev/null || true)"

if [[ -n "$expected_branch" ]] && [[ -z "$git_branch" || "$git_branch" != "$expected_branch" ]]; then
  if (( ! is_coordinator )) && [[ -z "$git_status" ]] && git show-ref --verify --quiet "refs/heads/$expected_branch"; then
    git switch "$expected_branch" >/dev/null 2>&1 || true
    git_branch="$(git branch --show-current 2>/dev/null || true)"
    git_status="$(git status --short 2>/dev/null || true)"
  fi
fi

if [[ -n "$expected_branch" ]] && [[ -z "$git_branch" || "$git_branch" != "$expected_branch" ]]; then
  set_status_context "$status_file" "${git_branch:-unknown}" "$pwd_now" "no"
  if (( ! is_coordinator )); then
    set_unambiguous_hold \
      "$status_file" \
      "preflight: expected branch $expected_branch in $expected_worktree but found ${git_branch:-unknown}" \
      "stay on $expected_worktree, resolve the branch mismatch, and request Twilight review if correction is not obvious"
  fi
  printf 'ESCALATE_TWI\n'
  exit 0
fi

set_status_context "$status_file" "${git_branch:-unknown}" "$pwd_now" "yes"

if (( is_coordinator )); then
  if [[ "$rootdir" != "$AGENIC_PROJECT_ROOT" ]]; then
    if [[ -n "$git_status" ]]; then
      set_push_status "$status_file" "project_local_runtime_state"
    else
      set_push_status "$status_file" "clean_local_branch"
    fi
    printf 'ESCALATE_TWI\n'
    exit 0
  fi

  if [[ -n "$git_status" ]]; then
    set_push_status "$status_file" "uncommitted_local_changes"
    update_field "STATUS" "HOLD" "$status_file"
    update_field "BLOCKERS" "preflight: coordinator worktree is dirty; Twilight must reconcile or put away local changes before normal coordination work" "$status_file"
    update_field "NEXT_STEP" "launch Twilight in dirty-fix-first mode, put away or reconcile the pending changes, then continue with normal coordination work" "$status_file"
    printf 'BLOCKED_DIRTY_FIX_FIRST\n'
    exit 0
  fi

  set_push_status "$status_file" "clean_and_pushed"
  printf 'ESCALATE_TWI\n'
  exit 0
fi

decision_needed="$(field_block "DECISION_NEEDED" "$status_file")"
questions_for_twi="$(field_block "QUESTIONS_FOR_TWI" "$status_file")"
status_value="$(field_block "STATUS" "$status_file")"
next_step="$(field_block "NEXT_STEP" "$status_file")"
blockers="$(field_block "BLOCKERS" "$status_file")"

if ! field_is_empty "$decision_needed" || ! field_is_empty "$questions_for_twi"; then
  printf 'ESCALATE_TWI\n'
  exit 0
fi

if [[ -z "$git_status" ]] && status_indicates_ready_no_llm "$status_value" "$next_step" "$blockers"; then
  printf 'READY_NO_LLM\n'
else
  printf 'ESCALATE_MINI\n'
fi