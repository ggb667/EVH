#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
workfile="${2:?missing workfile}"
rootdir="${3:?missing rootdir}"
promptfile="${4:?missing prompt file}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"
load_project_paths "$(cd "$script_dir/../.." && pwd)"
registry_file="$(pony_assignment_registry_path)"

resolve_path() {
  local path="${1:-}"
  if [[ -e "$path" ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$path"
  fi
}

find_auto_switch_target() {
  local worker_label="${1:?missing worker label}"

  [[ -f "$registry_file" ]] || return 0

  python3 - "$worker_label" "$rootdir" "$workfile" "$registry_file" "$AGENIC_TEAM_COORDINATION_DIR" <<'PY'
import csv
import sys
from pathlib import Path

worker_label, current_root, current_work, registry_path, coord_dir = sys.argv[1:]
rows = list(csv.DictReader(Path(registry_path).open(), delimiter='\t'))
coord_dir = Path(coord_dir)
current = None
alternates = []
slug_map = {
    'AJ': 'aj',
    'FS': 'fs',
    'Pinkie': 'pinkie',
    'Rarity': 'rarity',
    'RD': 'rd',
    'Spike': 'spike',
    'Twilight': 'twi',
}

for row in rows:
    if row['worker_label'] != worker_label:
        continue
    slug = slug_map.get(row['worker_label'])
    status = 'PROCEED'
    branch_verified = 'yes'
    if slug:
        status_file = coord_dir / f'{slug}.status.md'
        if status_file.exists():
            for line in status_file.read_text().splitlines():
                if line.startswith('STATUS: '):
                    status = line.split(': ', 1)[1].strip()
                elif line.startswith('BRANCH_VERIFIED: '):
                    branch_verified = line.split(': ', 1)[1].strip().lower()
    if branch_verified != 'yes' and status == 'PROCEED':
        status = 'HOLD'
    item = (row['assignment_id'], row['worktree'], row['workfile'], row['promptfile'], status)
    if row['worktree'] == current_root and row['workfile'] == current_work:
        current = item
    else:
        alternates.append(item)

if current is None or current[4] in {'PROCEED', 'WAITING'}:
    raise SystemExit(0)

proceed = [item for item in alternates if item[4] == 'PROCEED']
if len(proceed) == 1:
    current_id = current[0]
    alternate_id, worktree, workfile, promptfile, _ = proceed[0]
    print(f"{current_id}\t{alternate_id}\t{worktree}\t{workfile}\t{promptfile}")
PY
}

workfile="$(resolve_path "$workfile")"
rootdir="$(resolve_path "$rootdir")"
promptfile="$(resolve_path "$promptfile")"

worker_slug="$(worker_slug_for_personality "$personality" || true)"
if [[ -n "$worker_slug" ]]; then
  worker_label="$(worker_label_for_slug "$worker_slug")"
  auto_switch_target="$(find_auto_switch_target "$worker_label")"
  if [[ -n "$auto_switch_target" ]]; then
    IFS=$'\t' read -r current_assignment_id alternate_assignment_id alternate_rootdir alternate_workfile alternate_promptfile <<<"$auto_switch_target"
    echo "Launcher: ${current_assignment_id} is not PROCEED; switching to ${alternate_assignment_id}."
    exec "$0" "$personality" "$alternate_workfile" "$alternate_rootdir" "$alternate_promptfile"
  fi
fi

if [[ ! -f "$promptfile" ]]; then
  echo "ERROR: prompt file not found: $promptfile" >&2
  exit 1
fi

prompt="$(<"$promptfile")"

exec "$(pony_script_path enter-worker-and-codex.sh)" \
  "$personality" \
  "$workfile" \
  "$rootdir" \
  "$prompt"