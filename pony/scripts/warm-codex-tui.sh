#!/usr/bin/env bash
set -euo pipefail

codex_repo_root="${CODEX_REPO_ROOT:-/home/ggb66/dev/codex/codex-rs}"
codex_target_dir="${CARGO_TARGET_DIR:-/tmp/codex-pony-target}"

cd "$codex_repo_root"
exec env CARGO_TARGET_DIR="$codex_target_dir" \
  cargo build -p codex-tui --bin codex-tui