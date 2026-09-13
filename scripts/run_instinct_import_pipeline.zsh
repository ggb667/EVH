#!/usr/bin/env zsh
set -euo pipefail

# Launch the already-existing fixed importer pipeline.
exec python3 "$(cd "$(dirname "$0")/.." && pwd)/scripts/run_instinct_import_fixed.py" "$@"
