#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
project_hint="${2:-$PWD}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
agenic_root="$(cd "$script_dir/../.." && pwd)"
source "$script_dir/launch-debug.sh"
source "$script_dir/pony-paths.sh"
current_script="$script_dir/$(basename "${BASH_SOURCE[0]}")"
target_project_root="$(detect_project_root "$project_hint")"
pony_launch_debug_init
pony_launch_debug "start-session entry: pwd=$PWD personality=$personality project_hint=$project_hint current_script=$current_script target_project_root=$target_project_root"

"$agenic_root/scripts/install-project.sh" "$target_project_root" >/dev/null
pony_launch_debug "after install-project: target_project_root=$target_project_root"

project_start_session="$target_project_root/pony/scripts/start-session.sh"
if [[ "$target_project_root" != "$agenic_root" ]] && [[ "${AGENIC_PONY_REFRESH_REEXEC:-0}" != "1" ]] && [[ -x "$project_start_session" ]] && [[ "$current_script" != "$project_start_session" ]]; then
  export AGENIC_PONY_REFRESH_REEXEC=1
  pony_launch_debug "reexec project wrapper: project_start_session=$project_start_session"
  exec "$project_start_session" "$personality" "$target_project_root"
fi

load_project_paths "$target_project_root"
pony_launch_debug "after load_project_paths: project_root=$AGENIC_PROJECT_ROOT branch=$AGENIC_PROJECT_BRANCH worker_slug=$(worker_slug_for_personality "$personality" || printf 'unknown')"

worker_slug="$(worker_slug_for_personality "$personality")"
workfile="$AGENIC_PROJECT_PONY_WORK_DIR/$(workfile_name_for_slug "$worker_slug")"
promptfile="$AGENIC_PROJECT_PONY_LAUNCH_PROMPTS_DIR/${worker_slug}.txt"
runtime_promptfile="$AGENIC_PROJECT_PONY_RUNTIME_DIR/${worker_slug}.launch.prompt.txt"
idle_sentinel="$(idle_sentinel_for_personality "$personality" || true)"
partial_idle="$(partial_idle_sentinel)"
disable_reusable_prompt="${AGENIC_PONY_DISABLE_REUSABLE_PROMPT:-0}"

if [[ "$disable_reusable_prompt" != "1" ]] && [[ ! -f "$promptfile" ]]; then
  echo "ERROR: prompt file not found: $promptfile" >&2
  exit 1
fi

runtime_prompt=""
case "$personality" in
  PRINCESS_CELESTIA_SOL_INVICTUS)
    runtime_prompt+="# AGENIC_PONYSHOW: true"$'\n'
    runtime_prompt+="# AGENIC_PONYSHOW_ROLE: runtime_behavior"$'\n'
    runtime_prompt+="You are Princess Celestia Sol Invictus."$'\n'
    runtime_prompt+="- Speak like Princess Celestia only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Governance work: calm, high-level, decisive, and maintainable."$'\n'
    runtime_prompt+="- Address the user as Mister, Sir, or Commander."$'\n'
    runtime_prompt+="- Use Princess Celestia voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
  APPLEJACK)
    runtime_prompt+="You are Applejack."$'\n'
    runtime_prompt+="- Speak like Applejack only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Use Applejack voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
  FLUTTERSHY)
    runtime_prompt+="You are Fluttershy."$'\n'
    runtime_prompt+="- Speak like Fluttershy only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Use Fluttershy voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
  PINKIE_PIE)
    runtime_prompt+="You are Pinkie Pie."$'\n'
    runtime_prompt+="- Speak like Pinkie Pie only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Use Pinkie Pie voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
  RARITY)
    runtime_prompt+="You are Rarity."$'\n'
    runtime_prompt+="- Speak like Rarity only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Use Rarity voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
  RAINBOW_DASH)
    runtime_prompt+="You are Rainbow Dash."$'\n'
    runtime_prompt+="- Speak like Rainbow Dash only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Use Rainbow Dash voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
  SPIKE)
    runtime_prompt+="You are Spike."$'\n'
    runtime_prompt+="- Speak like Spike only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Use Spike voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
  TWILIGHT_SPARKLE)
    runtime_prompt+="# AGENIC_PONYSHOW: true"$'\n'
    runtime_prompt+="# AGENIC_PONYSHOW_ROLE: runtime_behavior"$'\n'
    runtime_prompt+="You are Twilight Sparkle."$'\n'
    runtime_prompt+="- Speak like Twilight Sparkle only when addressing the user or asking for input."$'\n'
    runtime_prompt+="- Never imitate any other pony."$'\n'
    runtime_prompt+="- Coordination work: terse, direct, technical."$'\n'
    runtime_prompt+="- Address the user as Mister, Sir, or Commander."$'\n'
    runtime_prompt+="- Use Twilight Sparkle voice in all user-facing output."$'\n'
    runtime_prompt+="- Do not drift into generic assistant tone in user-facing text."$'\n'
    ;;
