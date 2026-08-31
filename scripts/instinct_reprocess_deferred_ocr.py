#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""Reprocess deferred no-text-layer Instinct PDFs through OCR and vector load.

The deferred folder is the unprocessed queue: PDFs stay there until they are
successfully reprocessed, then they move into the processed folder.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import sys
import traceback
import math
import shutil
import time
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from psycopg.rows import dict_row

from scripts.instinct_pdf_chunker import (
    ChunkingConfig,
    DEFAULT_DEFERRED_OCR_TABLE_NAME,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_OCR_PAGE_TABLE_NAME,
    DEFAULT_SOURCE_DOCUMENT_TABLE_NAME,
    DEFAULT_TABLE_NAME,
    PatientPdfSource,
    build_deferred_ocr_schema_sql,
    build_ocr_page_upsert_sql,
    build_ocr_page_schema_sql,
    build_source_document_schema_sql,
    chunk_pdf_pages,
    ensure_vector_schema,
    ocr_pdf_text_pages,
    safe_ocr_pdf_text_pages,
    safe_extract_pdf_text_pages,
    load_into_postgres,
    run_psql,
    load_term_index,
    sql_quote,
)
from scripts.instinct_pdf_family_sampler import create_chart_file_url, fetch_medical_history_visits


def _print(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)


