#!/usr/bin/env bash
set -euo pipefail

pony_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_agenic_root() {
  local script_dir="${1:?missing script dir}"
  local candidate_root
  local project_wrapper
  local wrapped_bin

  candidate_root="$(cd "$script_dir/../.." && pwd)"
  if [[ -x "$candidate_root/scripts/install-project.sh" ]]; then
    printf '%s\n' "$candidate_root"
    return 0
  fi

  if [[ -n "${AGENIC_PONY_SOURCE_ROOT:-}" ]] && [[ -x "${AGENIC_PONY_SOURCE_ROOT}/scripts/install-project.sh" ]]; then
    cd "$AGENIC_PONY_SOURCE_ROOT" && pwd
    return 0
  fi

  project_wrapper="$candidate_root/pony/bin/codex-pony"
  if [[ -f "$project_wrapper" ]]; then
    wrapped_bin="$(sed -n 's#^exec "\(.*\)/pony/bin/codex-pony" "\$@"$#\1/pony/bin/codex-pony#p' "$project_wrapper" | head -n 1)"
    if [[ -n "$wrapped_bin" ]] && [[ -x "$wrapped_bin" ]]; then
      cd "$(dirname "$wrapped_bin")/../.." && pwd
      return 0
    fi
  fi

  printf '%s\n' "$candidate_root"
}

agenic_root="$(resolve_agenic_root "$pony_script_dir")"
export AGENIC_PONY_SOURCE_ROOT="$agenic_root"
pony_root="$agenic_root/pony"
pony_bin_dir="$pony_root/bin"
pony_scripts_dir="$pony_root/scripts"
pony_launch_prompts_dir="$pony_root/launch.prompts"

detect_project_root() {
  local start_dir="${1:-$PWD}"
  if git -C "$start_dir" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "$start_dir" rev-parse --show-toplevel
  else
    cd "$start_dir" && pwd
  fi
}

detect_project_branch() {
  local project_root="${1:?missing project root}"
  local branch=""
  if branch="$(git -C "$project_root" symbolic-ref --quiet --short HEAD 2>/dev/null)"; then
    printf '%s\n' "$branch"
    return 0
  fi
  if branch="$(git -C "$project_root" rev-parse --short HEAD 2>/dev/null)"; then
    printf 'detached-%s\n' "$branch"
    return 0
  fi
  printf 'no-git-branch\n'
}

project_slug() {
  local project_root="${1:?missing project root}"
  printf '%s' "$(basename "$project_root")" | tr -cs '[:alnum:]._+-' '-' | sed 's/^-*//; s/-*$//'
}

worker_slug_for_personality() {
  case "${1:-}" in
    TIA|CELESTIA|PRINCESS|CELLY|SUNBUTT|PRINCESS_CELESTIA_SOL_INVICTUS) printf 'celestia\n' ;;
    AJ|APPLEJACK) printf 'aj\n' ;;
    FS|FLUTTERSHY|SHY|FLUTTERS) printf 'fs\n' ;;
    PINKIE|PINKIE_PIE) printf 'pinkie\n' ;;
    RARITY|RARES) printf 'rarity\n' ;;
    RD|RAINBOW|RAINBOW_DASH|DASH) printf 'rd\n' ;;
    SPIKE) printf 'spike\n' ;;
    TWI|TWILIGHT|TWILIGHT_SPARKLE) printf 'twi\n' ;;
    *) return 1 ;;
  esac
}

worker_label_for_slug() {
  case "${1:-}" in
    celestia) printf 'Princess Celestia Sol Invictus\n' ;;
    aj) printf 'AJ\n' ;;
    fs) printf 'FS\n' ;;
    pinkie) printf 'Pinkie\n' ;;
    rarity) printf 'Rarity\n' ;;
    rd) printf 'RD\n' ;;
    spike) printf 'Spike\n' ;;
    twi) printf 'Twilight\n' ;;
    *) return 1 ;;
  esac
}

worker_personality_for_slug() {
  case "${1:-}" in
    celestia) printf 'PRINCESS_CELESTIA_SOL_INVICTUS\n' ;;
    aj) printf 'APPLEJACK\n' ;;
    fs) printf 'FLUTTERSHY\n' ;;
    pinkie) printf 'PINKIE_PIE\n' ;;
    rarity) printf 'RARITY\n' ;;
    rd) printf 'RAINBOW_DASH\n' ;;
    spike) printf 'SPIKE\n' ;;
    twi) printf 'TWILIGHT_SPARKLE\n' ;;
    *) return 1 ;;
  esac
}

