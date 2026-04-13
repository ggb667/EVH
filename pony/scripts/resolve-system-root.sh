#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="${1:-$(cd "$script_dir/../.." && pwd)}"
config_path="$project_root/pony/pony.system.config.yaml"

default_repo='https://github.com/ggb667/agenic-pony-system.git'
default_ref='main'

config_value() {
  local key="${1:?missing config key}"
  local file="${2:?missing config path}"
  [[ -f "$file" ]] || return 0
  awk -F': ' -v key="$key" '$1 == key {print substr($0, index($0, ": ") + 2); exit}' "$file"
}

valid_source_root() {
  local candidate="${1:-}"
  [[ -n "$candidate" && -x "$candidate/scripts/install-project.sh" ]]
}

cache_root_for_repo() {
  local repo_url="${1:?missing repo url}"
  local ref="${2:?missing ref}"
  local cache_base
  local repo_slug

  if [[ -n "${AGENIC_PONY_SOURCE_CACHE_ROOT:-}" ]]; then
    printf '%s\n' "$AGENIC_PONY_SOURCE_CACHE_ROOT"
    return 0
  fi

  cache_base="${AGENIC_PONY_SOURCE_CACHE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/agenic-pony-system/sources}"
  repo_slug="$(printf '%s' "$repo_url-$ref" | tr -cs '[:alnum:]._-' '-')"
  printf '%s\n' "$cache_base/$repo_slug"
}

ensure_cached_source() {
  local repo_url="${1:?missing repo url}"
  local ref="${2:?missing ref}"
  local cache_root="${3:?missing cache root}"

  if valid_source_root "$cache_root"; then
    return 0
  fi

  if [[ -d "$cache_root/.git" ]]; then
    git -C "$cache_root" fetch --depth 1 origin "$ref" >/dev/null 2>&1 || true
    git -C "$cache_root" checkout --quiet FETCH_HEAD >/dev/null 2>&1 || \
      git -C "$cache_root" checkout --quiet "$ref" >/dev/null 2>&1 || true
    valid_source_root "$cache_root" && return 0
  fi

  mkdir -p "$(dirname "$cache_root")"
  git clone --depth 1 --branch "$ref" "$repo_url" "$cache_root" >/dev/null 2>&1 || return 1
  valid_source_root "$cache_root"
}

configured_root="$(config_value agenic_system_root "$config_path")"
configured_repo="$(config_value agenic_system_repo "$config_path")"
configured_ref="$(config_value agenic_system_ref "$config_path")"

repo_url="${configured_repo:-$default_repo}"
ref="${configured_ref:-$default_ref}"
cache_root="$(cache_root_for_repo "$repo_url" "$ref")"

if valid_source_root "${AGENIC_PONY_SOURCE_ROOT:-}"; then
  cd "$AGENIC_PONY_SOURCE_ROOT" && pwd
  exit 0
fi

if ensure_cached_source "$repo_url" "$ref" "$cache_root"; then
  cd "$cache_root" && pwd
  exit 0
fi

if valid_source_root "$configured_root"; then
  cd "$configured_root" && pwd
  exit 0
fi

candidate_root="$(cd "$script_dir/../.." && pwd)"
if valid_source_root "$candidate_root"; then
  cd "$candidate_root" && pwd
  exit 0
fi

printf 'ERROR: unable to resolve agenic pony system source root\n' >&2
exit 1