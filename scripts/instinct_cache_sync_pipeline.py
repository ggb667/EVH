#!/usr/bin/env python3
from __future__ import annotations

"""Shared helpers for the simple Instinct cache-sync pipeline.

Step 1.1: clients -> public.instinct_owner_lookup_cache
Step 1.2: patients -> public.instinct_patient_lookup_cache
Step 1.3: client/patient documents -> public.rag_source_document
"""

import json
import os
import time
from hashlib import sha256
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Callable

from scripts.instinct_identity_sync import InstinctApiSyncClient, _account_payload, _ensure_identity_schema, _patient_payload


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _db_url() -> str:
    url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if url:
        return url
    from urllib.parse import quote

    return (
        f"postgresql://{os.environ['EVH_PGUSER']}:{quote(os.environ['EVH_PGPASSWORD'], safe='')}"
        f"@{os.environ['EVH_PGHOST']}:{os.environ['EVH_PGPORT']}/{os.environ['EVH_PGDATABASE']}?sslmode=require"
    )


def connect_db():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_db_url(), row_factory=dict_row)


def emit(log: Callable[[str], None], event: str, **payload: Any) -> None:
    record = {"event": event, "timestamp": now_utc().isoformat(), **payload}
    line = json.dumps(record, sort_keys=True, default=str)
    log(line)


def _smoothed_average(samples: list[float], *, alpha: float = 0.25) -> float:
    if not samples:
        return 0.0
    value = samples[0]
    for sample in samples[1:]:
        value = (alpha * sample) + ((1.0 - alpha) * value)
    return value


@dataclass(frozen=True)
class SyncSummary:
    fetched: int
    inserted: int
    updated: int
    seconds: float
    patients_scanned: int = 0
    documents_discovered: int = 0
    documents_ingested: int = 0
    documents_failed: int = 0


