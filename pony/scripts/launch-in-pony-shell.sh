#!/usr/bin/env bash
set -euo pipefail

personality="${1:?missing personality}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
launch_project_root="$(cd "$script_dir/../.." && pwd)"

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

launcher_home_root="${TMPDIR:-/tmp}/agenic-pony-zdotdir"
launcher_home="$launcher_home_root/${USER:-user}-$(basename "$launch_project_root")-${personality}"
mkdir -p "$launcher_home"

cat >"$launcher_home/.zshrc" <<'EOF'
typeset -g POWERLEVEL9K_INSTANT_PROMPT=quiet
[[ -f ~/.zshrc ]] && source ~/.zshrc || true
cd "${AGENIC_PROJECT_ROOT}"
[[ -f ./pony/scripts/pony.zsh.support.zsh ]] && source ./pony/scripts/pony.zsh.support.zsh || true

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
  _agenic_pony_launch_once() {
    zle -D zle-line-init
    BUFFER="./pony/scripts/start-session.sh ${(q)AGENIC_LAUNCH_PERSONALITY} ${(q)AGENIC_PROJECT_ROOT}"
    CURSOR=${#BUFFER}
    zle accept-line
  }
  zle -N zle-line-init _agenic_pony_launch_once
fi
EOF

exec env ZDOTDIR="$launcher_home" zsh -i