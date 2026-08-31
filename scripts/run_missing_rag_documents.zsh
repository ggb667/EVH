#!/usr/bin/env zsh
set -euo pipefail

if [[ ! -f "$HOME/dev/postgress_connection.zsh" ]]; then
  print -u2 "missing Postgres connection helper: $HOME/dev/postgress_connection.zsh"
  exit 1
fi

source "$HOME/dev/postgress_connection.zsh"

project_root="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$project_root/scripts/report_missing_rag_documents.py" "$@"
