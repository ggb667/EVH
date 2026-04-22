#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
launch_project_root="$(cd "$script_dir/../.." && pwd)"
source "$script_dir/launch-debug.sh"

case "$personality" in
  PRINCESS_CELESTIA_SOL_INVICTUS) pony_func="celestia" ;;
  TWILIGHT_SPARKLE) pony_func="twi" ;;
  APPLEJACK) pony_func="aj" ;;
  PINKIE_PIE) pony_func="pinkie" ;;
  FLUTTERSHY) pony_func="shy" ;;
  RARITY) pony_func="rarity" ;;
  RAINBOW_DASH) pony_func="rd" ;;
  SPIKE) pony_func="spike" ;;
  *) pony_func="" ;;
esac

export AGENIC_LAUNCH_PERSONALITY="$personality"
export AGENIC_PROJECT_ROOT="$launch_project_root"
export PONY_FUNC="$pony_func"
unset AGENIC_PONY_AUTORAN
unset AGENIC_PONY_AUTORAN_DONE
pony_launch_debug_init
pony_launch_debug "launch wrapper start: pwd=$PWD project_root=$launch_project_root personality=$personality pony_func=${pony_func:-none}"
export AGENIC_PONY_LAUNCH_DEBUG_LOG

launcher_home_root="${TMPDIR:-/tmp}/agenic-pony-zdotdir"
launcher_home="$launcher_home_root/${USER:-user}-$(basename "$launch_project_root")-${personality}"
mkdir -p "$launcher_home"

cat >"$launcher_home/.zshrc" <<'EOF'
typeset -g POWERLEVEL9K_INSTANT_PROMPT=quiet
_agenic_pony_log() {
  [[ "${AGENIC_PONY_LAUNCH_DEBUG:-0}" == "1" ]] || return 0
  [[ -n "${AGENIC_PONY_LAUNCH_DEBUG_LOG:-}" ]] || return 0
  printf '%s [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "launcher.zshrc" "$1" >>"${AGENIC_PONY_LAUNCH_DEBUG_LOG}"
}
_agenic_pony_log "shell init start: pwd=$PWD target=${AGENIC_PROJECT_ROOT}"
cd "${AGENIC_PROJECT_ROOT}"
_agenic_pony_log "after cd: pwd=$PWD"
[[ -f ~/.zshrc ]] && source ~/.zshrc || true
_agenic_pony_log "after sourcing ~/.zshrc: pwd=$PWD personality=${PERSONALITY:-unset}"
cd "${AGENIC_PROJECT_ROOT}"
unset AGENIC_PONY_AUTORAN
unset AGENIC_PONY_AUTORAN_DONE
export PATH="${AGENIC_PROJECT_ROOT}/pony/bin:${PATH}"
_agenic_pony_log "after reasserting project root: pwd=$PWD autoran=${AGENIC_PONY_AUTORAN:-unset}"
typeset -g POWERLEVEL9K_INSTANT_PROMPT=quiet
[[ -f ./pony/scripts/pony.zsh.support.zsh ]] && source ./pony/scripts/pony.zsh.support.zsh || true
_agenic_pony_log "after sourcing pony.zsh.support.zsh: pwd=$PWD personality=${PERSONALITY:-unset}"

_agenic_pony_apply_identity() {
  if [[ -n "${PONY_FUNC:-}" ]] && whence -w "${PONY_FUNC}" >/dev/null 2>&1; then
    "${PONY_FUNC}"
  else
    export PERSONALITY="${AGENIC_LAUNCH_PERSONALITY:-}"
    if whence -w p10k >/dev/null 2>&1; then
      p10k reload || true
    fi
  fi
}

_agenic_pony_apply_identity
_agenic_pony_log "after identity apply: pwd=$PWD personality=${PERSONALITY:-unset}"

if [[ -z "${AGENIC_PONY_AUTORAN:-}" ]]; then
  export AGENIC_PONY_AUTORAN=1
  _agenic_pony_log "autorun start-session: personality=${AGENIC_LAUNCH_PERSONALITY} project=${AGENIC_PROJECT_ROOT}"
  source_root="$(./pony/scripts/resolve-system-root.sh "${AGENIC_PROJECT_ROOT}")"
  export AGENIC_PONY_SOURCE_ROOT="${source_root}"
  "${source_root}/pony/scripts/start-session.sh" "${AGENIC_LAUNCH_PERSONALITY}" "${AGENIC_PROJECT_ROOT}" </dev/tty >/dev/tty 2>&1
fi
EOF

pony_launch_debug "exec zsh: zdotdir=$launcher_home"
exec env ZDOTDIR="$launcher_home" zsh -i