workfile_name_for_slug() {
  case "${1:-}" in
    celestia) printf 'governor-celestia.md\n' ;;
    twi) printf 'coordinator-twi.md\n' ;;
    *) printf '%s.md\n' "${1:?missing worker slug}" ;;
  esac
}

worker_slug_for_label() {
  case "${1:-}" in
    Princess|Princess\ Celestia|Princess\ Celestia\ Sol\ Invictus) printf 'celestia\n' ;;
    AJ) printf 'aj\n' ;;
    FS) printf 'fs\n' ;;
    Pinkie) printf 'pinkie\n' ;;
    Rarity) printf 'rarity\n' ;;
    RD) printf 'rd\n' ;;
    Spike) printf 'spike\n' ;;
    Twilight) printf 'twi\n' ;;
    *) return 1 ;;
  esac
}

idle_sentinel_for_personality() {
  case "${1:-}" in
    TIA|CELESTIA|PRINCESS|CELLY|SUNBUTT|PRINCESS_CELESTIA_SOL_INVICTUS) printf 'Princess Celestia is tending the sun and awaiting new prompt instructions. Ω\n' ;;
    AJ|APPLEJACK) printf 'Applejack is bucking apples and awaiting new prompt instructions. Ω\n' ;;
    FS|FLUTTERSHY|SHY|FLUTTERS) printf 'Fluttershy is feeding her animals and awaiting new prompt instructions. Ω\n' ;;
    PINKIE|PINKIE_PIE) printf 'Pinkie Pie is baking a cake and awaiting new prompt instructions. Ω\n' ;;
    RARITY|RARES) printf 'Rarity is sewing a dress and awaiting new prompt instructions. Ω\n' ;;
    RD|RAINBOW|RAINBOW_DASH|DASH) printf 'Rainbow Dash is practicing tricks and awaiting new prompt instructions. Ω\n' ;;
    SPIKE) printf 'Spike is reading a comic and awaiting new prompt instructions. Ω\n' ;;
    TWI|TWILIGHT|TWILIGHT_SPARKLE) printf 'Twilight Sparkle is reading a book and awaiting new prompt instructions. Ω\n' ;;
    *) return 1 ;;
  esac
}

partial_idle_sentinel() {
  printf 'Ω\n'
}

load_project_paths() {
  local project_root="${1:-$PWD}"
  project_root="$(detect_project_root "$project_root")"

  export AGENIC_PROJECT_ROOT="$project_root"
  export AGENIC_PROJECT_BRANCH
  AGENIC_PROJECT_BRANCH="$(detect_project_branch "$project_root")"
  export AGENIC_PROJECT_NAME
  AGENIC_PROJECT_NAME="$(basename "$project_root")"
  export AGENIC_PROJECT_SLUG
  AGENIC_PROJECT_SLUG="$(project_slug "$project_root")"

  export AGENIC_PROJECT_PONY_DIR="$project_root/pony"
  export AGENIC_PROJECT_PONY_AGENTS_DIR="$AGENIC_PROJECT_PONY_DIR/agents"
  export AGENIC_PROJECT_PONY_ASSETS_DIR="$AGENIC_PROJECT_PONY_DIR/assets"
  export AGENIC_PROJECT_PONY_BIN_DIR="$AGENIC_PROJECT_PONY_DIR/bin"
  export AGENIC_PROJECT_PONY_SCRIPTS_DIR="$AGENIC_PROJECT_PONY_DIR/scripts"
  export AGENIC_PROJECT_PONY_VENDOR_DIR="$AGENIC_PROJECT_PONY_DIR/vendor"
  export AGENIC_PROJECT_PONY_LAUNCH_PROMPTS_DIR="$AGENIC_PROJECT_PONY_DIR/launch.prompts"
  export AGENIC_PROJECT_PONY_LAUNCH_CONFIGS_DIR="$AGENIC_PROJECT_PONY_DIR/launch.configs"
  export AGENIC_PROJECT_PONY_TEAM_COORDINATION_DIR="$AGENIC_PROJECT_PONY_DIR/team.coordination"
  export AGENIC_PROJECT_PONY_RUNTIME_DIR="$AGENIC_PROJECT_PONY_DIR/runtime"
  export AGENIC_PROJECT_PONY_WORK_DIR="$AGENIC_PROJECT_PONY_DIR/work"
  export AGENIC_PROJECT_PONY_WORKTREES_DIR="$AGENIC_PROJECT_PONY_DIR/worktrees"
  export AGENIC_PROJECT_PONY_CONFIG_PATH="$AGENIC_PROJECT_PONY_DIR/pony.system.config.yaml"

  export AGENIC_PROJECT_PONY_RUNTIME_QUEUE_DIR="$AGENIC_PROJECT_PONY_RUNTIME_DIR/queue"
  export AGENIC_PROJECT_PONY_RUNTIME_QUEUE_ITEMS_DIR="$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_DIR/items"
  export AGENIC_PROJECT_PONY_RUNTIME_STATE_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/runtime.state"
  export AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/user.draft"
  export AGENIC_PROJECT_PONY_RUNTIME_ACTIVE_PROMPT_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/active.prompt"
  export AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/pending.notice"
  export AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_SEEN_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/pending.notice.seen"

  export AGENIC_PROJECT_PONY_WINDOWS_WARP_MARKER="$AGENIC_PROJECT_PONY_DIR/pony.system.configured.windows.warp"
  export AGENIC_PROJECT_PONY_LINUX_SHELL_MARKER="$AGENIC_PROJECT_PONY_DIR/pony.system.configured.linux.shell"
  export AGENIC_PROJECT_PONY_MACOS_SHELL_MARKER="$AGENIC_PROJECT_PONY_DIR/pony.system.configured.macos.shell"

  export AGENIC_AGENT_WORK_DIR="$AGENIC_PROJECT_PONY_WORK_DIR"
  export AGENIC_TEAM_COORDINATION_DIR="$AGENIC_PROJECT_PONY_TEAM_COORDINATION_DIR"
}

