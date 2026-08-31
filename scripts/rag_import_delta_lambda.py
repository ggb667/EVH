from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row


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


def _fetch_missing_documents(conn) -> list[MissingDocument]:
    sql = """
SELECT
  i.document_pdf_id,
  i.client_id,
  i.patient_id,
  i.originalfilename,
  COUNT(p.id)::int AS chunk_count
FROM public.rag_document_identity i
LEFT JOIN public.pms_page_chunk p
  ON p.document_pdf_id = i.document_pdf_id
GROUP BY i.document_pdf_id, i.client_id, i.patient_id, i.originalfilename
HAVING COUNT(p.id) = 0
ORDER BY i.client_id, i.patient_id, i.document_pdf_id;
""".strip()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
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


def lambda_handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    db_url = _build_db_url()
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        missing = _fetch_missing_documents(conn)

    payload = {
        "status": "ok",
        "missing_count": len(missing),
        "missing_documents": [asdict(row) for row in missing[:100]],
        "truncated": len(missing) > 100,
    }
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
    }
