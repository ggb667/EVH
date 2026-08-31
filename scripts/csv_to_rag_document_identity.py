#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""Load rag_document_identity rows from a CSV file and upsert them into Postgres.

This is a thin wrapper around the CSV tail/import mode so the name makes the
purpose explicit:

- it does not walk Instinct
- it does not generate CSV
- it only reads an existing CSV and upserts rows into rag_document_identity
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sync_document_identity_from_instinct import main as sync_main


def main(argv: list[str] | None = None) -> int:
    default_argv = [
        "--csv-file",
        "/tmp/rag_document_identity.csv",
        "--batch-size",
        "100",
    ]
    return sync_main(argv if argv is not None else default_argv)


if __name__ == "__main__":
    raise SystemExit(main())
