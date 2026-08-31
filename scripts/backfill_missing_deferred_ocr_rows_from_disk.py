#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""Backfill rag_deferred_ocr_document from the live INSTINCT REST API.

This script walks INSTINCT directly:
- accounts
- patients for each account
- chart PDFs for each patient

It writes one deferred-table row per chart PDF using the live API as source of
truth. The rows begin in `unprocessed` state so the downstream pipeline can
take over from there.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_pdf_family_sampler import fetch_medical_history_visits


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


def _normalize(text: Any) -> str | None:
    if text is None:
        return None
    s = str(text).strip()
    return s or None


def _emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def _load_checkpoint(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text())
        if isinstance(payload, dict):
            return {k: str(v) for k, v in payload.items() if v is not None}
    except Exception:
        pass
    return {}


def _save_checkpoint(path: Path, *, account_index: int, patient_index: int, chart_index: int, client_id: str, patient_id: str, chart_id: str) -> None:
    payload = {
        "account_index": account_index,
        "patient_index": patient_index,
        "chart_index": chart_index,
        "client_id": client_id,
        "patient_id": patient_id,
        "chart_id": chart_id,
    }
    path.write_text(json.dumps(payload, sort_keys=True))


def _iter_charts_for_patient(adapter: InstinctApiAdapter, patient_id: str) -> list[dict[str, Any]]:
    history = fetch_medical_history_visits(patient_id)
    charts = history.get("charts") if isinstance(history, dict) else []
    return charts if isinstance(charts, list) else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill rag_deferred_ocr_document from INSTINCT")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--deferred-ocr-table-name", default="rag_deferred_ocr_document")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--limit-accounts", type=int, default=0)
    parser.add_argument("--limit-patients", type=int, default=0)
    parser.add_argument("--limit-charts", type=int, default=0)
    parser.add_argument("--checkpoint-path", default="/tmp/evh_instinct_deferred_backfill.checkpoint.json")
    args = parser.parse_args(argv)

    if not args.database_url:
        args.database_url = _build_db_url()

    base_url = os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com")
    username = os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME")
    password = os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD")
    if not username or not password:
        raise SystemExit("Missing INSTINCT credentials.")

    adapter = InstinctApiAdapter(base_url, username, password)
    _emit("auth_start", base_url=base_url)
    adapter.authenticate()
    accounts = list(adapter.iter_accounts())
    _emit("auth_done", accounts=len(accounts))
    checkpoint_path = Path(args.checkpoint_path)
    checkpoint = _load_checkpoint(checkpoint_path)
    resume_account_index = int(checkpoint.get("account_index", "-1"))
    resume_patient_index = int(checkpoint.get("patient_index", "-1"))
    resume_chart_index = int(checkpoint.get("chart_index", "-1"))
    resume_client_id = checkpoint.get("client_id", "")
    resume_patient_id = checkpoint.get("patient_id", "")
    resume_chart_id = checkpoint.get("chart_id", "")

    existing_rows: set[str] = set()
    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT document_pdf_id
                FROM {args.deferred_ocr_table_name}
                WHERE document_pdf_id IS NOT NULL
                """
            )
            existing_rows = {str(row["document_pdf_id"]) for row in cur.fetchall() if row.get("document_pdf_id")}

    _emit("backfill_preflight_done", existing_in_deferred_table=len(existing_rows))

    rows: list[dict[str, Any]] = []
    skipped_existing = 0
    processed_accounts = 0
    processed_patients = 0
    processed_charts = 0
    inserted = 0

    def flush_rows(cur: Any, *, final: bool = False) -> None:
        nonlocal inserted
        if not rows:
            return
        _emit(
            "db_batch_execute_start",
            batch_size=len(rows),
            inserted=inserted,
            total=inserted + len(rows),
            final=final,
        )
        params = [
            (
                row["source_name"],
                row["source_uri"],
                row["patient_name"],
                row["page_count"],
                row["reason"],
                row["status"],
                row["metadata"],
                row["disk_filename"],
                row["document_pdf_id"],
                row["source_system"],
                row["remote_content_length"],
                row["downloaded_sha256"],
                row["fetch_uri"],
                row["fetch_uri_observed_at"],
                row["local_cache_path"],
                row["content_hash"] if "content_hash" in row else None,
                row["content_length"] if "content_length" in row else None,
            )
            for row in rows
        ]
        cur.executemany(
            f"""
            INSERT INTO {args.deferred_ocr_table_name} (
                source_name,
                source_uri,
                patient_name,
                page_count,
                reason,
                status,
                metadata,
                disk_filename,
                document_pdf_id,
                source_system,
                remote_content_length,
                downloaded_sha256,
                fetch_uri,
                fetch_uri_observed_at,
                local_cache_path,
                content_hash,
                content_length
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (document_pdf_id) DO UPDATE SET
                source_name = EXCLUDED.source_name,
                source_uri = EXCLUDED.source_uri,
                patient_name = EXCLUDED.patient_name,
                page_count = EXCLUDED.page_count,
                reason = EXCLUDED.reason,
                status = EXCLUDED.status,
                metadata = EXCLUDED.metadata,
                disk_filename = EXCLUDED.disk_filename,
                source_system = EXCLUDED.source_system,
                remote_content_length = COALESCE(EXCLUDED.remote_content_length, {args.deferred_ocr_table_name}.remote_content_length),
                downloaded_sha256 = COALESCE(EXCLUDED.downloaded_sha256, {args.deferred_ocr_table_name}.downloaded_sha256),
                fetch_uri = COALESCE(EXCLUDED.fetch_uri, {args.deferred_ocr_table_name}.fetch_uri),
                fetch_uri_observed_at = COALESCE(EXCLUDED.fetch_uri_observed_at, {args.deferred_ocr_table_name}.fetch_uri_observed_at),
                local_cache_path = COALESCE(EXCLUDED.local_cache_path, {args.deferred_ocr_table_name}.local_cache_path),
                content_hash = COALESCE(EXCLUDED.content_hash, {args.deferred_ocr_table_name}.content_hash),
                content_length = COALESCE(EXCLUDED.content_length, {args.deferred_ocr_table_name}.content_length),
                detected_at = now()
            """,
            params,
        )
        cur.executemany(
            """
            INSERT INTO rag_document_identity (document_pdf_id, client_id, patient_id, originalfilename)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (document_pdf_id) DO UPDATE SET
                client_id = EXCLUDED.client_id,
                patient_id = EXCLUDED.patient_id,
                originalfilename = EXCLUDED.originalfilename
            """,
            [
                (
                    row["document_pdf_id"],
                    row["client_id"],
                    row["patient_id"],
                    row["originalfilename"],
                )
                for row in rows
            ],
        )
        inserted += len(rows)
        _emit("batch_written", batch_size=len(rows), inserted=inserted, final=final)
        _emit("progress_pulse", records_processed=inserted, records_mod_100=(inserted % 100), final=final)
        rows.clear()

    for account_index, account in enumerate(accounts):
        if (
            account_index < resume_account_index
            or (account_index == resume_account_index and resume_client_id and _normalize(account.get("id")) == resume_client_id and resume_patient_index >= 0)
        ):
            if account_index < resume_account_index:
                continue
        if args.limit_accounts and processed_accounts >= args.limit_accounts:
            break
        client_id = _normalize(account.get("id"))
        if not client_id:
            continue
        client_name = _normalize(account.get("name") or account.get("displayName") or account.get("businessName"))
        processed_accounts += 1

        for patient_index, patient in enumerate(adapter.iter_patients_for_account(client_id)):
            if account_index == resume_account_index and patient_index < resume_patient_index:
                continue
            if args.limit_patients and processed_patients >= args.limit_patients:
                break
            patient_id = _normalize(patient.get("id"))
            if not patient_id:
                continue
            patient_name = _normalize(patient.get("name") or patient.get("patientName") or client_name or patient_id)
            processed_patients += 1
            charts = _iter_charts_for_patient(adapter, patient_id)
            for chart_index, chart in enumerate(charts):
                if account_index == resume_account_index and patient_index == resume_patient_index and chart_index <= resume_chart_index:
                    continue
                if args.limit_charts and processed_charts >= args.limit_charts:
                    break
                if not isinstance(chart, dict):
                    continue
                chart_id = _normalize(chart.get("id"))
                if not chart_id:
                    continue
                processed_charts += 1
                if chart_id in existing_rows:
                    skipped_existing += 1
                    continue

                filename = _normalize(chart.get("filename") or chart.get("label") or f"{chart_id}.pdf") or f"{chart_id}.pdf"
                fetch_uri = None
                try:
                    fetch_uri = create_chart_file_url(chart_id, inline=True)
                except Exception as exc:
                    fetch_uri = None

                rows.append(
                    {
                        "source_name": f"{client_id}:{patient_id}:{filename}",
                        "source_uri": fetch_uri,
                        "client_id": client_id,
                        "patient_id": patient_id,
                        "patient_name": patient_name,
                        "document_pdf_id": chart_id,
                        "disk_filename": filename,
                        "source_system": "instinct",
                        "document_pdf_id": chart_id,
                        "original_filename": filename,
                        "remote_content_length": None,
                        "downloaded_sha256": None,
                        "fetch_uri": fetch_uri,
                        "fetch_uri_observed_at": None,
                        "local_cache_path": None,
                        "page_count": None,
                        "reason": "backfilled_from_instinct_api",
                        "status": "pending",
                        "metadata": json.dumps(
                            {
                                "backfilled_from_instinct_api": True,
                                "account_index": account_index,
                                "patient_index": patient_index,
                                "chart_index": chart_index,
                                "client_id": client_id,
                                "client_name": client_name,
                                "patient_id": patient_id,
                                "patient_name": patient_name,
                                "originalfilename": filename,
                                "chart_id": chart_id,
                                "chart_label": chart.get("label"),
                                "chart_type": chart.get("__typename") or chart.get("type"),
                            },
                            sort_keys=True,
                        ),
                    }
                )
                _save_checkpoint(
                    checkpoint_path,
                    account_index=account_index,
                    patient_index=patient_index,
                    chart_index=chart_index,
                    client_id=client_id,
                    patient_id=patient_id,
                    chart_id=chart_id,
                )
                if len(rows) >= args.chunk_size:
                    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
                        with conn.cursor() as cur:
                            flush_rows(cur, final=False)
                            conn.commit()
                            _save_checkpoint(
                                checkpoint_path,
                                account_index=account_index,
                                patient_index=patient_index,
                                chart_index=chart_index,
                                client_id=client_id,
                                patient_id=patient_id,
                                chart_id=chart_id,
                            )

    _emit("backfill_rows_prepared", rows=inserted + len(rows), skipped_existing=skipped_existing)

    if args.dry_run:
        for row in rows[:25]:
            print(json.dumps(row, indent=2, sort_keys=True))
        return 0

    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            flush_rows(cur, final=True)
            conn.commit()
    if processed_accounts or processed_patients or processed_charts:
        _save_checkpoint(
            checkpoint_path,
            account_index=max(resume_account_index, 0 if processed_accounts else resume_account_index),
            patient_index=max(resume_patient_index, 0 if processed_patients else resume_patient_index),
            chart_index=max(resume_chart_index, 0 if processed_charts else resume_chart_index),
            client_id=resume_client_id,
            patient_id=resume_patient_id,
            chart_id=resume_chart_id,
        )

    _emit(
        "backfill_done",
        rows=len(rows),
        skipped_existing=skipped_existing,
        inserted=inserted,
        accounts=processed_accounts,
        patients=processed_patients,
        charts=processed_charts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
