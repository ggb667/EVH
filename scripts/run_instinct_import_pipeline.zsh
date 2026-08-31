#!/usr/bin/env zsh
set -euo pipefail

# Source the approved Postgres connection bootstrap for this lane.
# The helper is expected to export the DB connection variables used by the
# existing importer runner.
if [[ ! -f "$HOME/dev/postgress_connection.zsh" ]]; then
  print -u2 "missing Postgres connection helper: $HOME/dev/postgress_connection.zsh"
  exit 1
fi

source "$HOME/dev/postgress_connection.zsh"

# Launch the already-existing fixed importer pipeline.
exec python3 "$(cd "$(dirname "$0")/.." && pwd)/scripts/run_instinct_import_fixed.py" "$@"
