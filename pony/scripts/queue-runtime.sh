#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"

project_hint="$(cd "$script_dir/../.." && pwd)"

init_runtime_paths() {
  if declare -F load_project_paths >/dev/null 2>&1; then
    load_project_paths "$project_hint"
    return 0
  fi

  local project_root="$project_hint"
  if git -C "$project_root" rev-parse --show-toplevel >/dev/null 2>&1; then
    project_root="$(git -C "$project_root" rev-parse --show-toplevel)"
  else
    project_root="$(cd "$project_root" && pwd)"
  fi

  export AGENIC_PROJECT_ROOT="$project_root"
  export AGENIC_PROJECT_PONY_DIR="$project_root/pony"
  export AGENIC_PROJECT_PONY_RUNTIME_DIR="$AGENIC_PROJECT_PONY_DIR/runtime"
  export AGENIC_PROJECT_PONY_RUNTIME_QUEUE_DIR="$AGENIC_PROJECT_PONY_RUNTIME_DIR/queue"
  export AGENIC_PROJECT_PONY_RUNTIME_QUEUE_ITEMS_DIR="$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_DIR/items"
  export AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/runtime.state"
  export AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/user.draft"
  export AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/active.prompt"
  export AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/pending.notice"
  export AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_SEEN_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/pending.notice.seen"
}

init_runtime_paths

ensure_runtime_layout() {
  mkdir -p \
    "$AGENIC_PROJECT_PONY_RUNTIME_DIR" \
    "$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_DIR" \
    "$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_ITEMS_DIR"

  [[ -f "$AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH" ]] || printf 'idle\n' >"$AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH"
  [[ -f "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH" ]] || : >"$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH"
  [[ -f "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_SEEN_PATH" ]] || : >"$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_SEEN_PATH"
  [[ -f "$AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH" ]] || : >"$AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH"
  [[ -f "$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH" ]] || : >"$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH"
}

next_queue_id() {
  local last_id_path="$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_DIR/last_id"
  local next_id=1
  if [[ -f "$last_id_path" ]]; then
    next_id="$(( $(cat "$last_id_path") + 1 ))"
  fi
  printf '%s\n' "$next_id" >"$last_id_path"
  printf '%06d\n' "$next_id"
}

queue_item_path() {
  local item_id="${1:?missing item id}"
  printf '%s/%s.env\n' "$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_ITEMS_DIR" "$item_id"
}

queue_body_path() {
  local item_id="${1:?missing item id}"
  printf '%s/%s.body.txt\n' "$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_ITEMS_DIR" "$item_id"
}

