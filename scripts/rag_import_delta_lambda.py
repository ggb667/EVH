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
    next_patient: int
    complete: bool
    documents_discovered: int
    documents_ingested: int
    documents_failed: int


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


def _lambda_handler_unlocked(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    base_url = os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com").strip()
    client_id = os.environ.get("INSTINCT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("INSTINCT_CLIENT_SECRET", "").strip()
    process_all = bool(event.get("process_all"))
    patient_limit = None if process_all else _parse_patient_limit(event)
    document_limit = None if process_all else _parse_document_limit(event)
    patient_start = max(0, int(event.get("start_patient", event.get("next_patient", event.get("patient_start", 0))) or 0))
    has_cursor = any(key in event for key in ("start_patient", "next_patient", "patient_start"))
    batch_size = max(1, int(event.get("patient_batch", patient_limit or 500) or 500))
    if patient_limit is not None:
        remaining_patients = max(patient_limit - patient_start, 0)
        if remaining_patients:
            batch_size = min(batch_size, remaining_patients)
    # Leave a generous handoff margin for checkpoint/DB commit and async
    # continuation. A document extraction or embedding can consume time
    # after the patient-loop guard, so do not run right up to Lambda's limit.
    requested_max_seconds = min(float(event.get("max_seconds", 600) or 600), 600.0)

    client = InstinctApiSyncClient(base_url, client_id, client_secret)
    with psycopg.connect(_build_db_url(), row_factory=dict_row) as conn:
        run_id = str(event.get("run_id") or "").strip()
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS public.rag_import_run (
                run_id text PRIMARY KEY, started_at timestamptz NOT NULL, next_patient integer NOT NULL DEFAULT 0,
                patients_scanned integer NOT NULL DEFAULT 0, documents_found integer NOT NULL DEFAULT 0,
                documents_ingested integer NOT NULL DEFAULT 0, documents_failed integer NOT NULL DEFAULT 0,
                status text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())""")
            recover_requested = bool(event.get("recover") or event.get("resume"))
            if not run_id and recover_requested and not has_cursor:
                cur.execute("""SELECT run_id, next_patient FROM public.rag_import_run
                    WHERE status='FAILED' ORDER BY updated_at DESC LIMIT 1""")
                recovered = cur.fetchone()
                if recovered:
                    run_id = str(recovered["run_id"])
                    patient_start = max(patient_start, int(recovered["next_patient"] or 0))
                    print(json.dumps({"event": "RUN_RECOVERED", "run_id": run_id,
                                      "next_patient": patient_start}, sort_keys=True), flush=True)
            if not run_id:
                run_id = f"rd-{int(time.time())}"
            with conn.cursor() as lock_cur:
                lock_cur.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS acquired", (run_id,))
                lock_row = lock_cur.fetchone() or {}
                if not bool(lock_row.get("acquired")):
                    print(json.dumps({"event": "RUN_ALREADY_ACTIVE", "run_id": run_id, "patient_start": patient_start}, sort_keys=True), flush=True)
                    return {
                        "statusCode": 202,
                        "headers": {"content-type": "application/json; charset=utf-8"},
                        "body": json.dumps({"status": "already_running", "run_id": run_id}, sort_keys=True),
                    }
            if run_id and not has_cursor:
                cur.execute("SELECT next_patient, status FROM public.rag_import_run WHERE run_id=%s", (run_id,))
                existing_run = cur.fetchone()
                if existing_run and str(existing_run.get("status") or "") == "FAILED":
                    recovered_start = max(patient_start, int(existing_run.get("next_patient") or 0))
                    if recovered_start > patient_start:
                        patient_start = recovered_start
                        if patient_limit is not None:
                            remaining_patients = max(patient_limit - patient_start, 0)
                            batch_size = min(max(1, batch_size), remaining_patients) if remaining_patients else 1
                        print(json.dumps({"event": "RUN_CURSOR_RESUMED", "run_id": run_id, "next_patient": patient_start}, sort_keys=True), flush=True)
            cur.execute("""INSERT INTO public.rag_import_run (run_id, started_at, next_patient, status)
                VALUES (%s, now(), %s, 'FAILED') ON CONFLICT (run_id) DO UPDATE SET status='FAILED', updated_at=now()""", (run_id, patient_start))
        conn.commit()
        clients_summary = sync_clients(client, conn, log=print)
        patients_summary = sync_patients(client, conn, log=print)
        remaining_seconds = None
        if context is not None and hasattr(context, "get_remaining_time_in_millis"):
            try:
                remaining_seconds = max(0.0, (float(context.get_remaining_time_in_millis()) / 1000.0) - 35.0)
            except Exception:
                remaining_seconds = None
        document_max_seconds = requested_max_seconds if remaining_seconds is None else min(requested_max_seconds, remaining_seconds)

        def checkpoint(progress: dict[str, Any]) -> None:
            checkpoint_status = "COMPLETE" if str(progress.get("status") or "").upper() == "COMPLETE" else "FAILED"
            checkpoint_progress = {**progress, "status": checkpoint_status}
            with conn.cursor() as progress_cur:
                progress_cur.execute(
                    """UPDATE public.rag_import_run
                    SET next_patient = GREATEST(next_patient, %s),
                        status = %s,
                        updated_at = now()
                    WHERE run_id = %s""",
                    (
                        int(progress.get("next_patient") or patient_start),
                        checkpoint_status,
                        run_id,
                    ),
                )
            conn.commit()
            print(json.dumps({"event": "RUN_CHECKPOINT", "run_id": run_id, **checkpoint_progress}, sort_keys=True, default=str), flush=True)

        documents_summary = sync_documents(
            client,
            conn,
            log=print,
            document_limit=document_limit,
            patient_limit=batch_size,
            patient_start=patient_start,
            max_seconds=document_max_seconds,
            progress_callback=checkpoint,
        )
        processed_patients = documents_summary.patients_scanned
        next_patient = patient_start + int(processed_patients)
        limit_reached = patient_limit is not None and next_patient >= patient_limit
        time_budget_reached = documents_summary.stop_reason == "time_budget"
        complete = (int(processed_patients) == 0 or (int(processed_patients) < batch_size and not time_budget_reached) or limit_reached) and documents_summary.documents_failed == 0
        with conn.cursor() as cur:
            cur.execute("""UPDATE public.rag_import_run
                SET next_patient=GREATEST(next_patient, %s),
                    patients_scanned=GREATEST(patients_scanned, %s),
                    documents_found=GREATEST(documents_found, %s),
                    documents_ingested=GREATEST(documents_ingested, %s),
                    documents_failed=GREATEST(documents_failed, %s),
                    status=%s,
                    updated_at=now()
                WHERE run_id=%s""", (next_patient, next_patient,
                documents_summary.fetched, documents_summary.inserted, documents_summary.documents_failed,
                'COMPLETE' if complete else 'FAILED', run_id))
        conn.commit()

    processed_patients = documents_summary.patients_scanned
    next_patient = patient_start + int(processed_patients)
    limit_reached = patient_limit is not None and next_patient >= patient_limit
    # Zero-progress pages are terminal, not continuation candidates. Time-budget
    # stops with forward progress are continuation candidates, not completion.
    time_budget_reached = documents_summary.stop_reason == "time_budget"
    complete = (int(processed_patients) == 0 or (int(processed_patients) < batch_size and not time_budget_reached) or limit_reached) and documents_summary.documents_failed == 0
    with psycopg.connect(_build_db_url(), row_factory=dict_row) as state_conn:
        with state_conn.cursor() as cur:
            cur.execute("""UPDATE public.rag_import_run
                SET next_patient=GREATEST(next_patient, %s),
                    patients_scanned=GREATEST(patients_scanned, %s),
                    documents_found=GREATEST(documents_found, %s),
                    documents_ingested=GREATEST(documents_ingested, %s),
                    documents_failed=GREATEST(documents_failed, %s),
                    status=%s,
                    updated_at=now()
                WHERE run_id=%s""", (next_patient, next_patient,
                documents_summary.fetched, documents_summary.inserted, documents_summary.documents_failed,
                'COMPLETE' if complete else 'FAILED', run_id))
        state_conn.commit()
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
        next_patient=next_patient,
        complete=complete,
        documents_discovered=documents_summary.documents_discovered,
        documents_ingested=documents_summary.documents_ingested,
        documents_failed=documents_summary.documents_failed,
    )
    print(json.dumps({
        "event": "COMPLETE" if complete else "CONTINUE",
        "message": "linear ingestion completed normally",
        "stop_reason": "exhausted" if complete else "continuation_scheduled",
        "patient_limit": patient_limit,
        "document_limit": document_limit,
        "documents_discovered": documents_summary.documents_discovered,
        "documents_ingested": documents_summary.documents_ingested,
        "documents_failed": documents_summary.documents_failed,
        "seconds": payload.seconds,
        "next_patient": next_patient,
        "stop_reason": documents_summary.stop_reason,
    }, sort_keys=True), flush=True)
    # Never self-invoke without forward progress.  A cursor at/after the
    # available patient set can otherwise create an unbounded Lambda
    # recursion (especially for process_all runs whose final page is empty).
    should_continue = (
        not complete
        and int(processed_patients) > 0
        and next_patient > patient_start
        # A failed document route is not recoverable by blindly advancing the
        # cursor; stop and surface the failed run for diagnosis instead of
        # recursively propagating half-baked failures across the full set.
        and documents_summary.documents_failed == 0
    )
    if should_continue:
        import boto3
        boto3.client("lambda").invoke(
            FunctionName=os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "evh_instinct_rag_import_delta"),
            InvocationType="Event",
            Payload=json.dumps({
                "start_patient": next_patient,
                "patient_batch": batch_size,
                "run_id": run_id,
                **({"process_all": True} if process_all else {}),
                **({"patient_limit": patient_limit} if patient_limit is not None else {}),
                **({"document_limit": document_limit} if document_limit is not None else {}),
                "max_seconds": requested_max_seconds,
                "continuation_token": event.get("_continuation_token", ""),
            }).encode(),
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


def lambda_handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    """Run at most one importer invocation while preserving authenticated self-handoff."""
    lock_conn = None
    token = str(event.get("continuation_token") or "").strip()
    if not token:
        token = f"{time.time_ns()}-{os.urandom(12).hex()}"
    event = dict(event)
    event["_continuation_token"] = token
    try:
        lock_conn = psycopg.connect(_build_db_url(), connect_timeout=15)
        with lock_conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS public.rag_import_lease "
                "(lease_key text PRIMARY KEY, token text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())"
            )
            cur.execute(
                """INSERT INTO public.rag_import_lease(lease_key,token) VALUES ('import',%s)
                ON CONFLICT (lease_key) DO UPDATE SET token=EXCLUDED.token,updated_at=now()
                WHERE public.rag_import_lease.token=%s OR public.rag_import_lease.updated_at < now()-interval '20 minutes'
                RETURNING token""",
                (token, token),
            )
            acquired = cur.fetchone() is not None
            competing_lease = None
            if not acquired:
                cur.execute("SELECT token, updated_at FROM public.rag_import_lease WHERE lease_key='import'")
                competing_lease = cur.fetchone()
            lock_conn.commit()
        if not acquired:
            request_id = getattr(context, "aws_request_id", None) if context is not None else None
            owner_token, owner_updated_at = competing_lease or (None, None)
            # Keep the refusal diagnosable in CloudWatch even though no run row
            # is created for an overlap. Tokens identify the competing lease
            # only; they contain no credentials or document data.
            print(
                json.dumps(
                    {
                        "event": "RUN_ALREADY_RUNNING",
                        "status": "refused",
                        "requested_run_id": event.get("run_id"),
                        "request_id": request_id,
                        "requested_token": token,
                        "owner_token": owner_token,
                        "owner_updated_at": owner_updated_at.isoformat() if owner_updated_at else None,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            return {"statusCode": 409, "body": json.dumps({"error": "RUN_ALREADY_RUNNING"})}
        return _lambda_handler_unlocked(event, context)
    finally:
        if lock_conn is not None:
            try:
                with lock_conn.cursor() as cur:
                    cur.execute("DELETE FROM public.rag_import_lease WHERE lease_key='import' AND token=%s", (token,))
                lock_conn.commit()
            finally:
                lock_conn.close()
