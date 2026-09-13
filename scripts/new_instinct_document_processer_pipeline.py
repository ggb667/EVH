#!/usr/bin/env python3
"""Simple Instinct -> Postgres document pipeline, step 1: build missing worklist.

This first step finds the documents we still need to process.
It does not fetch or mutate any document rows yet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class MissingWorkItem:
    document_pdf_id: str
    client_id: str
    patient_id: str
    originalfilename: str
    chunk_count: int


def _build_db_url() -> str:
    db_url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if db_url:
        return db_url
    return (
        f"postgresql://{os.environ['EVH_PGUSER']}:{os.environ['EVH_PGPASSWORD']}"
        f"@{os.environ['EVH_PGHOST']}:{os.environ['EVH_PGPORT']}/{os.environ['EVH_PGDATABASE']}?sslmode=require"
    )


def build_missing_worklist(conn, *, client_id: str | None = None, patient_id: str | None = None) -> list[MissingWorkItem]:
    clauses: list[str] = []
    params: list[Any] = []
    if client_id:
        clauses.append("i.client_id = %s")
        params.append(client_id)
    if patient_id:
        clauses.append("i.patient_id = %s")
        params.append(patient_id)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
SELECT
  i.document_pdf_id,
  i.client_id,
  i.patient_id,
  i.originalfilename,
  COUNT(p.id)::int AS chunk_count
FROM public.rag_document_identity i
LEFT JOIN public.pms_page_chunk p
  ON p.document_pdf_id = i.document_pdf_id
{where_sql}
GROUP BY i.document_pdf_id, i.client_id, i.patient_id, i.originalfilename
HAVING COUNT(p.id) = 0
ORDER BY i.client_id, i.patient_id, i.document_pdf_id;
""".strip()

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()

    return [
        MissingWorkItem(
            document_pdf_id=str(row["document_pdf_id"]),
            client_id=str(row["client_id"]),
            patient_id=str(row["patient_id"]),
            originalfilename=str(row["originalfilename"]),
            chunk_count=int(row["chunk_count"]),
        )
        for row in rows
    ]


def main(argv: list[str] | None = None) -> int:
    import psycopg
    from psycopg.rows import dict_row

    parser = argparse.ArgumentParser(description="Build the missing document worklist for the Instinct pipeline")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--client-id", default="")
    parser.add_argument("--patient-id", default="")
    parser.add_argument("--jsonl", action="store_true", help="Emit JSON lines instead of a summary")
    args = parser.parse_args(argv)

    db_url = args.database_url.strip() or _build_db_url()
    from psycopg.rows import dict_row

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        missing = build_missing_worklist(
            conn,
            client_id=args.client_id.strip() or None,
            patient_id=args.patient_id.strip() or None,
        )

    if args.jsonl:
        for row in missing:
            print(json.dumps(asdict(row), sort_keys=True), flush=True)
    else:
        print(json.dumps({"missing_count": len(missing)}, sort_keys=True), flush=True)
        for row in missing:
            print(
                f"missing | client_id={row.client_id} | patient_id={row.patient_id} | "
                f"document_pdf_id={row.document_pdf_id} | filename={row.originalfilename}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