read_body_from_args_or_stdin() {
  if [[ $# -gt 0 ]]; then
    printf '%s' "$1"
  else
    cat
  fi
}

write_queue_item() {
  local source="${1:?missing source}"
  local requester="${2:-}"
  local body="${3:?missing body}"
  local item_id
  item_id="$(next_queue_id)"
  local created_at
  created_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local item_path
  item_path="$(queue_item_path "$item_id")"
  local body_path
  body_path="$(queue_body_path "$item_id")"

  cat >"$item_path" <<EOF
ITEM_ID='$item_id'
SOURCE='$source'
REQUESTER_IDENTITY='$requester'
CREATED_AT='$created_at'
BODY_PATH='$body_path'
EOF
  printf '%s' "$body" >"$body_path"
  printf '%s\n' "$item_id"
}

queue_ids() {
  find "$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_ITEMS_DIR" -maxdepth 1 -type f -name '*.env' -printf '%f\n' \
    | sed 's/\.env$//' \
    | sort
}

load_item() {
  local item_id="${1:?missing item id}"
  local item_path
  item_path="$(queue_item_path "$item_id")"
  [[ -f "$item_path" ]] || return 1
  # shellcheck disable=SC1090
  source "$item_path"
}

render_item() {
  local item_id="${1:?missing item id}"
  load_item "$item_id"
  local body
  body="$(cat "$BODY_PATH")"
  printf 'item_id=%s\tsource=%s\trequester=%s\tcreated_at=%s\tbody=%s\n' \
    "$ITEM_ID" "$SOURCE" "${REQUESTER_IDENTITY:-none}" "$CREATED_AT" "$body"
}

show_notice_for_item() {
  local item_id="${1:?missing item id}"
  load_item "$item_id"
  local body
  body="$(cat "$BODY_PATH")"
  if [[ "$SOURCE" == "agent" ]]; then
    if [[ -n "${REQUESTER_IDENTITY:-}" ]]; then
      printf 'Pending agent request from %s:\n%s\n' "$REQUESTER_IDENTITY" "$body"
    else
      printf 'Pending agent request:\n%s\n' "$body"
    fi
  fi
}

cmd_init() {
  ensure_runtime_layout
}

cmd_enqueue() {
  ensure_runtime_layout
  local source="${1:?missing source}"
  local requester="${2:-}"
  local body="${3:-}"
  if [[ -z "$body" ]]; then
    body="$(read_body_from_args_or_stdin)"
  fi
  write_queue_item "$source" "$requester" "$body"
}

cmd_list() {
  ensure_runtime_layout
  local item_id
  while IFS= read -r item_id; do
    [[ -n "$item_id" ]] || continue
    render_item "$item_id"
  done < <(queue_ids)
}

cmd_pending_notice() {
  ensure_runtime_layout
  : >"$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH"
  local item_id
  while IFS= read -r item_id; do
    [[ -n "$item_id" ]] || continue
    load_item "$item_id"
    if [[ "$SOURCE" == "agent" ]]; then
      show_notice_for_item "$item_id" | tee "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH"
      return 0
    fi
  done < <(queue_ids)
}

cmd_next() {
  ensure_runtime_layout
  local user_item=""
  local first_item=""
  local item_id
  while IFS= read -r item_id; do
    [[ -n "$item_id" ]] || continue
    if [[ -z "$first_item" ]]; then
      first_item="$item_id"
    fi
    load_item "$item_id"
    if [[ "$SOURCE" == "user" ]]; then
      user_item="$item_id"
      break
    fi
  done < <(queue_ids)

  local selected="${user_item:-$first_item}"
  [[ -n "$selected" ]] || return 0

  load_item "$selected"
  local state="running.agent.prompt"
  if [[ "$SOURCE" == "user" ]]; then
    state="running.prompt"
  fi
  printf '%s\n' "$state" >"$AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH"
  cat "$BODY_PATH" >"$AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH"
  printf '%s\n' "$selected"
}

cmd_pop() {
  ensure_runtime_layout
  local item_id="${1:?missing item id}"
  load_item "$item_id"
  rm -f "$(queue_item_path "$item_id")" "$BODY_PATH"
  if [[ ! -s "$AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH" ]]; then
    printf 'idle\n' >"$AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH"
  fi
}

cmd_complete() {
  ensure_runtime_layout
  : >"$AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH"
  printf 'idle\n' >"$AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH"
}

cmd_state_get() {
  ensure_runtime_layout
  cat "$AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH"
}

cmd_state_set() {
  ensure_runtime_layout
  local value="${1:?missing state}"
  printf '%s\n' "$value" >"$AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH"
}

cmd_draft_save() {
  ensure_runtime_layout
  read_body_from_args_or_stdin "${1:-}" >"$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH"
}

cmd_draft_load() {
  ensure_runtime_layout
  cat "$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH"
}

cmd_active_prompt() {
  ensure_runtime_layout
  cat "$AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH"
}

command="${1:-}"
shift || true

case "$command" in
  init) cmd_init "$@" ;;
  enqueue) cmd_enqueue "$@" ;;
  list) cmd_list "$@" ;;
  pending-notice) cmd_pending_notice "$@" ;;
  next) cmd_next "$@" ;;
  pop) cmd_pop "$@" ;;
  complete) cmd_complete "$@" ;;
  state-get) cmd_state_get "$@" ;;
  state-set) cmd_state_set "$@" ;;
  draft-save) cmd_draft_save "$@" ;;
  draft-load) cmd_draft_load "$@" ;;
  active-prompt) cmd_active_prompt "$@" ;;
  *)
    printf '%s\n' "Usage: $0 {init|enqueue|list|pending-notice|next|pop|complete|state-get|state-set|draft-save|draft-load|active-prompt}" >&2
    exit 1
    ;;
esac