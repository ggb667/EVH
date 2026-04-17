#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/../.." && pwd)"
unset AGENIC_PONY_SOURCE_ROOT
source_root="$("$project_root/pony/scripts/resolve-system-root.sh" "$project_root")"

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
export AGENIC_PROJECT_ROOT="$project_root"
export AGENIC_PONY_SOURCE_ROOT="$source_root"
export PONY_FUNC="$pony_func"

launcher_home_root="${TMPDIR:-/tmp}/agenic-pony-zdotdir"
launcher_home="$launcher_home_root/${USER:-user}-$(basename "$project_root")-${personality}"
mkdir -p "$launcher_home"

cat >"$launcher_home/.zshrc" <<'INNER_EOF'
typeset -g POWERLEVEL9K_INSTANT_PROMPT=quiet
[[ -f ~/.zshrc ]] && source ~/.zshrc || true
cd "${AGENIC_PROJECT_ROOT}"
[[ -f "${AGENIC_PONY_SOURCE_ROOT}/pony/scripts/pony.zsh.support.zsh" ]] && source "${AGENIC_PONY_SOURCE_ROOT}/pony/scripts/pony.zsh.support.zsh" || true

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

if [[ -z "${AGENIC_PONY_AUTORAN:-}" ]]; then
  export AGENIC_PONY_AUTORAN=1
  autoload -Uz add-zsh-hook
  _agenic_pony_launch_once() {
    add-zsh-hook -d precmd _agenic_pony_launch_once
    "${AGENIC_PONY_SOURCE_ROOT}/pony/scripts/start-session.sh" "${AGENIC_LAUNCH_PERSONALITY}" "${AGENIC_PROJECT_ROOT}"
  }
  add-zsh-hook precmd _agenic_pony_launch_once
fi
INNER_EOF

exec env ZDOTDIR="$launcher_home" zsh -i