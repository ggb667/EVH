from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from scripts.instinct_cache_sync_pipeline import sync_clients, sync_documents, sync_patients
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
    base_url = os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com").strip()
    client_id = os.environ.get("INSTINCT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("INSTINCT_CLIENT_SECRET", "").strip()
    process_all = bool(event.get("process_all"))
    patient_limit = None if process_all else _parse_patient_limit(event)
    document_limit = None if process_all else _parse_document_limit(event)

    client = InstinctApiSyncClient(base_url, client_id, client_secret)
    with psycopg.connect(_build_db_url(), row_factory=dict_row) as conn:
        clients_summary = sync_clients(client, conn, log=print)
        patients_summary = sync_patients(client, conn, log=print)
        documents_summary = sync_documents(
            client,
            conn,
            log=print,
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
    print(json.dumps({
        "event": "COMPLETE",
        "message": "linear ingestion completed normally",
        "stop_reason": "limits_or_exhausted",
        "patient_limit": patient_limit,
        "document_limit": document_limit,
        "documents_fetched": documents_summary.fetched,
        "seconds": payload.seconds,
    }, sort_keys=True), flush=True)
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
