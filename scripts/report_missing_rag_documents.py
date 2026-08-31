#!/usr/bin/env python3
"""Report documents present in rag_document_identity but missing from pms_page_chunk.

This is the delta/queue builder for the importer refresh lane:
- identity rows define the source-of-truth document set
- chunk rows define which documents have actually been ingested
- documents with identity rows but no chunk rows are the 1% backlog

The output is JSON lines so it can be piped into downstream tooling or cron logs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class MissingDocument:
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


def _fetch_missing_documents(conn, *, client_id: str | None = None, patient_id: str | None = None) -> list[MissingDocument]:
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

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        MissingDocument(
            document_pdf_id=str(row["document_pdf_id"]),
            client_id=str(row["client_id"]),
            patient_id=str(row["patient_id"]),
            originalfilename=str(row["originalfilename"]),
            chunk_count=int(row["chunk_count"]),
        )
        for row in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report rag_document_identity rows that have no matching pms_page_chunk rows")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--client-id", default="", help="Optional client filter")
    parser.add_argument("--patient-id", default="", help="Optional patient filter")
    parser.add_argument("--jsonl", action="store_true", help="Emit JSON lines instead of a human summary")
    args = parser.parse_args(argv)

    db_url = args.database_url.strip() or _build_db_url()
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        missing = _fetch_missing_documents(
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
