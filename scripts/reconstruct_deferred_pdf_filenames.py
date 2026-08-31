#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""Reconstruct deferred PDF filenames in place when identity metadata is available.

Filename format:
    pdfid_clientid_patientid_originalfilename.pdf

This script does not redownload PDFs. It uses:
- rag_source_document metadata when available
- cached Instinct chart crawl data from pdf_size_table.json when available

If a field cannot be recovered, the script falls back conservatively and logs it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row

DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
DEFAULT_DEFERRED_DIR = DATA_ROOT / "instinct-pdfs-deferred"
DEFAULT_PDF_SIZE_TABLE = Path(__file__).resolve().parents[1] / "pdf_size_table.json"


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


def _normalize(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_filename_piece(value: str | None) -> str | None:
    if not value:
        return None
    value = value.replace("/", "_").replace("\\", "_")
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._")
    return value or None


def _read_chart_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in payload:
        if isinstance(row, dict):
            chart_id = _normalize(row.get("chart_id"))
            if chart_id:
                out[chart_id] = row
    return out


def _load_db_rows(database_url: str, pdf_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not pdf_ids:
        return {}
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    metadata->>'pdf_id' AS pdf_id,
                    metadata->>'patient_id' AS patient_id,
                    metadata->>'patient_name' AS patient_name,
                    source_name,
                    source_uri,
                    status
                FROM rag_source_document
                WHERE metadata ? 'pdf_id'
                  AND metadata->>'pdf_id' = ANY(%s)
                """,
                (pdf_ids,),
            )
            rows = cur.fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        pdf_id = _normalize(row.get("pdf_id"))
        if pdf_id:
            out[pdf_id] = row
    return out


@dataclass(frozen=True)
class RenamePlan:
    pdf_id: str
    source_path: Path
    target_path: Path
    client_id: str | None
    patient_id: str | None
    original_filename: str | None
    source: str


def _derive_plan(
    *,
    pdf_path: Path,
    chart_cache: dict[str, dict[str, Any]],
    source_rows: dict[str, dict[str, Any]],
) -> RenamePlan:
    pdf_id = pdf_path.stem
    client_id = None
    patient_id = None
    original_filename = None
    source = "fallback"

    row = source_rows.get(pdf_id)
    if row:
        source = "rag_source_document"
        patient_id = _normalize(row.get("patient_id"))
        patient_name = _normalize(row.get("patient_name"))
        source_name = _normalize(row.get("source_name"))
        if source_name and ":" in source_name:
            parts = source_name.split(":")
            if len(parts) >= 3:
                client_id = _normalize(parts[0])
                if not patient_id:
                    patient_id = _normalize(parts[1])
                original_filename = _normalize(":".join(parts[2:]))
        if not original_filename and source_name:
            original_filename = Path(source_name).name
        if row.get("source_uri"):
            source = "rag_source_document"

    cache_row = chart_cache.get(pdf_id)
    if cache_row:
        if source == "fallback":
            source = "pdf_size_table.json"
        client_id = client_id or _normalize(cache_row.get("client_id"))
        patient_id = patient_id or _normalize(cache_row.get("patient_id"))
        original_filename = original_filename or _normalize(cache_row.get("filename"))

    if not original_filename:
        original_filename = f"{pdf_id}.pdf"

    client_piece = _safe_filename_piece(client_id) or "unknown_client"
    patient_piece = _safe_filename_piece(patient_id) or "unknown_patient"
    orig_piece = _safe_filename_piece(original_filename) or f"{pdf_id}.pdf"
    target_name = f"{pdf_id}_{client_piece}_{patient_piece}_{orig_piece}"
    if not target_name.lower().endswith(".pdf"):
        target_name += ".pdf"

    return RenamePlan(
        pdf_id=pdf_id,
        source_path=pdf_path,
        target_path=pdf_path.with_name(target_name),
        client_id=client_id,
        patient_id=patient_id,
        original_filename=original_filename,
        source=source,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct deferred PDF filenames in place")
    parser.add_argument("--deferred-dir", default=str(DEFAULT_DEFERRED_DIR))
    parser.add_argument("--chart-cache", default=str(DEFAULT_PDF_SIZE_TABLE))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files processed; 0 means all.")
    args = parser.parse_args(argv)

    deferred_dir = Path(args.deferred_dir).expanduser()
    chart_cache = _read_chart_cache(Path(args.chart_cache).expanduser())
    pdf_files = sorted(p for p in deferred_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if args.limit and args.limit > 0:
        pdf_files = pdf_files[: args.limit]

    database_url = _build_db_url()
    source_rows = _load_db_rows(database_url, [p.stem for p in pdf_files])

    renamed = 0
    unchanged = 0
    ambiguous = 0
    plans = []
    for pdf_path in pdf_files:
        plan = _derive_plan(pdf_path=pdf_path, chart_cache=chart_cache, source_rows=source_rows)
        plans.append(plan)
        if plan.target_path.name == plan.source_path.name:
            unchanged += 1
            continue
        if plan.target_path.exists():
            ambiguous += 1
            continue
        if not args.dry_run:
            plan.source_path.rename(plan.target_path)
        renamed += 1
        print(
            json.dumps(
                {
                    "pdf_id": plan.pdf_id,
                    "source": plan.source,
                    "old_name": plan.source_path.name,
                    "new_name": plan.target_path.name,
                    "client_id": plan.client_id,
                    "patient_id": plan.patient_id,
                    "original_filename": plan.original_filename,
                    "renamed": not args.dry_run,
                },
                sort_keys=True,
            )
        )

    print(
        json.dumps(
            {
                "deferred_files_seen": len(pdf_files),
                "renamed": renamed,
                "unchanged": unchanged,
                "name_conflicts": ambiguous,
                "dry_run": args.dry_run,
                "chart_cache_rows": len(chart_cache),
                "source_document_rows": len(source_rows),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
