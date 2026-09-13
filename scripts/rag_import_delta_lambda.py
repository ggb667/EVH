from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from scripts.instinct_batch_flow import BatchMessage, handle_sqs_records, orchestrate_initial_run, parse_message
from scripts.instinct_cache_sync_pipeline import ensure_schema, sync_clients, sync_documents, sync_patients
from scripts.instinct_identity_sync import InstinctApiSyncClient


@dataclass(frozen=True)
class LambdaRunSummary:
    step: str
    patient_limit: int | None
    document_limit: int | None
    clients_fetched: int
    clients_upserted: int
    patients_fetched: int
    patients_upserted: int
    fetched: int
    inserted: int
    updated: int
    seconds: float


def _build_db_url() -> str:
    db_url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if db_url:
        return db_url
    return (
        f"postgresql://{os.environ['EVH_PGUSER']}:{os.environ['EVH_PGPASSWORD']}"
        f"@{os.environ['EVH_PGHOST']}:{os.environ['EVH_PGPORT']}/{os.environ['EVH_PGDATABASE']}?sslmode=require"
    )


def _parse_patient_limit(event: dict[str, Any]) -> int | None:
    for key in ("patient_limit", "patientLimit", "limit"):
        value = event.get(key)
        if value in (None, "", 0, "0"):
            continue
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            continue
    env_limit = os.environ.get("STEP13_PATIENT_LIMIT", "").strip()
    if env_limit:
        return max(1, int(env_limit))
    return 1000


def _parse_document_limit(event: dict[str, Any]) -> int | None:
    for key in ("document_limit", "documentLimit", "docs", "doc_limit"):
        value = event.get(key)
        if value in (None, "", 0, "0"):
            continue
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            continue
    env_limit = os.environ.get("STEP13_DOCUMENT_LIMIT", "").strip()
    if env_limit:
        return max(1, int(env_limit))
    return 1000


def _table_total(conn, stage: str) -> int:
    table = {
        "clients": "public.instinct_owner_lookup_cache",
        "patients": "public.instinct_patient_lookup_cache",
        "documents": "public.rag_source_document",
    }.get(stage)
    if not table:
        return 0
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        row = cur.fetchone()
        return int(next(iter(row.values()))) if row else 0


def _instrumented_log(conn, stage: str):
    target_total = _table_total(conn, stage)
    started = __import__("time").perf_counter()
    last_report = {"count": 0}

    def log(line: str) -> None:
        print(line, flush=True)
        try:
            payload = json.loads(line)
        except Exception:
            return
        if payload.get("event") != "documents_patient_fetch_start":
            return
        count = int(payload.get("index") or 0)
        if count == 0 or count % 10:
            return
        elapsed = max(__import__("time").perf_counter() - started, 0.001)
        rate = count / elapsed
        remaining = max(target_total - count, 0)
        eta = remaining / rate if rate else None
        print(json.dumps({
            "event": "progress_estimate",
            "stage": stage,
            "processed": count,
            "table_total": target_total,
            "percent": round(count * 100 / target_total, 3) if target_total else None,
            "elapsed_seconds": round(elapsed, 2),
            "rate_rows_per_second": round(rate, 4),
            "estimated_remaining_seconds": round(eta, 2) if eta is not None else None,
        }, sort_keys=True), flush=True)

    return log