def _upsert_many(conn, sql: str, rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def sync_clients(client: InstinctApiSyncClient, conn, *, log: Callable[[str], None]) -> SyncSummary:
    started = time.perf_counter()
    accounts, _ = client.iter_accounts()
    rows = [_account_payload(account) for account in accounts]
    emit(log, "clients_fetch_done", fetched=len(rows))
    inserted = _upsert_many(
        conn,
        """
        INSERT INTO public.instinct_owner_lookup_cache (
            account_id, pims_code, owner_name, phone_primary, phone_all, email, address, city_state_zip,
            owner_name_lower, owner_name_last_first, phone_digits, updated_at, deleted_at, merged_into_account_id, synced_at
        ) VALUES (
            %(account_id)s, %(pims_code)s, %(owner_name)s, %(phone_primary)s, %(phone_all)s, %(email)s, %(address)s, %(city_state_zip)s,
            %(owner_name_lower)s, %(owner_name_last_first)s, %(phone_digits)s, %(updated_at)s, %(deleted_at)s, %(merged_into_account_id)s, %(synced_at)s
        )
        ON CONFLICT (account_id) DO UPDATE SET
            pims_code = EXCLUDED.pims_code,
            owner_name = EXCLUDED.owner_name,
            phone_primary = EXCLUDED.phone_primary,
            phone_all = EXCLUDED.phone_all,
            email = EXCLUDED.email,
            address = EXCLUDED.address,
            city_state_zip = EXCLUDED.city_state_zip,
            owner_name_lower = EXCLUDED.owner_name_lower,
            owner_name_last_first = EXCLUDED.owner_name_last_first,
            phone_digits = EXCLUDED.phone_digits,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at,
            merged_into_account_id = EXCLUDED.merged_into_account_id,
            synced_at = EXCLUDED.synced_at
        """,
        rows,
    )
    emit(log, "clients_upsert_done", upserted=inserted)
    return SyncSummary(fetched=len(rows), inserted=inserted, updated=0, seconds=round(time.perf_counter() - started, 3))


def sync_patients(client: InstinctApiSyncClient, conn, *, log: Callable[[str], None]) -> SyncSummary:
    started = time.perf_counter()
    patients: list[dict[str, Any]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["pageCursor"] = cursor
            params["pageDirection"] = "after"
        data = client._get("/v1/patients", params)
        page_rows = data.get("data") or data.get("patients") or data.get("items") or data.get("results") or []
        if isinstance(page_rows, list):
            patients.extend([row for row in page_rows if isinstance(row, dict)])
        metadata = data.get("metadata") if isinstance(data, dict) else None
        cursor = metadata.get("after") if isinstance(metadata, dict) else None
        if not cursor:
            break
    emit(log, "patients_fetch_done", fetched=len(patients))
    rows = [_patient_payload(patient) for patient in patients]
    inserted = _upsert_many(
        conn,
        """
        INSERT INTO public.instinct_patient_lookup_cache (
            patient_id, account_id, patient_name, patient_pims_code, birthdate, species, breed, color, sex,
            weight, owner_name, phone_primary, address, city_state_zip, updated_at, deleted_at, merged_into_patient_id, synced_at
        ) VALUES (
            %(patient_id)s, %(account_id)s, %(patient_name)s, %(patient_pims_code)s, %(birthdate)s, %(species)s, %(breed)s, %(color)s, %(sex)s,
            %(weight)s, %(owner_name)s, %(phone_primary)s, %(address)s, %(city_state_zip)s, %(updated_at)s, %(deleted_at)s, %(merged_into_patient_id)s, %(synced_at)s
        )
        ON CONFLICT (patient_id) DO UPDATE SET
            account_id = EXCLUDED.account_id,
            patient_name = EXCLUDED.patient_name,
            patient_pims_code = EXCLUDED.patient_pims_code,
            birthdate = EXCLUDED.birthdate,
            species = EXCLUDED.species,
            breed = EXCLUDED.breed,
            color = EXCLUDED.color,
            sex = EXCLUDED.sex,
            weight = EXCLUDED.weight,
            owner_name = EXCLUDED.owner_name,
            phone_primary = EXCLUDED.phone_primary,
            address = EXCLUDED.address,
            city_state_zip = EXCLUDED.city_state_zip,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at,
            merged_into_patient_id = EXCLUDED.merged_into_patient_id,
            synced_at = EXCLUDED.synced_at
        """,
        rows,
    )
    emit(log, "patients_upsert_done", upserted=inserted)
    return SyncSummary(fetched=len(rows), inserted=inserted, updated=0, seconds=round(time.perf_counter() - started, 3))


def sync_documents(
    client: InstinctApiSyncClient,
    conn,
    *,
    log: Callable[[str], None],
    patient_limit: int | None = None,
    document_limit: int | None = None,
    candidate_scan_limit: int | None = None,
    stop_after_first_ingestion: bool = False,
    patient_start: int = 0,
    max_seconds: float | None = None,
) -> SyncSummary:
    import requests

    def fetch_medical_history_visits(patient_id: str, *, timeout: int = 30, retries: int = 3) -> dict[str, Any]:
        token = os.environ.get("TOKEN", "").strip()
        if not token:
            raise RuntimeError("TOKEN is required for Instinct GraphQL document fetches")
        query = """
query medicalHistoryVisits($patientId: ID!, $chartTypes: [ChartType]) {
  patient(id: $patientId) {
    id
    name
    pimsId
    account { id pimsCode }
    __typename
  }
  charts(patientId: $patientId, chartTypes: $chartTypes) {
    __typename
    ... on ChartFile {
      id
      filename
      label
      contentType
      type
      insertedAt
    }
    ... on ChartDocument {
      id
      label
      description
      type
      insertedAt
    }
    ... on Diagnostic {
      id
      label
      diagnosticType
      displayStatus
      insertedAt
    }
  }
}
""".strip()
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            started = time.perf_counter()
            try:
                resp = requests.post(
                    "https://evh.api.instinctvet.com/graphql",
                    json={"query": query, "variables": {"patientId": patient_id, "chartTypes": ["CHART_DOCUMENT", "CHART_FILE", "DIAGNOSTIC"]}},
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    timeout=timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
                if "errors" in payload:
                    raise RuntimeError(json.dumps(payload["errors"], sort_keys=True))
                if attempt > 1:
                    emit(log, "documents_patient_fetch_retry_success", patient_id=patient_id, attempt=attempt, elapsed_seconds=round(time.perf_counter() - started, 3))
                return payload["data"]
            except Exception as exc:
                last_error = exc
                emit(
                    log,
                    "documents_patient_fetch_retry",
                    patient_id=patient_id,
                    attempt=attempt,
                    retries=retries,
                    elapsed_seconds=round(time.perf_counter() - started, 3),
                    error=str(exc),
                )
                if attempt >= retries:
                    raise
                time.sleep(min(2 ** (attempt - 1), 5))
        raise last_error or RuntimeError("unreachable")

    started = time.perf_counter()
    os.environ["TOKEN"] = os.environ.get("TOKEN", "").strip() or client._auth()
    with conn.cursor() as cur:
        cur.execute("select patient_id from public.instinct_patient_lookup_cache order by patient_id")
        patient_ids = [str(row["patient_id"]) for row in cur.fetchall()]
    patient_start = max(0, int(patient_start or 0))
    if patient_limit is not None:
        patient_ids = patient_ids[patient_start:patient_start + patient_limit]
    else:
        patient_ids = patient_ids[patient_start:]
    emit(log, "documents_patient_list_ready", patients=len(patient_ids))

    existing_by_doc_id: dict[str, tuple[str | None, str | None]] = {}
    existing_query_started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_pdf_id, status, metadata
            FROM public.rag_source_document
            WHERE ingestion_complete = true
            """
        )
        for row in cur.fetchall():
            metadata = row.get("metadata") if isinstance(row, dict) else {}
            chart_hash = metadata.get("chart_hash") if isinstance(metadata, dict) else None
            existing_by_doc_id[str(row["document_pdf_id"])] = (str(row.get("status") or ""), str(chart_hash) if chart_hash else None)
    existing_query_seconds = time.perf_counter() - existing_query_started
    emit(log, "db_query_complete", query="existing_source_documents", rows=len(existing_by_doc_id), seconds=round(existing_query_seconds, 4))

    upsert_sql = """
        INSERT INTO public.rag_source_document (
            document_pdf_id, client_id, patient_id, source_name, source_uri, document_label, status, ingestion_complete, metadata, synced_at,
            content_hash, content_length, page_count, chunk_count, summary, processed_at, table_records
        ) VALUES (
            %(document_pdf_id)s, %(client_id)s, %(patient_id)s, %(source_name)s, %(source_uri)s, %(document_label)s, %(status)s, %(ingestion_complete)s, %(metadata)s, %(synced_at)s,
            %(content_hash)s, %(content_length)s, %(page_count)s, %(chunk_count)s, %(summary)s, %(processed_at)s, %(table_records)s
        )
        ON CONFLICT (document_pdf_id) DO UPDATE SET
            client_id = EXCLUDED.client_id,
            patient_id = EXCLUDED.patient_id,
            source_name = EXCLUDED.source_name,
            source_uri = EXCLUDED.source_uri,
            document_label = EXCLUDED.document_label,
            status = EXCLUDED.status,
            ingestion_complete = EXCLUDED.ingestion_complete,
            metadata = EXCLUDED.metadata,
            synced_at = EXCLUDED.synced_at
    """
    rows: list[dict[str, Any]] = []
    first_new_processed = False
    fetch_elapsed_seconds: list[float] = []
    skipped_count = 0
    upsert_candidate_count = 0
    documents_ingested = 0
    documents_failed = 0
    patient_api_seconds = 0.0
    candidate_processing_seconds = 0.0
    document_limit = document_limit if document_limit and document_limit > 0 else None
    for idx, patient_id in enumerate(patient_ids, start=1):
        if max_seconds is not None and time.perf_counter() - started >= max_seconds:
            emit(log, "documents_time_budget_reached", next_patient=patient_start + idx - 1)
            break
        if candidate_scan_limit is not None and idx > candidate_scan_limit:
            emit(log, "documents_candidate_scan_limit_reached", candidate_scan_limit=candidate_scan_limit, completed=idx - 1)
            break
        patient_fetch_start = time.perf_counter()
        emit(log, "documents_patient_fetch_start", patient_id=patient_id, index=idx, total=len(patient_ids))
        api_started = time.perf_counter()
        data = fetch_medical_history_visits(patient_id, timeout=30)
        patient_api_seconds += time.perf_counter() - api_started
        patient = data.get("patient") if isinstance(data, dict) else {}
        charts = data.get("charts") if isinstance(data, dict) else []
        client_id = normalize_text((patient or {}).get("account", {}).get("id")) if isinstance(patient, dict) else ""
        if not client_id:
            raise RuntimeError(f"Instinct patient {patient_id} has no real client/account id; refusing document upsert")
        candidate_started = time.perf_counter()
        for chart in charts if isinstance(charts, list) else []:
            if not isinstance(chart, dict):
                continue
            doc_id = normalize_text(chart.get("id"))
            if not doc_id.isdigit():
                continue
            chart_hash = sha256(json.dumps(chart, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            existing_status, existing_hash = existing_by_doc_id.get(doc_id, (None, None))
            if existing_status == "complete" and existing_hash == chart_hash:
                skipped_count += 1
                continue
            if document_limit is not None and len(rows) >= document_limit:
                break
            upsert_candidate_count += 1
            rows.append(
                {
                    "document_pdf_id": int(doc_id),
                    "client_id": client_id,
                    "patient_id": int(patient_id) if patient_id.isdigit() else None,
                    "source_name": normalize_text(chart.get("filename") or chart.get("name") or chart.get("label")) or None,
                    "source_uri": None,
                    "document_label": normalize_text(chart.get("label")) or None,
                    # This stage has only discovered chart metadata.  It has
                    # not downloaded, extracted/OCR'd, chunked, embedded, or
                    # persisted document content; never represent discovery
                    # as completed ingestion.
                    "status": "pending",
                    "ingestion_complete": False,
                    "metadata": json.dumps({"instinct_type": chart.get("__typename"), "chart": chart, "chart_hash": chart_hash}, default=str),
                    "synced_at": now_utc(),
                    "content_hash": chart_hash,
                    "content_length": 0,
                    "page_count": 0,
                    "chunk_count": 0,
                    "summary": "",
                    "processed_at": now_utc(),
                    "table_records": json.dumps([]),
                }
            )
            emit(log, "new_document_found", document_pdf_id=doc_id, patient_id=patient_id)
            ingestion_succeeded = False
            try:
                from scripts.instinct_pdf_chunker import ChunkingConfig, PatientPdfSource, chunk_patient_pdf_timed, load_into_postgres
                token = os.environ.get("TOKEN", "").strip()
                mutation = "mutation createChartFileUrl($id: ID!, $inline: Boolean) { createChartFileUrl(id: $id, inline: $inline) }"
                url_response = requests.post(
                    "https://evh.api.instinctvet.com/graphql",
                    json={"query": mutation, "variables": {"id": doc_id, "inline": True}},
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    timeout=30,
                )
                url_response.raise_for_status()
                source_uri = str((url_response.json().get("data") or {}).get("createChartFileUrl") or "")
                source = PatientPdfSource(
                    patient_id=str(patient_id),
                    patient_name=str(chart.get("label") or chart.get("filename") or doc_id),
                    pdf_id=doc_id,
                    pdf_url=source_uri,
                    client_id=str(client_id),
                )
                documents, page_count, timing = chunk_patient_pdf_timed(source, ChunkingConfig(), defer_no_text_page_threshold=8)
                if not documents:
                    raise RuntimeError("ingestion produced no text chunks")
                embed_seconds, postgres_seconds = load_into_postgres(
                    database_url=_db_url(), table_name="public.pms_page_chunk",
                    source_name=str(chart.get("filename") or chart.get("label") or doc_id),
                    source_uri=source_uri, documents=documents, vector_dimensions=1536,
                )
                for row in rows:
                    if str(row["document_pdf_id"]) == doc_id:
                        row.update({"source_uri": source_uri, "status": "complete", "ingestion_complete": True, "page_count": page_count, "chunk_count": len(documents), "processed_at": now_utc()})
                        break
                ingestion_succeeded = True
                emit(log, "new_document_processed", document_pdf_id=doc_id, page_count=page_count, chunk_count=len(documents), embed_seconds=round(embed_seconds, 3), postgres_seconds=round(postgres_seconds, 3), **{k: round(float(v), 3) for k, v in timing.items() if isinstance(v, (int, float))})
            except Exception as exc:
                documents_failed += 1
                emit(log, "document_ingestion_failed", document_pdf_id=doc_id, error=str(exc))
            else:
                documents_ingested += 1
            if stop_after_first_ingestion and ingestion_succeeded:
                emit(log, "stop_after_first_ingestion", document_pdf_id=doc_id, message="new document found, and processed")
                break
        candidate_processing_seconds += time.perf_counter() - candidate_started
        if document_limit is not None and len(rows) >= document_limit:
            emit(log, "documents_document_limit_reached", document_limit=document_limit, completed=idx, total=len(patient_ids))
            break
        elapsed = time.perf_counter() - patient_fetch_start
        fetch_elapsed_seconds.append(elapsed)
        running_avg = sum(fetch_elapsed_seconds) / len(fetch_elapsed_seconds)
        smoothed_avg = _smoothed_average(fetch_elapsed_seconds)
        remaining = max(0, len(patient_ids) - idx)
        eta_seconds = smoothed_avg * remaining
        processed_so_far = idx
        processed_rate_per_hour = (processed_so_far / max(1e-6, sum(fetch_elapsed_seconds))) * 3600.0
        emit(
            log,
            "documents_patient_fetch_done",
            patient_id=patient_id,
            charts=len(charts) if isinstance(charts, list) else 0,
            elapsed_seconds=round(elapsed, 3),
            running_avg_fetch_seconds=round(running_avg, 3),
            smoothed_avg_fetch_seconds=round(smoothed_avg, 3),
            estimated_remaining_seconds=round(eta_seconds, 1),
            estimated_total_seconds=round(smoothed_avg * len(patient_ids), 1),
            patients_per_hour=round(processed_rate_per_hour, 1),
            skipped_documents=skipped_count,
            pending_upserts=upsert_candidate_count,
            completed=idx,
            total=len(patient_ids),
        )

    upsert_started = time.perf_counter()
    inserted = _upsert_many(conn, upsert_sql, rows)
    upsert_seconds = time.perf_counter() - upsert_started
    total_seconds = time.perf_counter() - started
    emit(log, "db_upsert_complete", rows=len(rows), seconds=round(upsert_seconds, 4))
    emit(
        log,
        "documents_timing_summary",
        total_seconds=round(total_seconds, 4),
        patient_list_and_auth_seconds=round(max(0.0, existing_query_started - started), 4),
        existing_documents_query_seconds=round(existing_query_seconds, 4),
        patient_api_seconds=round(patient_api_seconds, 4),
        candidate_processing_seconds=round(candidate_processing_seconds, 4),
        database_upsert_seconds=round(upsert_seconds, 4),
        patients_scanned=idx if patient_ids else 0,
        document_candidates=len(rows),
    )
    emit(
        log,
        "documents_upsert_done",
        upserted=inserted,
        average_fetch_seconds=round(sum(fetch_elapsed_seconds) / len(fetch_elapsed_seconds), 3) if fetch_elapsed_seconds else 0.0,
        smoothed_fetch_seconds=round(_smoothed_average(fetch_elapsed_seconds), 3) if fetch_elapsed_seconds else 0.0,
        total_fetch_seconds=round(sum(fetch_elapsed_seconds), 3),
        skipped_documents=skipped_count,
        pending_upserts=upsert_candidate_count,
        patients_per_hour=round((len(patient_ids) / max(1e-6, sum(fetch_elapsed_seconds))) * 3600.0, 1) if fetch_elapsed_seconds else 0.0,
    )
    return SyncSummary(fetched=len(rows), inserted=inserted, updated=0, seconds=round(total_seconds, 3), patients_scanned=idx if patient_ids else 0,
                       documents_discovered=len(rows), documents_ingested=documents_ingested, documents_failed=documents_failed)