def _format_seconds(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _print_progress(
    *,
    run_started_at: float,
    ocred_count: int,
    ocr_not_reached_deferred_count: int,
    total_to_process: int,
) -> None:
    elapsed_s = max(time.monotonic() - run_started_at, 1e-9)
    velocity = ocred_count / elapsed_s
    remaining_files = max(0, total_to_process - (ocred_count + ocr_not_reached_deferred_count))
    eta_s = remaining_files / velocity if velocity > 0 else 0.0
    print(
        "PROGRESS_LINE | "
        f"Files Processed: ({ocred_count}) | "
        f"Number of Files Remaining: ({remaining_files}) | "
        f"failed={ocr_not_reached_deferred_count} | "
        f"elapsed_s={elapsed_s:.1f} | "
        f"velocity_fps={velocity:.4f} | "
        f"eta={_format_seconds(eta_s)}",
        flush=True,
    )


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def _should_retry_worker_result(worker_result: dict[str, Any]) -> bool:
    return not bool(worker_result.get("ok")) and str(worker_result.get("error_type") or "") in {"SignalError", "TimeoutError", "WorkerLost"}


def _emit_result(result: dict[str, Any]) -> None:
    print(f"RESULT {json.dumps(result, sort_keys=True)}", flush=True)


def _worker_job_from_payload(payload: dict[str, Any]) -> int:
    batch_rows = payload["batch_rows"]
    args = argparse.Namespace(
        database_url=payload["database_url"],
        table_name=payload["table_name"],
        deferred_ocr_table_name=payload["deferred_ocr_table_name"],
        source_document_table_name=payload["source_document_table_name"],
        ocr_page_table_name=payload["ocr_page_table_name"],
        embedding_model=payload["embedding_model"],
        vector_dimensions=payload["vector_dimensions"],
        chunk_size=payload["chunk_size"],
        chunk_overlap=payload["chunk_overlap"],
        dictionary_csv=payload.get("dictionary_csv", ""),
    )
    processed_pdf_dir = Path(payload["processed_pdf_dir"])
    term_index = load_term_index(Path(args.dictionary_csv) if args.dictionary_csv else None)
    config = ChunkingConfig(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    batch_ok = 0
    batch_failed = 0
    try:
        for batch_row in batch_rows:
            row = dict(batch_row["row"])
            local_pdf_path = Path(batch_row["local_pdf_path"])
            did_complete, ocr_attempted = _process_one_row(
                row=row,
                local_pdf_path=local_pdf_path,
                args=args,
                processed_pdf_dir=processed_pdf_dir,
                term_index=term_index,
                config=config,
            )
            batch_ok += 1 if did_complete else 0
            _emit_result({
                "document_pdf_id": str(row.get("document_pdf_id")),
                "filename": row.get("filename"),
                "status": "complete",
                "ok": True,
                "did_complete": did_complete,
                "ocr_attempted": ocr_attempted,
                "error_type": None,
                "error": None,
            })
        _emit_result({"status": "batch_complete", "ok": True, "batch_ok": batch_ok, "batch_failed": batch_failed})
        return 0
    except BaseException as exc:
        batch_failed += 1
        _emit_result({
            "document_pdf_id": str(row.get("document_pdf_id")) if "row" in locals() else None,
            "filename": row.get("filename") if "row" in locals() else None,
            "status": "failed",
            "ok": False,
            "did_complete": False,
            "ocr_attempted": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        _emit_result({"status": "batch_complete", "ok": False, "batch_ok": batch_ok, "batch_failed": batch_failed})
        return 0


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


def _update_status_sql(table: str, document_pdf_id: str, status: str, note: str | None = None) -> str:
    note_sql = "NULL" if note is None else sql_quote(note)
    return f"""
UPDATE {table}
SET status = {sql_quote(status)},
    metadata = CASE
        WHEN {note_sql} IS NULL THEN metadata
        ELSE COALESCE(metadata, '{{}}'::jsonb) || jsonb_build_object('reprocess_note', {note_sql})
    END
WHERE document_pdf_id = {sql_quote(document_pdf_id)};
""".strip()


def _parse_deferred_filename(filename: str) -> dict[str, str | None]:
    stem = Path(filename).stem
    parts = stem.split("_", 3)
    if len(parts) < 4:
        return {
            "document_pdf_id": None,
            "client_id": None,
            "patient_id": None,
            "original_filename": None,
        }
    document_pdf_id, client_id, patient_id, original_filename = parts[0], parts[1], parts[2], parts[3]
    return {
        "document_pdf_id": document_pdf_id or None,
        "client_id": client_id or None,
        "patient_id": patient_id or None,
        "original_filename": original_filename or None,
    }


def _move_pdf_to_processed_dir(source_uri: str | None, processed_pdf_dir: Path) -> Path | None:
    if not source_uri:
        return None
    source_path = Path(source_uri)
    if not source_path.is_file():
        return None
    processed_pdf_dir.mkdir(parents=True, exist_ok=True)
    destination = processed_pdf_dir / source_path.name
    if destination.exists():
        destination.unlink()
    shutil.move(str(source_path), str(destination))
    return destination


def _scaled_text_timeout_s(pdf_path: Path) -> int:
    return 60


def _scaled_ocr_timeout_s(pdf_path: Path) -> int:
    size_bytes = pdf_path.stat().st_size if pdf_path.exists() else 0
    size_mb = max(1, math.ceil(size_bytes / (1024 * 1024)))
    return size_mb * 60


def _download_pdf_to_path(pdf_url: str, destination: Path) -> None:
    from scripts.http_session import get_session

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.part")
    response = get_session().get(pdf_url, stream=True, timeout=240)
    response.raise_for_status()
    try:
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def _extract_pages_for_reprocess(pdf_path: Path) -> tuple[list[str], int, str, bool]:
    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        pages, page_count = safe_ocr_pdf_text_pages(pdf_bytes, timeout_s=_scaled_ocr_timeout_s(pdf_path))
        return pages, page_count, "ocr", True
    try:
        pages, page_count = safe_extract_pdf_text_pages(pdf_path, timeout_s=_scaled_text_timeout_s(pdf_path))
        return pages, page_count, "text-layer", False
    except Exception as exc:
        if "NoTextLayerError" in type(exc).__name__ or "no extractable text layer" in str(exc).lower():
            pages, page_count = safe_ocr_pdf_text_pages(pdf_bytes, timeout_s=_scaled_ocr_timeout_s(pdf_path))
            return pages, page_count, "ocr", True
        raise


def _store_ocr_pages(
    *,
    database_url: str,
    ocr_page_table_name: str,
    document_pdf_id: str,
    source_name: str,
    source_uri: str | None,
    pages: list[str],
    page_kind: str,
    metadata: dict[str, Any] | None = None,
    ) -> int:
    statements = [
        build_ocr_page_upsert_sql(
            ocr_page_table_name,
            document_pdf_id=document_pdf_id,
            source_name=source_name,
            source_uri=source_uri,
            page_number=page_number,
            page_text=page_text,
            page_kind=page_kind,
            ocr_method="tesseract" if page_kind == "ocr" else "pypdf",
            status="loaded",
            metadata={"page_count": len(pages), **(metadata or {})},
        )
        for page_number, page_text in enumerate(pages, start=1)
    ]
    if statements:
        run_psql(database_url, "\n".join(statements))
    return len(statements)


def _load_local_pdf_path(source_uri: str | None, document_pdf_id: str, deferred_pdf_dir: Path) -> Path | None:
    # Disk is the source of truth. Only the deferred folder is the OCR worker input.
    candidate_names = [f"{document_pdf_id}.pdf"]
    if source_uri:
        candidate_names.append(Path(source_uri).name)
    for name in candidate_names:
        candidate = deferred_pdf_dir / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def _build_deferred_file_index(deferred_pdf_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not deferred_pdf_dir.exists():
        return index
    for path in deferred_pdf_dir.glob("*.pdf"):
        if path.is_file() and path.stat().st_size > 0:
            index[path.stem] = path
    return index


def _fetch_document_identity_map(database_url: str, document_pdf_ids: list[str]) -> dict[str, dict[str, str]]:
    if not document_pdf_ids:
        return {}
    placeholders = ", ".join([f"({sql_quote(document_pdf_id)})" for document_pdf_id in document_pdf_ids])
    sql = f"""
        WITH input_ids(document_pdf_id) AS (VALUES {placeholders})
        SELECT
            input_ids.document_pdf_id AS document_pdf_id,
            rag_document_identity.client_id AS client_id,
            rag_document_identity.patient_id AS patient_id,
            rag_document_identity.originalfilename AS originalfilename
        FROM input_ids
        LEFT JOIN rag_document_identity
            ON rag_document_identity.document_pdf_id = input_ids.document_pdf_id
    """.strip()
    rows: list[dict[str, Any]] = []
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    identity_map: dict[str, dict[str, str]] = {}
    for row in rows or []:
        document_pdf_id = str(row.get("document_pdf_id") or "").strip()
        if not document_pdf_id:
            continue
        identity_map[document_pdf_id] = {
            "client_id": str(row.get("client_id") or "").strip(),
            "patient_id": str(row.get("patient_id") or "").strip(),
            "originalfilename": str(row.get("originalfilename") or "").strip(),
        }
    return identity_map


def _fetch_missing_pdf(patient_id: str, document_pdf_id: str, filename: str, source_pdf_dir: Path) -> Path | None:
    try:
        data = fetch_medical_history_visits(patient_id, timeout=5)
    except Exception:
        return None
    charts = data.get("charts") if isinstance(data, dict) else None
    if not isinstance(charts, list):
        return None
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        chart_document_pdf_id = str(chart.get("id") or "").strip()
        if chart_document_pdf_id != document_pdf_id:
            continue
        destination = source_pdf_dir / f"{document_pdf_id}.pdf"
        if destination.is_file() and destination.stat().st_size > 0:
            return destination
        pdf_url = create_chart_file_url(document_pdf_id, inline=True)
        _download_pdf_to_path(pdf_url, destination)
        return destination
    return None


def _file_result_line(*, document_pdf_id: str, filename: str, status: str, detail: str | None = None) -> str:
    parts = [f"document_pdf_id={document_pdf_id}", f"file={filename!r}", f"status={status}"]
    if detail:
        parts.append(f"detail={detail!r}")
    return " | ".join(parts)


def _pdf_magic_check(pdf_path: Path) -> bool:
    try:
        with pdf_path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except Exception:
        return False


def _process_one_row(
    *,
    row: dict[str, Any],
    local_pdf_path: Path,
    args: argparse.Namespace,
    processed_pdf_dir: Path,
    term_index: Any,
    config: ChunkingConfig,
) -> tuple[bool, bool]:
    verbose_insight = os.environ.get("EVH_IMPORT_VERBOSE_PDF_INSIGHT", "").strip().lower() in {"1", "true", "yes", "on"}
    filename = str(row["filename"])
    parsed = _parse_deferred_filename(filename)
    document_pdf_id = str(row.get("document_pdf_id") or parsed["document_pdf_id"] or Path(filename).stem)
    identity = row.get("_identity") if isinstance(row, dict) else None
    client_id = str((identity or {}).get("client_id") or row.get("client_id") or parsed["client_id"] or "")
    patient_id = str((identity or {}).get("patient_id") or row.get("patient_id") or parsed["patient_id"] or "")
    patient_name = str(row.get("patient_name") or patient_id)
    canonical_filename = str((identity or {}).get("originalfilename") or filename)
    if client_id and not row.get("client_id"):
        row = dict(row)
        row["client_id"] = client_id
    if patient_id and not row.get("patient_id"):
        row = dict(row)
        row["patient_id"] = patient_id
    source = PatientPdfSource(
        patient_id=patient_id,
        patient_name=patient_name,
        document_pdf_id=document_pdf_id,
        pdf_path=local_pdf_path,
    )
    ocr_attempted = False
    print(
        f"working_on | document_pdf_id={document_pdf_id} | file={filename!r} | path={local_pdf_path} | "
        f"pdf_magic={'yes' if _pdf_magic_check(local_pdf_path) else 'no'}",
        flush=True,
    )
    if verbose_insight:
        print(
            f"document_insight_start | document_pdf_id={document_pdf_id} | filename={filename!r} | local_path={local_pdf_path}",
            flush=True,
        )
    print(_file_result_line(document_pdf_id=document_pdf_id, filename=filename, status="ocr_start"), flush=True)
    pages, page_count, page_kind, ocr_attempted = _extract_pages_for_reprocess(local_pdf_path)
    if verbose_insight:
        print(
            f"document_insight_extracted | document_pdf_id={document_pdf_id} | pages={page_count} | page_kind={page_kind} | ocr_attempted={ocr_attempted}",
            flush=True,
        )
    if ocr_attempted:
        print(_file_result_line(document_pdf_id=document_pdf_id, filename=filename, status="ocr_attempted", detail=page_kind), flush=True)
    print(f"chunk_start | document_pdf_id={document_pdf_id} | file={filename!r} | pages={page_count} | kind={page_kind}", flush=True)
    docs = chunk_pdf_pages(source, pages, config, term_index=term_index)
    if verbose_insight:
        print(
            f"document_insight_chunked | document_pdf_id={document_pdf_id} | docs={len(docs)} | pages={page_count}",
            flush=True,
        )
    print(f"chunk_done | document_pdf_id={document_pdf_id} | file={filename!r} | docs={len(docs)}", flush=True)
    print(f"db_load_start | document_pdf_id={document_pdf_id} | file={filename!r}", flush=True)
    load_into_postgres(
        database_url=args.database_url,
        table_name=args.table_name,
        source_document_table_name=args.source_document_table_name,
        source_name=row["source_name"],
        source_uri=str(local_pdf_path),
        documents=docs,
        embedding_model=args.embedding_model,
        vector_dimensions=args.vector_dimensions,
    )
    print(f"db_load_done | document_pdf_id={document_pdf_id} | file={filename!r}", flush=True)
    moved_to = _move_pdf_to_processed_dir(str(local_pdf_path), processed_pdf_dir)
    if moved_to is not None:
        print(f"move_done | document_pdf_id={document_pdf_id} | file={filename!r} | moved={moved_to.name}", flush=True)
    else:
        print(f"move_skipped | document_pdf_id={document_pdf_id} | file={filename!r}", flush=True)
    print(f"ocr_page_store_start | document_pdf_id={document_pdf_id} | file={filename!r}", flush=True)
    stored_pages = _store_ocr_pages(
        database_url=args.database_url,
        ocr_page_table_name=args.ocr_page_table_name,
        document_pdf_id=document_pdf_id,
        source_name=row["source_name"],
        source_uri=str(local_pdf_path),
        pages=pages,
        page_kind=page_kind,
        metadata={
            "client_id": client_id,
            "patient_id": patient_id,
            "filename": canonical_filename,
        },
    )
    print(f"ocr_page_store_done | document_pdf_id={document_pdf_id} | file={filename!r} | pages={stored_pages}", flush=True)
    print(f"status_update_start | document_pdf_id={document_pdf_id} | file={filename!r}", flush=True)
    run_psql(args.database_url, _update_status_sql(args.deferred_ocr_table_name, document_pdf_id, "loaded", "reprocessed"))
    print(f"status_update_done | document_pdf_id={document_pdf_id} | file={filename!r}", flush=True)
    detail = f"pages={page_count} stored={stored_pages} kind={page_kind}"
    if moved_to is not None:
        detail += f" moved={moved_to.name}"
    print(_file_result_line(document_pdf_id=document_pdf_id, filename=filename, status="loaded", detail=detail), flush=True)
    return True, ocr_attempted


def _process_one_row_worker(
    row: dict[str, Any],
    local_pdf_path: str,
    args: argparse.Namespace,
    processed_pdf_dir: str,
    term_index: Any,
    config: ChunkingConfig,
    queue,
) -> None:
    try:
        row = dict(row)
        print(
            f"worker_start | document_pdf_id={row.get('document_pdf_id')} | file={row.get('filename')!r}",
            flush=True,
        )
        did_complete, ocr_attempted = _process_one_row(
            row=row,
            local_pdf_path=Path(local_pdf_path),
            args=args,
            processed_pdf_dir=Path(processed_pdf_dir),
            term_index=term_index,
            config=config,
        )
        print(
            f"worker_done | document_pdf_id={row.get('document_pdf_id')} | file={row.get('filename')!r}",
            flush=True,
        )
        queue.put(("ok", {"did_complete": did_complete, "ocr_attempted": ocr_attempted}))
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # pragma: no cover - child process
        queue.put((
            "err",
            {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=20),
            },
        ))


def _run_row_in_worker_process(
    *,
    row: dict[str, Any],
    local_pdf_path: Path,
    args: argparse.Namespace,
    processed_pdf_dir: Path,
    term_index: Any,
    config: ChunkingConfig,
) -> dict[str, Any]:
    payload = {
        "batch_rows": [{"row": row, "local_pdf_path": str(local_pdf_path)}],
        "database_url": args.database_url,
        "table_name": args.table_name,
        "deferred_ocr_table_name": args.deferred_ocr_table_name,
        "source_document_table_name": args.source_document_table_name,
        "ocr_page_table_name": args.ocr_page_table_name,
        "embedding_model": args.embedding_model,
        "vector_dimensions": args.vector_dimensions,
        "processed_pdf_dir": str(processed_pdf_dir),
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "dictionary_csv": args.dictionary_csv,
    }
    worker_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker-job",
        json.dumps(payload),
    ]
    print(f"spawn_worker | document_pdf_id={row.get('document_pdf_id')} | file={row.get('filename')!r}", flush=True)
    try:
        proc = subprocess.run(
            worker_cmd,
            capture_output=True,
            text=True,
            timeout=max(120, _scaled_ocr_timeout_s(local_pdf_path) + 120),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "did_complete": False, "ocr_attempted": True, "error_type": "TimeoutError", "error": "worker timed out"}
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n", flush=True)
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", flush=True)
    result_line = None
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            result_line = line[len("RESULT "):]
    if result_line:
        try:
            return json.loads(result_line)
        except Exception as exc:
            return {"ok": False, "did_complete": False, "ocr_attempted": False, "error_type": type(exc).__name__, "error": str(exc)}
    if proc.returncode < 0:
        return {"ok": False, "did_complete": False, "ocr_attempted": True, "error_type": "SignalError", "error": f"worker exited by signal {-proc.returncode}"}
    if proc.returncode != 0:
        return {"ok": False, "did_complete": False, "ocr_attempted": True, "error_type": "RuntimeError", "error": f"worker exit code {proc.returncode}"}
    return {"ok": False, "did_complete": False, "ocr_attempted": False, "error_type": "WorkerLost", "error": "worker exited without RESULT line"}


def _run_batch_in_worker_process(
    *,
    worker_id: int,
    batch_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    processed_pdf_dir: Path,
    term_index: Any,
    config: ChunkingConfig,
) -> dict[str, Any]:
    if not batch_rows:
        return {"ok": True, "did_complete": False, "ocr_attempted": False, "error_type": None, "error": None, "results": []}
    first_row = batch_rows[0]
    payload = {
        "batch_rows": batch_rows,
        "database_url": args.database_url,
        "table_name": args.table_name,
        "deferred_ocr_table_name": args.deferred_ocr_table_name,
        "source_document_table_name": args.source_document_table_name,
        "ocr_page_table_name": args.ocr_page_table_name,
        "embedding_model": args.embedding_model,
        "vector_dimensions": args.vector_dimensions,
        "processed_pdf_dir": str(processed_pdf_dir),
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "dictionary_csv": args.dictionary_csv,
    }
    worker_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker-job",
        json.dumps(payload),
    ]
    print(
        f"spawn_worker | worker_id={worker_id} | batch_first_document_pdf_id={first_row['row'].get('document_pdf_id')} | batch_files={len(batch_rows)}",
        flush=True,
    )
    try:
        proc = subprocess.run(
            worker_cmd,
            capture_output=True,
            text=True,
            timeout=max(120, sum(_scaled_ocr_timeout_s(Path(item["local_pdf_path"])) for item in batch_rows) + 120),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error_type": "TimeoutError", "error": "batch worker timed out", "results": [], "worker_id": worker_id}
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n", flush=True)
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", flush=True)
    results: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            try:
                results.append(json.loads(line[len("RESULT "):]))
            except Exception:
                continue
    if proc.returncode < 0:
        return {"ok": False, "error_type": "SignalError", "error": f"batch worker exited by signal {-proc.returncode}", "results": results, "worker_id": worker_id}
    if proc.returncode != 0 and not results:
        return {"ok": False, "error_type": "RuntimeError", "error": f"batch worker exit code {proc.returncode}", "results": results, "worker_id": worker_id}
    return {"ok": True, "error_type": None, "error": None, "results": results, "worker_id": worker_id}


def _run_row_with_retry_and_monitoring(
    *,
    row: dict[str, Any],
    local_pdf_path: Path,
    args: argparse.Namespace,
    processed_pdf_dir: Path,
    term_index: Any,
    config: ChunkingConfig,
    max_retries: int = 1,
    heartbeat_timeout_s: int = 45,
) -> dict[str, Any]:
    document_pdf_id = str(row["document_pdf_id"])
    for attempt in range(max_retries + 1):
        worker_result = _run_row_in_worker_process(
            row=row,
            local_pdf_path=local_pdf_path,
            args=args,
            processed_pdf_dir=processed_pdf_dir,
            term_index=term_index,
            config=config,
        )

        if bool(worker_result.get("ok")) or attempt >= max_retries or not _should_retry_worker_result(worker_result):
            return worker_result

        print(
            f"worker_respawn | document_pdf_id={document_pdf_id} | file={row['filename']!r} | retry={attempt + 1} | error_type={worker_result.get('error_type')}",
            flush=True,
        )

    return worker_result or {
        "did_complete": False,
        "ocr_attempted": False,
        "ok": False,
        "error_type": "RuntimeError",
        "error": "worker monitoring failed",
    }


class _Tee:
    def __init__(self, *streams: Any) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        total = 0
        for stream in self._streams:
            total = stream.write(data)
            stream.flush()
        return total

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reprocess deferred OCR PDFs.")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--deferred-ocr-table-name", default=DEFAULT_DEFERRED_OCR_TABLE_NAME)
    parser.add_argument("--table-name", default=DEFAULT_TABLE_NAME)
    parser.add_argument("--source-document-table-name", default=DEFAULT_SOURCE_DOCUMENT_TABLE_NAME)
    parser.add_argument("--ocr-page-table-name", default=DEFAULT_OCR_PAGE_TABLE_NAME)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--vector-dimensions", type=int, default=DEFAULT_EMBEDDING_DIMENSIONS)
    parser.add_argument("--dictionary-csv", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--pass-mode",
        choices=("text-first", "ocr-only", "all"),
        default="text-first",
        help="Process text-layer PDFs first, OCR-only PDFs second, or restrict to one pass.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Reprocess deferred PDFs marked as text-layer pending instead of the default pending queue.",
    )
    parser.add_argument(
        "--text-first",
        action="store_true",
        help="Process ocr_needed rows first, then regular pending rows, with randomized order inside each bucket.",
    )
    parser.add_argument(
        "--only-pdf-id",
        default="",
        help="Restrict the run to a single deferred PDF id for debugging.",
    )
    parser.add_argument(
        "--deferred-pdf-dir",
        default=str(DATA_ROOT / "instinct-pdfs-deferred"),
        help="Read deferred/unprocessed PDFs from here for OCR reprocessing.",
    )
    parser.add_argument(
        "--processed-pdf-dir",
        default=str(DATA_ROOT / "instinct-pdfs-processed"),
        help="Move successfully reprocessed PDFs here after OCR/vector load completes.",
    )
    parser.add_argument(
        "--log-file",
        default="/tmp/evh_deferred_ocr.out",
        help="Mirror stdout/stderr to this log file while still showing output in the terminal.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of files to process concurrently.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of files per consecutive batch.",
    )
    parser.add_argument(
        "--verbose-document-logging",
        action="store_true",
        help="Enable per-document and per-page insight logs inside the PDF tools.",
    )
    parser.add_argument(
        "--worker-job",
        default="",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.worker_job:
        payload = json.loads(args.worker_job)
        raise SystemExit(_worker_job_from_payload(payload))

    if args.verbose_document_logging:
        os.environ["EVH_IMPORT_VERBOSE_PDF_INSIGHT"] = "1"

    if not args.database_url:
        args.database_url = _build_db_url()

    log_path = Path(args.log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = _Tee(sys.stdout, log_handle)  # type: ignore[assignment]
    sys.stderr = _Tee(sys.stderr, log_handle)  # type: ignore[assignment]
    print(f"[log_file] {log_path}", flush=True)

    term_index = load_term_index(Path(args.dictionary_csv) if args.dictionary_csv else None)
    config = ChunkingConfig(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    deferred_pdf_dir = Path(args.deferred_pdf_dir).expanduser()
    processed_pdf_dir = Path(args.processed_pdf_dir).expanduser()
    deferred_pdf_dir.mkdir(parents=True, exist_ok=True)
    processed_pdf_dir.mkdir(parents=True, exist_ok=True)
    run_psql(args.database_url, build_ocr_page_schema_sql(args.ocr_page_table_name))

    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if args.text_first:
                cur.execute(
                    f"""
                    SELECT source_name, source_uri, patient_name, document_pdf_id, page_count, reason, status, metadata, disk_filename
                    FROM {args.deferred_ocr_table_name}
                    WHERE status = %s
                    """
                    ,
                    ("ocr_needed",),
                )
                text_rows = cur.fetchall()
                cur.execute(
                    f"""
                    SELECT source_name, source_uri, patient_name, document_pdf_id, page_count, reason, status, metadata, disk_filename
                    FROM {args.deferred_ocr_table_name}
                    WHERE status = %s
                    """
                    ,
                    ("pending",),
                )
                regular_rows = cur.fetchall()
                random.shuffle(text_rows)
                random.shuffle(regular_rows)
                rows = text_rows + regular_rows
            else:
                pending_status = "ocr_needed" if args.text else "pending"
                cur.execute(
                    f"""
                    SELECT source_name, source_uri, patient_name, document_pdf_id, page_count, reason, status, metadata, disk_filename
                    FROM {args.deferred_ocr_table_name}
                    WHERE status = %s
                    """
                    , (pending_status,))
                rows = cur.fetchall()

    if args.only_document_pdf_id:
        rows = [row for row in rows if str(row.get("document_pdf_id") or "") == args.only_document_pdf_id]

    deferred_file_index = _build_deferred_file_index(deferred_pdf_dir)
    local_rows: list[dict[str, Any]] = []
    rows_by_document_pdf_id = {str(row.get("document_pdf_id") or ""): row for row in rows}
    identity_map = _fetch_document_identity_map(args.database_url, list(rows_by_document_pdf_id.keys()))
    local_rows = []
    if args.text_first:
        for row in rows:
            document_pdf_id = str(row.get("document_pdf_id") or "")
            pdf_path = deferred_file_index.get(document_pdf_id)
            if pdf_path is None:
                continue
            parsed = _parse_deferred_filename(pdf_path.name)
            row = dict(row)
            row["filename"] = row.get("disk_filename") or pdf_path.name
            if parsed["original_filename"] and not row["filename"]:
                row["filename"] = parsed["original_filename"]
            row["_identity"] = identity_map.get(document_pdf_id, {})
            local_rows.append(row)
    else:
        sortable_rows: list[tuple[int, str, dict[str, Any]]] = []
        for document_pdf_id, pdf_path in sorted(deferred_file_index.items()):
            row = rows_by_document_pdf_id.get(document_pdf_id)
            if row is not None:
                parsed = _parse_deferred_filename(pdf_path.name)
                row = dict(row)
                row["filename"] = row.get("disk_filename") or pdf_path.name
                if parsed["original_filename"] and not row["filename"]:
                    row = dict(row)
                    row["filename"] = parsed["original_filename"]
                row["_identity"] = identity_map.get(document_pdf_id, {})
                sortable_rows.append((pdf_path.stat().st_size, document_pdf_id, row))
        sortable_rows.sort(key=lambda item: (item[0], item[1]))
        local_rows = [row for _size, _document_pdf_id, row in sortable_rows]
    if args.limit:
        local_rows = local_rows[: args.limit]

    print(
        f"start | pending={len(rows)} | local_files={len(deferred_file_index)} | "
        f"local_rows={len(local_rows)}",
        flush=True,
    )
    run_started_at = time.monotonic()
    total_to_process = len(local_rows)
    ocred_count = 0
    ocr_not_reached_deferred_count = 0
    text_layer_count = 0
    ocr_only_count = 0
    batch_size = max(1, int(args.batch_size or 10))
    print(f"worker_plan_start | batch_size={batch_size} | total_rows={len(local_rows)}", flush=True)
    batches = _chunked(local_rows, batch_size)
    print(f"worker_plan_ready | batches={len(batches)}", flush=True)
    max_workers = max(1, int(args.workers or 1))
    print(f"worker_pool_start | workers={max_workers} | batches={len(batches)}", flush=True)
    batch_payloads: list[tuple[int, list[dict[str, Any]]]] = []
    for batch_index, batch in enumerate(batches, start=1):
        print(f"batch_start | batch_index={batch_index} | batch_files={len(batch)}", flush=True)
        batch_rows: list[dict[str, Any]] = []
        for row in batch:
            document_pdf_id = str(row["document_pdf_id"])
            local_pdf_path = deferred_file_index.get(document_pdf_id)
            if local_pdf_path is None:
                print(f"row_skip_missing | batch_index={batch_index} | document_pdf_id={document_pdf_id} | file={row.get('filename')!r}", flush=True)
                continue
            print(
                f"worker_dispatch | batch_index={batch_index} | document_pdf_id={document_pdf_id} | file={row.get('filename')!r} | path={local_pdf_path}",
                flush=True,
            )
            batch_rows.append({"row": row, "local_pdf_path": str(local_pdf_path)})
        if batch_rows:
            batch_payloads.append((batch_index, batch_rows))
        else:
            print(f"batch_empty | batch_index={batch_index}", flush=True)

    def _run_one_batch(worker_id: int, batch_index: int, batch_rows: list[dict[str, Any]]) -> tuple[int, int, dict[str, Any]]:
        return worker_id, batch_index, _run_batch_in_worker_process(
            worker_id=worker_id,
            batch_rows=batch_rows,
            args=args,
            processed_pdf_dir=processed_pdf_dir,
            term_index=term_index,
            config=config,
        )

    def _mark_failed_safely(
        *,
        document_pdf_id: str,
        filename: str,
        note: str,
        worker_id: int,
        batch_index: int,
    ) -> None:
        try:
            run_psql(
                args.database_url,
                _update_status_sql(
                    args.deferred_ocr_table_name,
                    document_pdf_id,
                    "ocr_not_reached_deferred",
                    note,
                ),
            )
        except Exception as exc:
            print(
                f"status_update_failed | worker_id={worker_id} | batch_index={batch_index} | document_pdf_id={document_pdf_id} | file={filename!r} | error_type={type(exc).__name__} | error={exc}",
                flush=True,
            )

    with cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_run_one_batch, ((idx - 1) % max_workers) + 1, batch_index, batch_rows): (batch_index, ((idx - 1) % max_workers) + 1)
            for idx, (batch_index, batch_rows) in enumerate(batch_payloads, start=1)
        }
        for future in cf.as_completed(future_map):
            batch_index, worker_id = future_map[future]
            try:
                worker_id, batch_index, worker_result = future.result()
            except Exception as exc:
                print(
                    f"batch_future_failed | worker_id={worker_id} | batch_index={batch_index} | error_type={type(exc).__name__} | error={exc}",
                    flush=True,
                )
                ocr_not_reached_deferred_count += len(batch_payloads[batch_index - 1][1]) if 0 <= batch_index - 1 < len(batch_payloads) else 0
                continue
            results = worker_result.get("results") or []
            for item in results:
                document_pdf_id = str(item.get("document_pdf_id") or "")
                filename = str(item.get("filename") or "")
                status = str(item.get("status") or "")
                ok = bool(item.get("ok"))
                if ok and status == "loaded":
                    ocred_count += 1
                if not ok:
                    ocr_not_reached_deferred_count += 1
                    note = f"{item.get('error_type')}: {item.get('error')}"
                    print(f"failure_trace | document_pdf_id={document_pdf_id} | file={filename!r} | {note}", flush=True)
                    _mark_failed_safely(
                        document_pdf_id=document_pdf_id,
                        filename=filename,
                        note=note,
                        worker_id=worker_id,
                        batch_index=batch_index,
                    )
                    print(_file_result_line(document_pdf_id=document_pdf_id, filename=filename, status="ocr_not_reached_deferred", detail=str(item.get("error_type"))), flush=True)
                print(
                    f"worker_result | worker_id={worker_id} | batch_index={batch_index} | document_pdf_id={document_pdf_id} | ok={ok} | status={status} | error_type={item.get('error_type')}",
                    flush=True,
                )
                print(
                    f"count_update_done | worker_id={worker_id} | batch_index={batch_index} | document_pdf_id={document_pdf_id} | processed={ocred_count} | failed={ocr_not_reached_deferred_count}",
                    flush=True,
                )
                print(
                    f"progress_about_to_print | worker_id={worker_id} | batch_index={batch_index} | document_pdf_id={document_pdf_id} | processed={ocred_count} | failed={ocr_not_reached_deferred_count}",
                    flush=True,
                )
                _print_progress(
                    run_started_at=run_started_at,
                    ocred_count=ocred_count,
                    ocr_not_reached_deferred_count=ocr_not_reached_deferred_count,
                    total_to_process=total_to_process,
                )
                print(
                    f"progress_printed | worker_id={worker_id} | batch_index={batch_index} | document_pdf_id={document_pdf_id} | processed={ocred_count} | failed={ocr_not_reached_deferred_count}",
                    flush=True,
                )

    elapsed_s = time.monotonic() - run_started_at
    attempted = ocred_count + ocr_not_reached_deferred_count
    avg_s = elapsed_s / attempted if attempted else 0.0
    remaining = max(0, len(local_rows) - attempted)
    velocity = ocred_count / elapsed_s if elapsed_s > 0 else 0.0
    eta_s = remaining / velocity if velocity > 0 else 0.0
    print(
        f"done | processed={ocred_count} | failed={ocr_not_reached_deferred_count} | "
        f"text_layer_seen={text_layer_count} | ocr_seen={ocr_only_count} | "
        f"attempted={attempted} | remaining={remaining} | elapsed_s={elapsed_s:.1f} | "
        f"avg_s_per_file={avg_s:.1f} | velocity_fps={velocity:.4f} | eta={_format_seconds(eta_s)}",
        flush=True,
    )
    sys.stdout = original_stdout  # type: ignore[assignment]
    sys.stderr = original_stderr  # type: ignore[assignment]
    log_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