def _instrument_client(client, log):
    original_get = client._get
    original_auth = client._auth

    def timed_get(path, params):
        started = time.perf_counter()
        try:
            return original_get(path, params)
        finally:
            print(json.dumps({"event": "instinct_http_complete", "method": "GET", "path": path,
                              "seconds": round(time.perf_counter() - started, 4)}, sort_keys=True), flush=True)

    def timed_auth(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_auth(*args, **kwargs)
        finally:
            print(json.dumps({"event": "instinct_http_complete", "method": "AUTH",
                              "seconds": round(time.perf_counter() - started, 4)}, sort_keys=True), flush=True)

    client._get = timed_get
    client._auth = timed_auth
    return client


def lambda_handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    if "Records" in event:
        def _process_message(msg: BatchMessage) -> dict[str, Any]:
            base_url = os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com").strip()
            client_id = os.environ.get("INSTINCT_CLIENT_ID", "").strip()
            client_secret = os.environ.get("INSTINCT_CLIENT_SECRET", "").strip()
            client = InstinctApiSyncClient(base_url, client_id, client_secret)
            connect_started = time.perf_counter()
            with psycopg.connect(_build_db_url(), row_factory=dict_row) as conn:
                print(json.dumps({"event": "db_connection_complete", "seconds": round(time.perf_counter() - connect_started, 4)}, sort_keys=True), flush=True)
                # Keep the remote schema compatible with the importer before any stage writes.
                ensure_schema(conn)
                log = _instrumented_log(conn, msg.stage)
                client = _instrument_client(client, log)
                if msg.stage == "clients":
                    summary = sync_clients(client, conn, log=log)
                elif msg.stage == "patients":
                    summary = sync_patients(client, conn, log=log)
                elif msg.stage == "documents":
                    summary = sync_documents(
                        client,
                        conn,
                        log=log,
                        patient_limit=msg.patient_limit,
                        document_limit=msg.document_limit,
                        candidate_scan_limit=msg.candidate_scan_limit,
                        stop_after_new=msg.stop_after_new,
                    )
                else:
                    raise RuntimeError(f"unknown batch stage: {msg.stage!r}")
                target_total = _table_total(conn, msg.stage)
            elapsed = max(float(summary.seconds), 0.001)
            rate = float(summary.fetched) / elapsed if summary.fetched else 0.0
            remaining = max(target_total - int(summary.fetched), 0)
            eta = (remaining / rate) if rate > 0 else None
            result = {
                "stage": msg.stage,
                "fetched": summary.fetched,
                "inserted": summary.inserted,
                "updated": summary.updated,
                "seconds": summary.seconds,
                "target_total_table_rows": target_total,
                "progress_rows": summary.fetched,
                "progress_percent": round((summary.fetched / target_total) * 100, 3) if target_total else None,
                "rate_rows_per_second": round(rate, 4),
                "estimated_remaining_seconds": round(eta, 2) if eta is not None else None,
            }
            print(json.dumps({"event": "batch_stage_complete", "run_id": msg.run_id, "result": result}, sort_keys=True), flush=True)
            return result

        response = handle_sqs_records(event, process_message=_process_message)
        print(json.dumps({"event": "sqs_batch_complete", "response": response}, sort_keys=True), flush=True)
        return response

    if event.get("action") == "enqueue" or event.get("mode") == "enqueue":
        all_new = bool(event.get("all_new") or event.get("allNew"))
        patient_limit = None if all_new else _parse_patient_limit(event)
        document_limit = None if all_new else _parse_document_limit(event)
        run_id = event.get("run_id")
        message_ids = orchestrate_initial_run(
            patient_limit=patient_limit,
            document_limit=document_limit,
            run_id=str(run_id).strip() if run_id else None,
            candidate_scan_limit=int(event.get("candidate_scan_limit")) if event.get("candidate_scan_limit") else None,
            stop_after_new=bool(event.get("stop_after_new")),
        )
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json; charset=utf-8"},
            "body": json.dumps({"status": "ok", "queued": len(message_ids), "message_ids": message_ids}, indent=2, sort_keys=True),
        }

    base_url = os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com").strip()
    client_id = os.environ.get("INSTINCT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("INSTINCT_CLIENT_SECRET", "").strip()
    patient_limit = _parse_patient_limit(event)
    document_limit = _parse_document_limit(event)

    client = InstinctApiSyncClient(base_url, client_id, client_secret)
    with psycopg.connect(_build_db_url(), row_factory=dict_row) as conn:
        clients_summary = sync_clients(client, conn, log=lambda _line: None)
        patients_summary = sync_patients(client, conn, log=lambda _line: None)
        documents_summary = sync_documents(
            client,
            conn,
            log=lambda _line: None,
            patient_limit=patient_limit,
            document_limit=document_limit,
        )

    payload = LambdaRunSummary(
        step="1.1-1.3",
        patient_limit=patient_limit,
        document_limit=document_limit,
        clients_fetched=clients_summary.fetched,
        clients_upserted=clients_summary.inserted,
        patients_fetched=patients_summary.fetched,
        patients_upserted=patients_summary.inserted,
        fetched=documents_summary.fetched,
        inserted=documents_summary.inserted,
        updated=documents_summary.updated,
        seconds=round(clients_summary.seconds + patients_summary.seconds + documents_summary.seconds, 3),
    )
    body = {
        "status": "ok",
        "summary": asdict(payload),
        "note": "step 1.1-1.3 cache sync lambda rewrite",
    }
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True),
    }
