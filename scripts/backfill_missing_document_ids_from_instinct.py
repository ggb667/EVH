from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evh_reminder_importer import InstinctApiAdapter


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


def _basename(value: str | None) -> str | None:
    if not value:
        return None
    return Path(value).name or value


def _chart_files_for_patient(adapter: InstinctApiAdapter, patient_id: str):
    import requests

    query = """
query medicalHistoryVisits($patientId: ID!, $chartTypes: [ChartType]) {
  charts(patientId: $patientId, chartTypes: $chartTypes) {
    __typename
    ... on ChartFile { id filename label type }
  }
}
""".strip()
    resp = requests.post(
        "https://evh.api.instinctvet.com/",
        json={
            "query": query,
            "variables": {
                "patientId": patient_id,
                "chartTypes": ["CHART_DOCUMENT", "CHART_FILE", "DIAGNOSTIC"],
            },
        },
        headers={"Authorization": f"Bearer {adapter.token}", "Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload.get("data", {}).get("charts") or []


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing Postgres document_pdf_id values one row at a time")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N rows")
    args = parser.parse_args()

    db_url = args.database_url.strip() or _build_db_url()
    base_url = os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com")
    username = os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME")
    password = os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD")
    if not username or not password:
        raise SystemExit("Missing INSTINCT credentials.")

    adapter = InstinctApiAdapter(base_url, username, password)
    adapter.token = adapter.authenticate()

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, metadata
                FROM public.rag_source_document
                WHERE document_pdf_id IS NULL
                  AND metadata ? 'chart_id'
                  AND metadata ? 'filename'
                ORDER BY id
                """
            )
            rows = cur.fetchall()

        patient_cache: dict[str, dict[str, str | None]] = {}
        matched = 0
        written = 0

        for idx, row in enumerate(rows, start=1):
            if args.limit and idx > args.limit:
                break

            meta = row["metadata"] or {}
            patient_id = _normalize(meta.get("patient_id"))
            chart_id = _normalize(meta.get("chart_id"))
            filename = _basename(_normalize(meta.get("filename")))

            if not patient_id or not chart_id:
                print(json.dumps({
                    "event": "row_skip",
                    "id": int(row["id"]),
                    "reason": "missing_patient_or_chart_id",
                }), flush=True)
                continue

            if patient_id not in patient_cache:
                charts = _chart_files_for_patient(adapter, patient_id)
                patient_cache[patient_id] = {
                    _normalize(chart.get("id")): _normalize(chart.get("filename"))
                    for chart in charts
                    if isinstance(chart, dict) and chart.get("__typename") == "ChartFile"
                }
                print(json.dumps({
                    "event": "patient_loaded",
                    "patient_id": patient_id,
                    "chart_count": len(patient_cache[patient_id]),
                    "rows_seen": idx,
                    "cache_size": len(patient_cache),
                }), flush=True)

            live_filename = _basename(patient_cache[patient_id].get(chart_id))
            if live_filename is None:
                print(json.dumps({
                    "event": "row_no_match",
                    "id": int(row["id"]),
                    "patient_id": patient_id,
                    "chart_id": chart_id,
                    "filename": filename,
                    "reason": "chart_not_found_live",
                }), flush=True)
                continue

            if filename and live_filename and filename != live_filename:
                print(json.dumps({
                    "event": "row_no_match",
                    "id": int(row["id"]),
                    "patient_id": patient_id,
                    "chart_id": chart_id,
                    "filename": filename,
                    "live_filename": live_filename,
                    "reason": "filename_mismatch",
                }), flush=True)
                continue

            matched += 1
            print(json.dumps({
                "event": "row_match",
                "id": int(row["id"]),
                "patient_id": patient_id,
                "chart_id": chart_id,
                "filename": filename,
                "live_filename": live_filename,
            }), flush=True)

            if not args.dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE public.rag_source_document SET document_pdf_id = %s WHERE id = %s",
                        (chart_id, int(row["id"])),
                    )
                conn.commit()
                written += 1
                print(json.dumps({
                    "event": "row_written",
                    "id": int(row["id"]),
                    "written": written,
                }), flush=True)

        print(json.dumps({
            "event": "scan_complete",
            "rows_examined": min(len(rows), args.limit or len(rows)),
            "matched": matched,
            "written": written,
            "dry_run": args.dry_run,
        }), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
