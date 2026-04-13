#!/usr/bin/env bash
set -euo pipefail

personality="${1:-}"
workfile="${2:-}"
rootdir="${3:-}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"
load_project_paths "$(cd "$script_dir/../.." && pwd)"
registry_file="$(pony_assignment_registry_path)"

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

compute_push_status() {
  local git_status="$1"
  local upstream_ref=""
  local counts=""
  local ahead=""
  local behind=""

  if [[ -n "$git_status" ]]; then
    printf 'uncommitted_local_changes\n'
    return 0
  fi

  upstream_ref="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  if [[ -z "$upstream_ref" ]]; then
    printf 'clean_no_upstream\n'
    return 0
  fi

  counts="$(git rev-list --left-right --count "${upstream_ref}...HEAD" 2>/dev/null || true)"
  if [[ -z "$counts" ]]; then
    printf 'clean_with_unknown_remote_state\n'
    return 0
  fi

  read -r behind ahead <<<"$counts"
  if [[ "$ahead" == "0" && "$behind" == "0" ]]; then
    printf 'clean_and_pushed\n'
  elif [[ "$ahead" != "0" && "$behind" == "0" ]]; then
    printf 'clean_local_commits_not_pushed\n'
  elif [[ "$ahead" == "0" && "$behind" != "0" ]]; then
    printf 'clean_behind_upstream\n'
  else
    printf 'clean_diverged_from_upstream\n'
  fi
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
    print("\t".join([row['assignment_id'], row['worker_label'], row['branch'], row['worktree']]))
PY
)"

worker_slug="$(worker_slug_for_personality "$personality" || true)"
status_file=""
expected_branch=""
if [[ -n "$worker_slug" ]]; then
  status_file="$(pony_worker_status_path "$worker_slug")"
fi
if [[ -n "$assignment_row" ]]; then
  IFS=$'\t' read -r assignment_id worker_label expected_branch expected_worktree <<<"$assignment_row"
fi

if [[ -z "$rootdir" || ! -d "$rootdir" ]]; then
  printf 'Postflight skipped: invalid rootdir %s\n' "${rootdir:-<empty>}" >&2
  exit 0
fi

cd "$rootdir"
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  printf 'Postflight skipped: %s is not a git worktree\n' "$rootdir" >&2
  exit 0
fi

git_branch="$(git branch --show-current 2>/dev/null || true)"
git_status="$(git status --short 2>/dev/null || true)"
push_status="$(compute_push_status "$git_status")"
branch_verified="no"
if [[ -n "$expected_branch" && "$git_branch" == "$expected_branch" ]]; then
  branch_verified="yes"
fi

if [[ -n "$status_file" && -f "$status_file" ]]; then
  update_field "BRANCH" "${git_branch:-unknown}" "$status_file"
  update_field "WORKTREE" "$rootdir" "$status_file"
  update_field "BRANCH_VERIFIED" "$branch_verified" "$status_file"
  update_field "PUSH_STATUS" "$push_status" "$status_file"
fi

printf 'Postflight: personality=%s branch=%s push_status=%s workfile=%s\n' \
  "${personality:-unknown}" \
  "${git_branch:-unknown}" \
  "$push_status" \
  "${workfile:-unknown}"