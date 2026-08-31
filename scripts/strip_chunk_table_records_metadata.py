#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""Remove duplicated table_records from pms_page_chunk metadata.

The chunk loader now keeps table_records at the document level only. This
utility updates existing chunk rows so their metadata no longer carries a
duplicate copy of the full document table extraction payload.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence
from urllib.parse import quote

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _build_where_clause(source_name: str | None) -> tuple[str, list[str]]:
    params: list[str] = []
    clause = "metadata ? 'table_records'"
    if source_name:
        params.append(source_name)
        clause += " AND source_name = %s"
    return clause, params


def _build_db_url() -> str:
    db_url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if db_url:
        return db_url
    user = os.environ["EVH_PGUSER"]
    pw = quote(os.environ["EVH_PGPASSWORD"], safe="")
    host = os.environ["EVH_PGHOST"]
    port = os.environ["EVH_PGPORT"]
    db = os.environ["EVH_PGDATABASE"]
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}?sslmode=require"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strip duplicated table_records from pms_page_chunk metadata."
    )
    parser.add_argument("--database-url", default="")
    parser.add_argument("--table-name", default="pms_page_chunk")
    parser.add_argument("--source-name", default="", help="Optional source_name filter.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report matching rows without updating them.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        args.database_url = _build_db_url()

    source_name = args.source_name.strip() or None
    where_clause, params = _build_where_clause(source_name)
    conn = psycopg.connect(args.database_url, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {args.table_name} WHERE {where_clause}",
                params,
            )
            matched = int(cur.fetchone()[0] or 0)
            print(f"matching_rows={matched}")
            if args.dry_run or matched == 0:
                conn.rollback()
                return 0
            cur.execute(
                f"""
                UPDATE {args.table_name}
                SET metadata = metadata - 'table_records'
                WHERE {where_clause}
                """,
                params,
            )
            print(f"updated_rows={cur.rowcount}")
        conn.commit()
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
