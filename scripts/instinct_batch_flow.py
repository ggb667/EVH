from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from scripts.instinct_cache_sync_pipeline import connect_db, emit, sync_clients, sync_documents, sync_patients
from scripts.instinct_identity_sync import InstinctApiSyncClient

try:  # pragma: no cover - boto3 is present in AWS, optional in tests
    import boto3
except Exception:  # pragma: no cover
    boto3 = None


@dataclass(frozen=True)
class BatchMessage:
    stage: str
    patient_limit: int | None = None
    document_limit: int | None = None
    run_id: str | None = None
    checkpoint: str | None = None
    candidate_scan_limit: int | None = None
    stop_after_new: bool = False


def parse_message(body: dict[str, Any]) -> BatchMessage:
    return BatchMessage(
        stage=str(body.get("stage", "")).strip(),
        patient_limit=_int_or_none(body.get("patient_limit")),
        document_limit=_int_or_none(body.get("document_limit")),
        run_id=str(body.get("run_id", "")).strip() or None,
        checkpoint=str(body.get("checkpoint", "")).strip() or None,
        candidate_scan_limit=_int_or_none(body.get("candidate_scan_limit")),
        stop_after_new=bool(body.get("stop_after_new")),
    )


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def _queue_client():
    queue_url = os.environ.get("EVH_IMPORT_QUEUE_URL", "").strip()
    if not queue_url:
        raise RuntimeError("EVH_IMPORT_QUEUE_URL is required for batch orchestration")
    if boto3 is None:
        raise RuntimeError("boto3 is required for batch orchestration")
    return boto3.client("sqs"), queue_url


def enqueue_work(items: Iterable[BatchMessage]) -> list[str]:
    client, queue_url = _queue_client()
    sent: list[str] = []
    for item in items:
        response = client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(asdict(item), sort_keys=True))
        sent.append(str(response.get("MessageId", "")))
    return sent


def orchestrate_initial_run(*, patient_limit: int | None = 1000, document_limit: int | None = 1000, run_id: str | None = None, candidate_scan_limit: int | None = None, stop_after_new: bool = False) -> list[str]:
    return enqueue_work(
        [
            BatchMessage(stage="clients", run_id=run_id),
            BatchMessage(stage="patients", run_id=run_id),
            BatchMessage(stage="documents", patient_limit=patient_limit, document_limit=document_limit, run_id=run_id, candidate_scan_limit=candidate_scan_limit, stop_after_new=stop_after_new),
        ]
    )


def handle_sqs_records(event: dict[str, Any], *, process_message: Callable[[BatchMessage], dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    for record in _lambda_event_records(event):
        message_id = str(record.get("messageId", ""))
        try:
            body = json.loads(record.get("body") or "{}")
            msg = parse_message(body if isinstance(body, dict) else {})
            result = process_message(msg)
            results.append({"messageId": message_id, "status": "ok", "result": result})
        except Exception as exc:  # noqa: BLE001
            failures.append({"itemIdentifier": message_id})
            results.append({"messageId": message_id, "status": "failed", "error": str(exc)})
    return {"batchItemFailures": failures, "results": results}


def _lambda_event_records(event: dict[str, Any]) -> list[dict[str, Any]]:
    if "Records" in event and isinstance(event["Records"], list):
        return [record for record in event["Records"] if isinstance(record, dict)]
    return []


def worker_lambda_handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    client = InstinctApiSyncClient(
        os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com").strip(),
        os.environ.get("INSTINCT_CLIENT_ID", "").strip(),
        os.environ.get("INSTINCT_CLIENT_SECRET", "").strip(),
    )
    failures: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    with connect_db() as conn:
        for record in _lambda_event_records(event):
            message_id = str(record.get("messageId", ""))
            try:
                body = json.loads(record.get("body") or "{}")
                msg = parse_message(body if isinstance(body, dict) else {})
                result = _process_message(client, conn, msg)
                results.append({"messageId": message_id, "status": "ok", "result": result})
            except Exception as exc:  # noqa: BLE001
                failures.append({"itemIdentifier": message_id})
                results.append({"messageId": message_id, "status": "failed", "error": str(exc)})
    return {
        "batchItemFailures": failures,
        "results": results,
    }


def _process_message(client: InstinctApiSyncClient, conn, msg: BatchMessage) -> dict[str, Any]:
    log_lines: list[str] = []
    log: Callable[[str], None] = log_lines.append
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
        )
    else:
        raise RuntimeError(f"unknown batch stage: {msg.stage!r}")
    return {
        "stage": msg.stage,
        "fetched": summary.fetched,
        "inserted": summary.inserted,
        "updated": summary.updated,
        "seconds": summary.seconds,
        "log_tail": log_lines[-10:],
    }
