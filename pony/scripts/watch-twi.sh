#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/pony-paths.sh"
load_project_paths "$(cd "$script_dir/../.." && pwd)"

coord_dir="$AGENIC_TEAM_COORDINATION_DIR"
inbox="$(pony_twi_event_stream_history_path)"
decisions="$(pony_twi_decisions_path)"
todo="$(pony_twi_todo_path)"
flag="$(pony_twi_review_needed_path)"

pony_ensure_layout_dirs
touch "$inbox" "$decisions" "$todo" "$flag"

is_twilight_owned_trigger() {
  case "${1:-}" in
    multi.agent.control.md|twi.status.md)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

normalize_worker_to_personality() {
  local worker="${1:-}"
  case "$(printf '%s' "$worker" | tr '[:lower:]' '[:upper:]')" in
    TWI|TWILIGHT|TWILIGHT_SPARKLE) printf 'TWILIGHT_SPARKLE' ;;
    DASH|DASHIE|RAINBOW|RD|RAINBOW_DASH) printf 'RAINBOW_DASH' ;;
    PINKIE|PINKIE_PIE) printf 'PINKIE_PIE' ;;
    RARES|RARITY) printf 'RARITY' ;;
    AJ|APPLEJACK) printf 'APPLEJACK' ;;
    SHY|FLUTTERS|FLUTTERSHY) printf 'FLUTTERSHY' ;;
    SPIKE) printf 'SPIKE' ;;
    *) printf 'TWILIGHT_SPARKLE' ;;
  esac
}

normalize_pending_field() {
  local value="${1:-}"
  local lower
  lower="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  if [[ -z "$lower" || "$lower" == "none" || "$lower" == "n/a" ]]; then
    return 1
  fi
  printf '%s' "$value"
}

has_pending_twilight_request() {
  local status_file="$1"
  local question
  local decision_needed

  [[ -f "$status_file" ]] || return 1
  question="$(sed -n 's/^QUESTIONS_FOR_TWI: //p' "$status_file" | head -n1)"
  decision_needed="$(sed -n 's/^DECISION_NEEDED: //p' "$status_file" | head -n1)"
  question="$(normalize_pending_field "$question" || true)"
  decision_needed="$(normalize_pending_field "$decision_needed" || true)"

  if [[ -z "$question" && -z "$decision_needed" ]]; then
    return 1
  fi
  if [[ -f "$decisions" && "$decisions" -nt "$status_file" ]]; then
    return 1
  fi
  return 0
}

material_change_marker() {
  local status_file="$1"
  local summary

  [[ -f "$status_file" ]] || return 1
  summary="$(rg -n "^(BRANCH|WORKTREE|STATUS|FILES_PLANNED|FILES_TOUCHED|BLOCKERS|NEXT_STEP|QUESTIONS_FOR_TWI|DECISION_NEEDED):" "$status_file" || true)"
  [[ -n "$summary" ]] || return 1
  printf '%s' "$summary" | sha256sum | awk '{print $1}'
}

refresh_todo() {
  {
    echo "# TWILIGHT TODO"
    echo
    echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    found=0
    for status_file in "$coord_dir"/*.status.md; do
      [[ -f "$status_file" ]] || continue
      worker="$(basename "$status_file" .status.md)"
      branch="$(sed -n 's/^BRANCH: //p' "$status_file")"
      worktree="$(sed -n 's/^WORKTREE: //p' "$status_file")"
      status="$(sed -n 's/^STATUS: //p' "$status_file")"
      question="$(normalize_pending_field "$(sed -n 's/^QUESTIONS_FOR_TWI: //p' "$status_file")" || true)"
      decision_needed="$(normalize_pending_field "$(sed -n 's/^DECISION_NEEDED: //p' "$status_file")" || true)"

      if has_pending_twilight_request "$status_file"; then
        found=1
        echo "## ${worker^^}"
        echo "- branch: ${branch:-unknown}"
        echo "- worktree: ${worktree:-unknown}"
        echo "- status: ${status:-unknown}"
        [[ -n "$question" ]] && echo "- question: $question"
        [[ -n "$decision_needed" ]] && echo "- decision_needed: $decision_needed"
        echo
      fi
    done

    if [[ "$found" -eq 0 ]]; then
      echo "No pending Twilight questions or decisions."
    fi
  } >"$todo"
}

maybe_play_done() {
  local status_file="$1"
  local worker status next_step decision_needed marker personality

  [[ -f "$status_file" ]] || return 0
  worker="$(basename "$status_file" .status.md)"
  status="$(sed -n 's/^STATUS: //p' "$status_file" | head -n1 | tr '[:upper:]' '[:lower:]')"
  next_step="$(sed -n 's/^NEXT_STEP: //p' "$status_file" | head -n1 | tr '[:upper:]' '[:lower:]')"
  decision_needed="$(sed -n 's/^DECISION_NEEDED: //p' "$status_file" | head -n1 | tr '[:upper:]' '[:lower:]')"
  marker="$coord_dir/.${worker}.done_sound_played"

  if [[ "$status" == "done" ]] &&
     [[ -z "$next_step" || "$next_step" == "none" || "$next_step" == "n/a" ]] &&
     [[ -z "$decision_needed" || "$decision_needed" == "none" || "$decision_needed" == "n/a" ]]; then
    if [[ ! -f "$marker" ]]; then
      personality="$(normalize_worker_to_personality "$worker")"
      "$(pony_bin_path ponydone)" "$personality" || true
      touch "$marker"
    fi
  else
    rm -f "$marker"
  fi
}

echo "Watching $coord_dir for worker status changes..."

inotifywait -m -e close_write,move,create "$coord_dir" --format '%f' | while read -r file; do
  case "$file" in
    *.status.md|multi.agent.control.md)
      if is_twilight_owned_trigger "$file"; then
        refresh_todo
        continue
      fi

      ts="$(date '+%Y-%m-%d %H:%M:%S')"
      changed_path="$coord_dir/$file"
      marker_file="$coord_dir/.${file}.last-review-hash"
      current_hash="$(material_change_marker "$changed_path" || true)"
      previous_hash="$(cat "$marker_file" 2>/dev/null || true)"

      if [[ -n "$current_hash" && "$current_hash" != "$previous_hash" ]]; then
        review_block="$(
          echo "## $ts"
          echo "- changed_file: $file"
          echo "- action: Twilight review needed"
          if [[ -f "$changed_path" ]]; then
            rg -n "^(BRANCH|WORKTREE|STATUS|FILES_PLANNED|FILES_TOUCHED|BLOCKERS|NEXT_STEP|QUESTIONS_FOR_TWI|DECISION_NEEDED):" "$changed_path" || true
          fi
          echo
        )"
        printf '%s\n' "$review_block" >>"$inbox"
        printf '%s\n' "$current_hash" >"$marker_file"
      fi

      refresh_todo
      maybe_play_done "$changed_path"
      touch "$flag"

      if [[ "$file" == *.status.md ]] && has_pending_twilight_request "$changed_path"; then
        PERSONALITY=TWILIGHT_SPARKLE "$(pony_bin_path ponyalert)" || true
      fi

      printf '\n[TWI REVIEW NEEDED] %s changed\n' "$file"
      ;;
    *)
      ;;
  esac
done