project_pony_dirs() {
  printf '%s\n' \
    "$AGENIC_PROJECT_PONY_DIR" \
    "$AGENIC_PROJECT_PONY_AGENTS_DIR" \
    "$AGENIC_PROJECT_PONY_ASSETS_DIR" \
    "$AGENIC_PROJECT_PONY_BIN_DIR" \
    "$AGENIC_PROJECT_PONY_SCRIPTS_DIR" \
    "$AGENIC_PROJECT_PONY_VENDOR_DIR" \
    "$AGENIC_PROJECT_PONY_LAUNCH_PROMPTS_DIR" \
    "$AGENIC_PROJECT_PONY_LAUNCH_CONFIGS_DIR" \
    "$AGENIC_PROJECT_PONY_TEAM_COORDINATION_DIR" \
    "$AGENIC_PROJECT_PONY_RUNTIME_DIR" \
    "$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_DIR" \
    "$AGENIC_PROJECT_PONY_RUNTIME_QUEUE_ITEMS_DIR" \
    "$AGENIC_PROJECT_PONY_WORK_DIR" \
    "$AGENIC_PROJECT_PONY_WORKTREES_DIR"
}

pony_ensure_layout_dirs() {
  while IFS= read -r dir; do
    mkdir -p "$dir"
  done < <(project_pony_dirs)
}

pony_bin_path() {
  local name="${1:?missing pony bin name}"
  printf '%s\n' "$AGENIC_PROJECT_PONY_BIN_DIR/$name"
}

pony_script_path() {
  local name="${1:?missing pony script name}"
  printf '%s\n' "$AGENIC_PROJECT_PONY_SCRIPTS_DIR/$name"
}

pony_launch_prompt_path() {
  local name="${1:?missing pony launch prompt name}"
  printf '%s\n' "$AGENIC_PROJECT_PONY_LAUNCH_PROMPTS_DIR/$name"
}

pony_coordination_path() {
  local name="${1:?missing coordination filename}"
  printf '%s\n' "$AGENIC_TEAM_COORDINATION_DIR/$name"
}

pony_assignment_registry_path() {
  pony_coordination_path "assignment.registry.tsv"
}

pony_worker_status_path() {
  local worker_slug="${1:?missing worker slug}"
  pony_coordination_path "${worker_slug}.status.md"
}

pony_worker_mailbox_path() {
  local worker_slug="${1:?missing worker slug}"
  pony_coordination_path "${worker_slug}.mailbox.md"
}

pony_twi_todo_path() {
  pony_coordination_path "twi.todo.md"
}

pony_twi_decisions_path() {
  pony_coordination_path "twi.decisions.md"
}

pony_twi_event_stream_history_path() {
  pony_coordination_path "twi.event.stream.history.md"
}

pony_twi_review_needed_path() {
  pony_coordination_path "twi.review-needed"
}

pony_multi_agent_control_path() {
  pony_coordination_path "multi.agent.control.md"
}