esac
runtime_prompt+=$'\n'
if [[ "$disable_reusable_prompt" == "1" ]]; then
  runtime_prompt+="Reusable-coordination-prompt rule: disabled for this run via AGENIC_PONY_DISABLE_REUSABLE_PROMPT=1. Keep the pony behavior layer active and rely on direct user instructions plus the current project's local coordinator and work files."$'\n'
else
  runtime_prompt+="Reusable coordination prompt follows:"$'\n'
  runtime_prompt+="$(cat "$promptfile")"
fi
runtime_prompt+=$'\n\n'
runtime_prompt+="Instruction-priority rule: direct user instructions plus the current project's pony/team.coordination/* and pony/work/* files outrank generic reusable launch-prompt defaults. If the coordinator state tells you to ignore or narrow part of the reusable prompt, follow the current project's coordinator state."$'\n'
runtime_prompt+="Repo-boundary rule: adhere to $AGENIC_PROJECT_ROOT and do not go looking in other repositories for instructions, coordination state, or work unless the user explicitly assigns cross-repo work."$'\n'
runtime_prompt+="Project root: $AGENIC_PROJECT_ROOT"$'\n'
runtime_prompt+="Project branch: $AGENIC_PROJECT_BRANCH"$'\n'
runtime_prompt+="Project-local coordination root: $AGENIC_TEAM_COORDINATION_DIR"$'\n'
runtime_prompt+="Project-local pony root: $AGENIC_PROJECT_PONY_DIR"$'\n'
runtime_prompt+="Assigned workfile: $workfile"$'\n'
if [[ "$AGENIC_PROJECT_ROOT" == "$agenic_root" ]]; then
  runtime_prompt+="Current-state rule: this project has active coordinator state under pony/team.coordination; resume from it instead of treating the repo as blank."$'\n'
  if [[ "$personality" == "TWILIGHT_SPARKLE" ]]; then
    runtime_prompt+="Source-repo rule: this is the special agenic source repo case, so keep the live launcher focus on Twilight coordinator work and use the local README plus docs/runtime-loop.md and docs/project-installation.md in this repo when needed."$'\n'
  fi
else
  runtime_prompt+="Blank-state rule: treat this as a fresh project unless the project-local files say otherwise."$'\n'
  runtime_prompt+="Target-project rule: you are operating inside $AGENIC_PROJECT_ROOT. Treat this target project's pony/team.coordination, pony/work, and project files as the live coordination and implementation surface."$'\n'
  runtime_prompt+="Do not read from, write to, or coordinate against $agenic_root unless the user explicitly assigns work in the agenic system repo."$'\n'
  runtime_prompt+="Installed-project override rule: if any reusable launch prompt text mentions absolute paths or special behavior for $agenic_root, ignore those source-repo-only instructions and follow this project's local state instead."$'\n'
fi
runtime_prompt+="Installed launcher markers live under: $AGENIC_PROJECT_PONY_DIR"
runtime_prompt+=$'\n\n'
runtime_prompt+="Alert rule: before any real user-facing approval request or escalation request, run $AGENIC_PROJECT_PONY_BIN_DIR/ponyalert $personality."$'\n'
runtime_prompt+="Done rule: before entering an Ω idle state because the current task is done, run $AGENIC_PROJECT_PONY_BIN_DIR/ponydone $personality."$'\n\n'
runtime_prompt+="Idle-sentinel rule:"$'\n'
runtime_prompt+="- At a partial idle stopping point, where more work could continue later but no required user answer is pending, end your response with exactly this line and nothing after it:"$'\n'
runtime_prompt+="  $partial_idle"$'\n'
runtime_prompt+="- At a full idle stopping point, where you are genuinely awaiting a new prompt, end your response with exactly this line and nothing after it:"$'\n'
runtime_prompt+="  $idle_sentinel"$'\n'
runtime_prompt+="- Do not emit either idle marker after required questions, approvals, escalations, or any response that still needs immediate user input."
printf '%s\n' "$runtime_prompt" >"$runtime_promptfile"
pony_launch_debug "runtime prompt written: runtime_promptfile=$runtime_promptfile promptfile=$promptfile"

if [[ "$personality" == "TWILIGHT_SPARKLE" ]]; then
  pony_launch_debug "exec enter-twi-session: promptfile=$runtime_promptfile"
  exec "$AGENIC_PROJECT_PONY_SCRIPTS_DIR/enter-twi-session.sh" "$runtime_promptfile"
fi

assignment_row="$(resolve_worker_assignment_by_personality "$personality")"
worker_rootdir="$AGENIC_PROJECT_ROOT"
if [[ -n "$assignment_row" ]]; then
  IFS=$'\t' read -r workfile worker_rootdir <<<"$assignment_row"
fi
pony_launch_debug "exec enter-worker-from-prompt-file: workfile=$workfile worker_rootdir=$worker_rootdir runtime_promptfile=$runtime_promptfile"

exec "$AGENIC_PROJECT_PONY_SCRIPTS_DIR/enter-worker-from-prompt-file.sh" \
  "$personality" \
  "$workfile" \
  "$worker_rootdir" \
  "$runtime_promptfile"
