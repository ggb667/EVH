"""Instinct RAG importer 2.0.

Clean file-only pipeline:
- inspect source locally if needed
- Word branch: extract text, if usable load; else skip-word-text-not-found
- PDF branch: run text methods in parallel, choose best usable result
- If text stage fails, run OCR methods in order and take first usable result
- On DONE, update checkpoint last
"""

from __future__ import annotations

import argparse
import json
import hashlib
import sys
import shutil
import subprocess
import tempfile
import os
import time
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

import requests

# Ensure direct worktree execution can import repo-local scripts.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pymupdf
from pypdf import PdfReader

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_batch_walk import iter_clients_from_index
from scripts.instinct_pdf_chunker import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    PatientPdfSource,
    build_deferred_ocr_schema_sql,
    build_deferred_ocr_content_hash_lookup_sql,
    build_deferred_ocr_upsert_sql,
    build_source_document_upsert_sql,
    _extract_word_text_pages,
    sql_quote,
    set_sql_verbose_logging,
    run_psql,
)
from scripts.instinct_pdf_family_sampler import create_chart_file_url, fetch_medical_history_visits


MIN_USABLE_CHARS = 100
TEXT_TIMEOUT_S = 70
OCR_TIMEOUT_S = 600
DOWNLOAD_FAILURE_STREAK_KIND: str | None = None
DOWNLOAD_FAILURE_STREAK_COUNT = 0

TABLE_STATUSES = [
    "word_winner",
    "text_winner",
    "ocr_winner",
    "skipped_word_text_not_found",
    "deferred",
]

METHOD_COUNTER_NAMES = [
    "pdftotext",
    "pypdf",
    "pymupdf",
    "pdftoppm",
    "pdftocairo",
    "gs",
    "tesseract",
]

SOURCE_DOCUMENT_TABLE_NAME = "rag_source_document"
DEFERRED_OCR_TABLE_NAME = "rag_deferred_ocr_document"
CHUNK_TABLE_NAME = "pms_page_chunk"
RUN_TOTAL_CLIENTS = 0
RUN_LAST_EVENT_AT: float | None = None
RUN_LOG_PATH: Path | None = None
RUN_LOG_FILE = None
RUN_DEFERRED_LOADED_CACHE: dict[str, int | None] | None = None


@dataclass(frozen=True)
class StageResult:
    pages: list[str]
    page_count: int
    method: str
    elapsed_seconds: float
    usable: bool
    detail: str = ""


@dataclass(frozen=True)
class ChartWorkItem:
    client_id: str
    client_name: str
    patient_id: str
    patient_name: str
    chart_id: str
    filename: str
    pdf_path: Path
    client_index: int
    patient_index: int
    chart_index: int


def _new_counters() -> dict[str, int]:
    counters = {
        "completed": 0,
        "loaded": 0,
        "deferred": 0,
        "skipped": 0,
        "skipped_word_text_not_found": 0,
        "word_winner": 0,
        "text_winner": 0,
        "ocr_winner": 0,
        "word": 0,
        "unrecognized_file": 0,
        "could_not_ocr": 0,
    }
    for name in METHOD_COUNTER_NAMES:
        counters[name] = 0
    return counters


def _count_method_win(counters: dict[str, int], method: str | None) -> None:
    if not method:
        return
    base = method.split(":", 1)[0]
    if base == "word":
        counters["word"] += 1
    elif base in counters:
        counters[base] += 1


def _count_rollup(counters: dict[str, int]) -> str:
    ordered = [
        ("skipped", counters.get("skipped", 0)),
        ("completed", counters.get("completed", 0)),
        ("loaded", counters.get("loaded", 0)),
        ("deferred", counters.get("deferred", 0)),
        ("completed", counters.get("completed", 0)),
    ]
    return " ".join(f"{name}: {count}" for name, count in ordered)


def _safe_pdf_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.exists() else 0
    except OSError:
        return 0


def _build_run_log_path(start_client_index: int, limit_pdfs: int, log_dir: Path | None = None) -> Path:
    base_dir = log_dir or Path("/tmp")
    base_dir.mkdir(parents=True, exist_ok=True)
    limit_part = str(limit_pdfs) if limit_pdfs > 0 else "all"
    return base_dir / f"evh_instinct_import_2_0.start_{start_client_index}.limit_{limit_part}.out"


class _TeeStream:
    def __init__(self, console_stream, log_file):
        self._console = console_stream
        self._log = log_file

    def write(self, data):
        self._console.write(data)
        self._log.write(data)
        return len(data)

    def flush(self):
        self._console.flush()
        self._log.flush()

    def isatty(self):
        return self._console.isatty()


def _redirect_stdio_to_log(log_path: Path) -> None:
    global RUN_LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG_FILE = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = _TeeStream(sys.__stdout__, RUN_LOG_FILE)
    sys.stderr = _TeeStream(sys.__stderr__, RUN_LOG_FILE)
    print(f"logging to {log_path}", flush=True)


def _fetch_processed_content_length(
    database_url: str,
    source_document_table_name: str,
    pdf_id: str,
) -> int | None:
    quoted_pdf_id = sql_quote(str(pdf_id))
    sql = f"""
SELECT content_length
FROM {source_document_table_name}
WHERE metadata->>'pdf_id' = {quoted_pdf_id}
  AND status = 'loaded'
ORDER BY processed_at DESC
LIMIT 1;
""".strip()
    result = run_psql(database_url, sql)
    text = result.stdout.strip()
    if not text:
        return None
    try:
        return int(text.splitlines()[-1].strip())
    except ValueError:
        return None


def _fetch_deferred_row(
    database_url: str,
    deferred_table_name: str,
    document_pdf_id: str,
) -> dict[str, str] | None:
    quoted_pdf_id = sql_quote(str(document_pdf_id))
    sql = f"""
SELECT document_pdf_id, status, content_hash, content_length
FROM {deferred_table_name}
WHERE document_pdf_id = {quoted_pdf_id}
LIMIT 1;
""".strip()
    result = run_psql(database_url, sql)
    text = result.stdout.strip()
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    # psql -At style output: doc_id|status|hash|len
    parts = lines[-1].split("|")
    if len(parts) < 4:
        return None
    return {
        "document_pdf_id": parts[0],
        "status": parts[1],
        "content_hash": parts[2],
        "content_length": parts[3],
    }


def _load_deferred_loaded_cache(database_url: str) -> dict[str, int | None]:
    sql = f"""
SELECT document_pdf_id, content_length
FROM {DEFERRED_OCR_TABLE_NAME}
WHERE status = 'loaded';
""".strip()
    result = run_psql(database_url, sql)
    text = result.stdout.strip()
    cache: dict[str, int | None] = {}
    if not text:
        return cache
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if not parts or not parts[0]:
            continue
        content_length: int | None = None
        if len(parts) > 1 and parts[1]:
            try:
                content_length = int(parts[1])
            except ValueError:
                content_length = None
        cache[parts[0]] = content_length
    return cache


def _download_failure_kind(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, FileNotFoundError):
        return "missing_url_or_missing_file"
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None:
            return f"http_{status}"
        return "http_error"
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.RequestException):
        return "request_exception"
    if "bad request" in text:
        return "http_400"
    return type(exc).__name__


def _milestone_pdf_size(pdf_path: Path) -> int | None:
    size = _safe_pdf_size(pdf_path)
    return size if size > 0 else None


def _resolve_client_name(account: dict[str, object], client_id: str) -> str | None:
    for key in ("name", "displayName", "businessName", "legalName", "fullName"):
        value = str(account.get(key) or "").strip()
        if not value:
            continue
        if value == client_id:
            continue
        if len(value) == 36 and value.count("-") == 4:
            continue
        return value
    return None


def _emit_milestone(status: str, **fields: object) -> None:
    global RUN_LAST_EVENT_AT
    now = perf_counter()
    payload: dict[str, object] = {}
    if "client_index" in fields:
        payload["client_index"] = fields.pop("client_index")
    payload["status"] = status
    payload.update(fields)
    payload["since_prev_seconds"] = None if RUN_LAST_EVENT_AT is None else round(now - RUN_LAST_EVENT_AT, 3)
    RUN_LAST_EVENT_AT = now
    print(json.dumps(payload), flush=True)


def _resolve_pdf_path(
    *,
    storage_path: Path,
    processed_dir: Path,
    pdf_url: str | None,
    database_url: str,
    chart_id: str,
    filename: str,
) -> tuple[Path, bool, bool]:
    """Return the usable local path, whether it should land in processed, and whether it was skipped."""
    global DOWNLOAD_FAILURE_STREAK_KIND, DOWNLOAD_FAILURE_STREAK_COUNT, RUN_DEFERRED_LOADED_CACHE
    deferred_row = None
    if RUN_DEFERRED_LOADED_CACHE is not None:
        deferred_content_length = RUN_DEFERRED_LOADED_CACHE.get(chart_id)
        if deferred_content_length is not None:
            deferred_row = {"content_length": str(deferred_content_length)}
    else:
        deferred_row = _fetch_deferred_row(database_url, DEFERRED_OCR_TABLE_NAME, chart_id)
    storage_exists = storage_path.exists() and _safe_pdf_size(storage_path) > 0
    processed_path = processed_dir / storage_path.name
    processed_exists = processed_path.exists() and _safe_pdf_size(processed_path) > 0
    if deferred_row is not None and (storage_exists or processed_exists):
        DOWNLOAD_FAILURE_STREAK_KIND = None
        DOWNLOAD_FAILURE_STREAK_COUNT = 0
        print("already downloaded, pdf matches table, already loaded, skipping", flush=True)
        return processed_path if processed_exists else storage_path, True, True
    destination = storage_path
    if not pdf_url:
        raise FileNotFoundError(f"missing PDF and no download URL for {filename}")
    if DOWNLOAD_FAILURE_STREAK_COUNT > 0 and DOWNLOAD_FAILURE_STREAK_KIND == "missing_url_or_missing_file":
        raise FileNotFoundError(f"repeat download failure already seen for {filename}")
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            _download_pdf_to_path(pdf_url, destination)
            if _safe_pdf_size(destination) <= 0:
                raise FileNotFoundError(f"downloaded PDF is still missing or empty: {destination}")
            if RUN_DEFERRED_LOADED_CACHE is not None and chart_id in RUN_DEFERRED_LOADED_CACHE:
                DOWNLOAD_FAILURE_STREAK_KIND = None
                DOWNLOAD_FAILURE_STREAK_COUNT = 0
                return destination, True, True
            if RUN_DEFERRED_LOADED_CACHE is None and _fetch_deferred_row(database_url, DEFERRED_OCR_TABLE_NAME, chart_id) is not None:
                DOWNLOAD_FAILURE_STREAK_KIND = None
                DOWNLOAD_FAILURE_STREAK_COUNT = 0
                return destination, True, True
            DOWNLOAD_FAILURE_STREAK_KIND = None
            DOWNLOAD_FAILURE_STREAK_COUNT = 0
            return destination, False, False
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(5)
    if last_exc is not None:
        DOWNLOAD_FAILURE_STREAK_KIND = _download_failure_kind(last_exc)
        DOWNLOAD_FAILURE_STREAK_COUNT += 1
        raise last_exc


def _write_checkpoint(checkpoint_path: Path | None, payload: dict[str, object]) -> None:
    if checkpoint_path is None:
        return
    checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_checkpoint(checkpoint_path: Path | None) -> dict[str, object]:
    if checkpoint_path is None or not checkpoint_path.exists():
        return {}
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resume_after_item(item: ChartWorkItem, *, resume_client_index: int, resume_patient_index: int, resume_chart_index: int) -> bool:
    if item.client_index < resume_client_index:
        return False
    if item.client_index > resume_client_index:
        return True
    if item.patient_index < resume_patient_index:
        return False
    if item.patient_index > resume_patient_index:
        return True
    return item.chart_index > resume_chart_index


def _parse_client_id_value(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _write_source_document_row(
    *,
    database_url: str | None,
    source_name: str,
    source_uri: str | None,
    content_hash: str,
    content_length: int,
    page_count: int,
    chunk_count: int,
    summary: str,
    metadata: dict[str, object],
    ) -> None:
    if not database_url:
        return
    run_psql(
        database_url,
        build_source_document_upsert_sql(
            SOURCE_DOCUMENT_TABLE_NAME,
            source_name=source_name,
            source_uri=source_uri,
            content_hash=content_hash,
            content_length=content_length,
            page_count=page_count,
            chunk_count=chunk_count,
            summary=summary,
            metadata=metadata,
        ),
    )


def _write_deferred_row(
    *,
    database_url: str | None,
    source_name: str,
    source_uri: str | None,
    client_id: str | None,
    patient_id: str | None,
    patient_name: str | None,
    pdf_id: str,
    filename: str,
    page_count: int | None,
    reason: str,
    metadata: dict[str, object],
) -> None:
    if not database_url:
        return
    run_psql(database_url, build_deferred_ocr_schema_sql(DEFERRED_OCR_TABLE_NAME))
    run_psql(
        database_url,
        build_deferred_ocr_upsert_sql(
            DEFERRED_OCR_TABLE_NAME,
            source_name=source_name,
            source_uri=source_uri,
            patient_id=patient_id,
            patient_name=patient_name,
            pdf_id=pdf_id,
            filename=filename,
            page_count=page_count,
            reason=reason,
            metadata=metadata,
        ),
    )
    if client_id and patient_id and pdf_id and filename:
        _write_document_identity_row(
            database_url=database_url,
            client_id=client_id,
            patient_id=patient_id,
            pdf_id=pdf_id,
            originalfilename=filename,
        )


def _write_document_identity_row(*, database_url: str | None, client_id: str | None, patient_id: str | None, pdf_id: str, originalfilename: str) -> None:
    if not database_url or not client_id or not patient_id or not pdf_id or not originalfilename:
        return
    run_psql(
        database_url,
        f"""
        INSERT INTO rag_document_identity (document_pdf_id, client_id, patient_id, originalfilename)
        VALUES ({sql_quote(pdf_id)}, {sql_quote(client_id)}, {sql_quote(patient_id)}, {sql_quote(originalfilename)})
        ON CONFLICT (document_pdf_id) DO UPDATE SET
            client_id = EXCLUDED.client_id,
            patient_id = EXCLUDED.patient_id,
            originalfilename = EXCLUDED.originalfilename;
        """.strip(),
    )


def _ingest_document(
    *,
    pdf_path: Path,
    source_name: str,
    source_uri: str | None,
    database_url: str | None,
    counters: dict[str, int],
) -> tuple[int, dict[str, float], str, int]:
    source = PatientPdfSource(patient_id="unknown", patient_name=source_name, pdf_path=pdf_path, pdf_url=source_uri)
    pages, extraction_meta = _extract_pdf_pages_local(pdf_path)
    page_count = int(extraction_meta.get("page_count") or len(pages))
    chunk_docs = _chunk_documents_from_pages(
        source_name=source_name,
        patient_id="unknown",
        patient_name=source_name,
        pages=pages,
    )
    summary = f"ingested {len(chunk_docs)} chunks"
    timing = {
        "text_method": extraction_meta.get("method"),
        "ocr_used": bool(extraction_meta.get("method") and str(extraction_meta.get("method")).startswith(("pdftoppm", "pdftocairo", "gs"))),
    }
    if database_url:
        content_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        metadata = {
            "source_name": source_name,
            "winner_method": None,
            "counters": counters,
            "timing": timing,
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "vector_dimensions": DEFAULT_EMBEDDING_DIMENSIONS,
        }
        _write_source_document_row(
            database_url=database_url,
            source_name=source_name,
            source_uri=source_uri,
            content_hash=content_hash,
            content_length=pdf_path.stat().st_size,
            page_count=page_count,
            chunk_count=len(chunk_docs),
            summary=summary,
            metadata=metadata,
        )
    return len(chunk_docs), timing, summary, page_count


def _finalize_document(
    *,
    pdf_path: Path,
    source_name: str,
    source_uri: str | None,
    database_url: str | None,
    status: str,
    winner_method: str | None,
    reason: str | None,
    page_count: int,
    candidates: list[StageResult] | None,
    counters: dict[str, int],
    checkpoint_path: Path | None,
    deferred_dir: Path | None,
    processed_dir: Path | None,
) -> int:
    _count_method_win(counters, winner_method)
    if status == "skipped_word_text_not_found":
        counters["skipped_word_text_not_found"] += 1
        counters["unrecognized_file"] += 1
    if status == "deferred" and reason == "could_not_extract":
        pass
    if status != "skipped":
        counters["completed"] += 1
    if status == "loaded":
        counters["loaded"] += 1
    if status == "deferred":
        counters[status] += 1

    payload: dict[str, object] = {
        "status": status,
        "winner_method": winner_method,
        "reason": reason,
        "page_count": page_count,
        "source_name": source_name,
        "file": str(pdf_path),
        "counts": _count_rollup(counters),
        "table_statuses": TABLE_STATUSES,
    }
    if candidates is not None:
        payload["candidates"] = [
            {
                "method": candidate.method,
                "usable": candidate.usable,
                "chars": sum(len(page.strip()) for page in candidate.pages),
                "elapsed_seconds": round(candidate.elapsed_seconds, 3),
            }
            for candidate in candidates
        ]
    ingest_result = None
    if status in {"word_winner", "text_winner", "ocr_winner"}:
        ingest_result = _ingest_document(
            pdf_path=pdf_path,
            source_name=source_name,
            source_uri=source_uri,
            database_url=database_url,
            counters=counters,
        )
        payload["ingest"] = {
            "chunk_count": ingest_result[0],
            "page_count": ingest_result[3],
            "summary": ingest_result[2],
        }
    print(json.dumps(payload, sort_keys=True))
    _write_checkpoint(
        checkpoint_path,
        {
            "status": status,
            "winner_method": winner_method,
            "reason": reason,
            "page_count": page_count,
            "source_name": source_name,
            "file": str(pdf_path),
            "counts": _count_rollup(counters),
            "table_statuses": TABLE_STATUSES,
        },
    )
    if status in {"word_winner", "text_winner", "ocr_winner"} and processed_dir is not None:
        processed_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdf_path), str(processed_dir / pdf_path.name))
    elif status == "deferred" and deferred_dir is not None:
        counters["deferred"] += 1
        deferred_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdf_path), str(deferred_dir / pdf_path.name))
    return 0 if status in {"word_winner", "text_winner", "ocr_winner"} else 1


def _usable_text(pages: list[str], *, min_chars: int = MIN_USABLE_CHARS) -> bool:
    return sum(len(page.strip()) for page in pages) >= min_chars


def _normalize_pages(pages: list[str]) -> list[str]:
    return [page.strip() for page in pages]


def _text_result(pages: list[str], page_count: int, method: str, elapsed_seconds: float, detail: str = "") -> StageResult:
    pages = _normalize_pages(pages)
    return StageResult(
        pages=pages,
        page_count=page_count,
        method=method,
        elapsed_seconds=elapsed_seconds,
        usable=_usable_text(pages),
        detail=detail,
    )


def _word_stage(pdf_path: Path) -> StageResult:
    source = PatientPdfSource(patient_id="unknown", patient_name=pdf_path.name, pdf_path=pdf_path, pdf_url=None)
    start = perf_counter()
    pages, page_count, method = _extract_word_text_pages(source)
    return _text_result(pages, page_count, f"word:{method}", perf_counter() - start, detail="word")


def _pdftotext_stage(pdf_path: Path) -> StageResult:
    start = perf_counter()
    cmd = shutil.which("pdftotext")
    if not cmd:
        return StageResult([], 0, "pdftotext", 0.0, False, "pdftotext unavailable")
    with tempfile.TemporaryDirectory(prefix="rag20-pdftotext-") as td:
        temp_dir = Path(td)
        out_path = temp_dir / "out.txt"
        proc = subprocess.run(
            [cmd, "-layout", str(pdf_path), str(out_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=TEXT_TIMEOUT_S,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[-1000:]
            return StageResult([], 0, "pdftotext", perf_counter() - start, False, err or f"returncode={proc.returncode}")
        text = out_path.read_text(encoding="utf-8", errors="replace")
        pages = text.split("\f")
        return _text_result(pages, len(pages), "pdftotext", perf_counter() - start)


def _pypdf_stage(pdf_path: Path) -> StageResult:
    start = perf_counter()
    try:
        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        for page in reader.pages:
            try:
                text = page.extract_text(extraction_mode="layout")
            except Exception:
                text = page.extract_text()
            pages.append(text or "")
        return _text_result(pages, len(pages), "pypdf", perf_counter() - start)
    except Exception as exc:
        return StageResult([], 0, "pypdf", perf_counter() - start, False, f"{type(exc).__name__}: {exc}")


def _pymupdf_stage(pdf_path: Path) -> StageResult:
    start = perf_counter()
    try:
        doc = pymupdf.open(str(pdf_path))
        pages = [(page.get_text() or "") for page in doc]
        return _text_result(pages, len(pages), "pymupdf", perf_counter() - start)
    except Exception as exc:
        return StageResult([], 0, "pymupdf", perf_counter() - start, False, f"{type(exc).__name__}: {exc}")


def _best_text_result(results: list[StageResult]) -> StageResult | None:
    usable = [r for r in results if r.usable]
    if not usable:
        return None
    best = usable[0]
    best_chars = sum(len(page.strip()) for page in best.pages)
    for candidate in usable[1:]:
        candidate_chars = sum(len(page.strip()) for page in candidate.pages)
        if candidate_chars > best_chars:
            best = candidate
            best_chars = candidate_chars
        elif candidate_chars == best_chars and candidate.elapsed_seconds < best.elapsed_seconds:
            best = candidate
            best_chars = candidate_chars
    return best


def _text_stage(pdf_path: Path) -> tuple[StageResult | None, list[StageResult]]:
    _emit_milestone("text_stage_start", pdf_path=str(pdf_path), bytes=_milestone_pdf_size(pdf_path))
    methods: list[tuple[str, Callable[[], StageResult]]] = [
        ("pdftotext", lambda: _pdftotext_stage(pdf_path)),
        ("pypdf", lambda: _pypdf_stage(pdf_path)),
        ("pymupdf", lambda: _pymupdf_stage(pdf_path)),
    ]
    results: list[StageResult] = []
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="rag20-text") as pool:
        future_map = {pool.submit(fn): name for name, fn in methods}
        for future in as_completed(future_map):
            result = future.result()
            results.append(result)
    best = _best_text_result(results)
    _emit_milestone("text_stage_done", pdf_path=str(pdf_path), bytes=_milestone_pdf_size(pdf_path), candidates=len(results), winner=(best.method if best else None))
    return best, results


def _ocr_timeout_for(pdf_path: Path) -> float:
    size_mb = max(pdf_path.stat().st_size / (1024 * 1024), 0.0)
    timeout = 90.0 + (size_mb * 45.0)
    return max(90.0, min(timeout, OCR_TIMEOUT_S))


def _ocr_pdftoppm_stage(pdf_path: Path) -> StageResult:
    start = perf_counter()
    timeout_s = _ocr_timeout_for(pdf_path)
    tesseract = shutil.which("tesseract")
    pdftoppm = shutil.which("pdftoppm")
    if not tesseract or not pdftoppm:
        return StageResult([], 0, "pdftoppm", 0.0, False, "pdftoppm/tesseract unavailable")
    try:
        with tempfile.TemporaryDirectory(prefix="rag20-ocr-") as td:
            temp_dir = Path(td)
            prefix = temp_dir / "ppm"
            proc = subprocess.run(
                [pdftoppm, "-png", "-r", "200", str(pdf_path), str(prefix)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout_s,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="replace")[-1000:]
                return StageResult([], 0, "pdftoppm", perf_counter() - start, False, err or f"returncode={proc.returncode}")
            images = sorted(temp_dir.glob("*.png"))
            pages: list[str] = []
            for image in images:
                try:
                    ocr = subprocess.run(
                        [tesseract, str(image), "stdout", "--psm", "6"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=timeout_s,
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    err = (exc.stderr or b"").decode("utf-8", errors="replace")[-1000:]
                    return StageResult([], 0, "pdftoppm", perf_counter() - start, False, err or f"tesseract returncode={exc.returncode}")
                except Exception as exc:
                    return StageResult([], 0, "pdftoppm", perf_counter() - start, False, str(exc))
                pages.append((ocr.stdout.decode("utf-8", errors="replace") or "").strip())
            return _text_result(pages, len(pages), "pdftoppm", perf_counter() - start)
    except Exception as exc:
        return StageResult([], 0, "pdftoppm", perf_counter() - start, False, str(exc))


def _ocr_pdftocairo_stage(pdf_path: Path) -> StageResult:
    start = perf_counter()
    timeout_s = _ocr_timeout_for(pdf_path)
    tesseract = shutil.which("tesseract")
    pdftocairo = shutil.which("pdftocairo")
    if not tesseract or not pdftocairo:
        return StageResult([], 0, "pdftocairo", 0.0, False, "pdftocairo/tesseract unavailable")
    try:
        with tempfile.TemporaryDirectory(prefix="rag20-ocr-") as td:
            temp_dir = Path(td)
            prefix = temp_dir / "cairo"
            proc = subprocess.run(
                [pdftocairo, "-png", "-r", "200", str(pdf_path), str(prefix)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout_s,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="replace")[-1000:]
                return StageResult([], 0, "pdftocairo", perf_counter() - start, False, err or f"returncode={proc.returncode}")
            images = sorted(temp_dir.glob("*.png"))
            pages: list[str] = []
            for image in images:
                try:
                    ocr = subprocess.run(
                        [tesseract, str(image), "stdout", "--psm", "6"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=timeout_s,
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    err = (exc.stderr or b"").decode("utf-8", errors="replace")[-1000:]
                    return StageResult([], 0, "pdftocairo", perf_counter() - start, False, err or f"tesseract returncode={exc.returncode}")
                except Exception as exc:
                    return StageResult([], 0, "pdftocairo", perf_counter() - start, False, str(exc))
                pages.append((ocr.stdout.decode("utf-8", errors="replace") or "").strip())
            return _text_result(pages, len(pages), "pdftocairo", perf_counter() - start)
    except Exception as exc:
        return StageResult([], 0, "pdftocairo", perf_counter() - start, False, str(exc))


def _ocr_gs_stage(pdf_path: Path) -> StageResult:
    start = perf_counter()
    timeout_s = _ocr_timeout_for(pdf_path)
    tesseract = shutil.which("tesseract")
    gs = shutil.which("gs") or shutil.which("ghostscript")
    if not tesseract or not gs:
        return StageResult([], 0, "gs", 0.0, False, "gs/tesseract unavailable")
    try:
        with tempfile.TemporaryDirectory(prefix="rag20-ocr-") as td:
            temp_dir = Path(td)
            out_file = temp_dir / "gs-%03d.png"
            proc = subprocess.run(
                [gs, "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", "-r200", f"-sOutputFile={out_file}", str(pdf_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout_s,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="replace")[-1000:]
                return StageResult([], 0, "gs", perf_counter() - start, False, err or f"returncode={proc.returncode}")
            images = sorted(temp_dir.glob("*.png"))
            pages: list[str] = []
            for image in images:
                try:
                    ocr = subprocess.run(
                        [tesseract, str(image), "stdout", "--psm", "6"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=timeout_s,
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    err = (exc.stderr or b"").decode("utf-8", errors="replace")[-1000:]
                    return StageResult([], 0, "gs", perf_counter() - start, False, err or f"tesseract returncode={exc.returncode}")
                except Exception as exc:
                    return StageResult([], 0, "gs", perf_counter() - start, False, str(exc))
                pages.append((ocr.stdout.decode("utf-8", errors="replace") or "").strip())
            return _text_result(pages, len(pages), "gs", perf_counter() - start)
    except Exception as exc:
        return StageResult([], 0, "gs", perf_counter() - start, False, str(exc))


def _ocr_stage(pdf_path: Path) -> StageResult | None:
    for fn in (_ocr_pdftoppm_stage, _ocr_pdftocairo_stage, _ocr_gs_stage):
        _emit_milestone("ocr_branch_start", tool=fn.__name__, pdf_path=str(pdf_path), bytes=_milestone_pdf_size(pdf_path))
        result = fn(pdf_path)
        if result.usable:
            return result
    return None


def _sniff_source_kind(pdf_path: Path) -> str:
    data = pdf_path.read_bytes()[:4096]
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "word"
    if data.startswith(b"PK\x03\x04"):
        return "word" if pdf_path.suffix.lower() in {".docx", ".docm", ".dotx", ".dotm"} else "pdf"
    if data.lstrip().startswith(b"%PDF"):
        return "pdf"
    if pdf_path.suffix.lower() in {".doc", ".docx", ".dot", ".dotm"}:
        return "word"
    return "unknown"


def _download_pdf_to_path(pdf_url: str, destination: Path) -> None:
    from scripts.http_session import get_session

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.part")
    response = get_session().get(pdf_url, stream=True, timeout=120)
    response.raise_for_status()
    try:
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def _stable_pdf_filename(pdf_id: str) -> str:
    safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(pdf_id))
    return f"{safe_id or 'unknown'}.pdf"


def split_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\f", "\n\n", "\n", ". ", "? ", "! ", "; ", ": ", " ", ""],
    )
    return splitter.split_text(text)


def _chunk_documents_from_pages(
    *,
    source_name: str,
    patient_id: str,
    patient_name: str,
    pages: list[str],
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[Document]:
    chunks = split_text("\f".join(pages), chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    documents: list[Document] = []
    for chunk_index, chunk_text in enumerate(chunks):
        documents.append(
            Document(
                page_content=chunk_text,
                metadata={
                    "source_name": source_name,
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "chunk_index": chunk_index,
                },
            )
        )
    return documents


def _extract_pdf_pages_local(pdf_path: Path) -> tuple[list[str], dict[str, object]]:
    text_result, candidates = _text_stage(pdf_path)
    if text_result and text_result.usable:
        return text_result.pages, {
            "method": text_result.method,
            "page_count": text_result.page_count,
            "candidates": candidates,
        }
    ocr_result = _ocr_stage(pdf_path)
    if ocr_result and ocr_result.usable:
        return ocr_result.pages, {
            "method": ocr_result.method,
            "page_count": ocr_result.page_count,
            "candidates": [ocr_result],
        }
    return [], {"method": None, "page_count": 0, "candidates": []}


def _build_work_item(
    *,
    client_id: str,
    client_name: str,
    patient_id: str,
    patient_name: str,
    chart_id: str,
    filename: str,
    pdf_storage_dir: Path,
    client_index: int,
    patient_index: int,
    chart_index: int,
) -> ChartWorkItem:
    return ChartWorkItem(
        client_id=client_id,
        client_name=client_name,
        patient_id=patient_id,
        patient_name=patient_name,
        chart_id=chart_id,
        filename=filename,
        pdf_path=pdf_storage_dir / _stable_pdf_filename(chart_id),
        client_index=client_index,
        patient_index=patient_index,
        chart_index=chart_index,
    )


def _process_chart_work_item(
    item: ChartWorkItem,
    *,
    database_url: str,
    checkpoint_path: Path | None,
    processed_dir: Path,
    deferred_dir: Path,
    counters: dict[str, int],
    pdf_url: str | None,
    progress_index: int,
) -> None:
    progress_total = RUN_TOTAL_CLIENTS
    checkpoint_payload: dict[str, object] = {
        "status": "item_start",
        "client_id": item.client_id,
        "client_name": item.client_name,
        "client_index": item.client_index,
        "patient_id": item.patient_id,
        "patient_name": item.patient_name,
        "patient_index": item.patient_index,
        "chart_id": item.chart_id,
        "filename": item.filename,
        "chart_index": item.chart_index,
    }
    try:
        pdf_path, restore_to_processed, was_skipped = _resolve_pdf_path(
            storage_path=item.pdf_path,
            processed_dir=processed_dir,
            pdf_url=pdf_url,
            database_url=database_url,
            chart_id=item.chart_id,
            filename=item.filename,
        )
    except (requests.exceptions.RequestException, FileNotFoundError) as exc:
        counters["deferred"] += 1
        counters["completed"] += 1
        print(
            json.dumps(
                {
                    "status": "deferred",
                    "client_index": item.client_index,
                    "patient_id": item.patient_id,
                    "chart_id": item.chart_id,
                    "filename": item.filename,
                    "error": str(exc),
                }
            ),
            flush=True,
        )
        _write_deferred_row(
            database_url=database_url,
            source_name=f"{item.client_id}:{item.patient_id}:{item.filename}",
            source_uri=pdf_url or str(item.pdf_path),
            client_id=item.client_id,
            patient_id=item.patient_id,
            patient_name=item.patient_name,
            pdf_id=item.chart_id,
            filename=item.filename,
            page_count=None,
            reason="download_failed",
            metadata={"client_id": item.client_id, "client_name": item.client_name, "error": str(exc)},
        )
        checkpoint_payload["status"] = "item_deferred_download"
        _write_checkpoint(checkpoint_path, checkpoint_payload)
        return
    if was_skipped:
        counters["skipped"] += 1
        counters["completed"] += 1
        _emit_milestone(
            "skipped",
            reason="already downloaded, pdf matches table, already loaded, skipping",
            progress=f"{progress_index}/{progress_total or '?'}",
            filename=item.filename,
            bytes=_safe_pdf_size(pdf_path),
        )
        checkpoint_payload["status"] = "item_skipped"
        _write_checkpoint(checkpoint_path, checkpoint_payload)
        return
    pages, extraction_meta = _extract_pdf_pages_local(pdf_path)
    page_count = int(extraction_meta.get("page_count") or len(pages))
    chunk_docs = _chunk_documents_from_pages(
        source_name=f"{item.client_id}:{item.patient_id}:{item.filename}",
        patient_id=item.patient_id,
        patient_name=item.patient_name,
        pages=pages,
    )
    timing = {
        "text_method": extraction_meta.get("method"),
        "ocr_used": bool(extraction_meta.get("method") and str(extraction_meta.get("method")).startswith(("pdftoppm", "pdftocairo", "gs"))),
    }
    if chunk_docs:
        winner_method = str(extraction_meta.get("method") or "")
        _count_method_win(counters, winner_method)
        load_meta = {
            "patient_id": item.patient_id,
            "patient_name": item.patient_name,
            "chart_id": item.chart_id,
            "filename": item.filename,
            "winner_method": winner_method,
            "timing": timing,
        }
        pdf_bytes = pdf_path.read_bytes()
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()
        pdf_size = len(pdf_bytes)
        _write_source_document_row(
            database_url=database_url,
            source_name=f"{item.client_id}:{item.patient_id}:{item.filename}",
            source_uri=pdf_url or str(pdf_path),
            content_hash=content_hash,
            content_length=pdf_size,
            page_count=page_count,
            chunk_count=len(chunk_docs),
            summary=f"ingested {len(chunk_docs)} chunks",
            metadata=load_meta,
        )
        processed_dir.mkdir(parents=True, exist_ok=True)
        if restore_to_processed and pdf_path.parent == processed_dir:
            pass
        else:
            processed_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf_path), str(processed_dir / pdf_path.name))
        _emit_milestone(
            "loaded",
            winner=winner_method,
            counts=_count_rollup(counters),
            pg=page_count,
            chunks=len(chunk_docs),
            progress=f"{progress_index}/{progress_total or '?'}",
            filename=item.filename,
            bytes=pdf_size,
        )
        checkpoint_payload["status"] = "item_loaded"
        _write_checkpoint(checkpoint_path, checkpoint_payload)
        return
    _write_deferred_row(
        database_url=database_url,
        source_name=f"{item.client_id}:{item.patient_id}:{item.filename}",
        source_uri=pdf_url or str(item.pdf_path),
        client_id=item.client_id,
        patient_id=item.patient_id,
        patient_name=item.patient_name,
        pdf_id=item.chart_id,
        filename=item.filename,
        page_count=page_count,
        reason="could_not_extract",
        metadata={"client_id": item.client_id, "client_name": item.client_name, "timing": timing},
    )
    deferred_dir.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        shutil.move(str(pdf_path), str(deferred_dir / pdf_path.name))
    _emit_milestone(
        "deferred",
        winner=None,
        reason="could_not_extract",
        counts=_count_rollup(counters),
        pg=page_count,
        chunks=0,
        progress=f"{progress_index}/{progress_total or '?'}",
        filename=item.filename,
        bytes=_safe_pdf_size(pdf_path),
    )
    checkpoint_payload["status"] = "item_deferred_extract"
    _write_checkpoint(checkpoint_path, checkpoint_payload)


def _main_once(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instinct RAG importer 2.0 batch walker")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--database-url", default="")
    parser.add_argument("--pdf-storage-dir", default=str(Path("/home/ggb66/dev/EVH/data/instinct-pdfs")))
    parser.add_argument("--deferred-dir", default=str(Path("/home/ggb66/dev/EVH/data/instinct-pdfs-deferred")))
    parser.add_argument("--processed-dir", default=str(Path("/home/ggb66/dev/EVH/data/instinct-pdfs-processed")))
    parser.add_argument("--start-client-index", type=int, default=0)
    parser.add_argument("--limit-clients", type=int, default=0)
    parser.add_argument("--limit-pdfs", type=int, default=0)
    parser.add_argument("--start-client-id", default="", help="inclusive minimum account/client id to process")
    parser.add_argument("--end-client-id", default="", help="inclusive maximum account/client id to process")
    parser.add_argument("--log-dir", default="", help="directory for the run log file")
    parser.add_argument("--log-file", default="", help="explicit log file path; overrides derived name")
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--max-restarts", type=int, default=0, help="when supervising, restart after crashes up to this many times")
    parser.add_argument("--restart-delay-seconds", type=float, default=2.0, help="delay before supervised restart")
    parser.add_argument("--supervise", action="store_true", help="restart the importer after unexpected exits")
    parser.add_argument("--verbose-sql", action="store_true", help="emit SQL start/done/failure logging")
    args = parser.parse_args(argv)

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials.")
    if not args.database_url:
        raise SystemExit("Missing --database-url.")

    global RUN_LAST_EVENT_AT
    RUN_LAST_EVENT_AT = None
    global RUN_LOG_PATH
    RUN_LOG_PATH = Path(args.log_file).expanduser() if args.log_file.strip() else _build_run_log_path(
        args.start_client_index,
        args.limit_pdfs,
        Path(args.log_dir).expanduser() if args.log_dir.strip() else None,
    )
    _redirect_stdio_to_log(RUN_LOG_PATH)
    _emit_milestone("startup", pid=os.getpid(), ppid=os.getppid())
    pdf_storage_dir = Path(args.pdf_storage_dir).expanduser()
    deferred_dir = Path(args.deferred_dir).expanduser()
    processed_dir = Path(args.processed_dir).expanduser()
    database_url = args.database_url.strip() or None
    set_sql_verbose_logging(bool(args.verbose_sql))
    checkpoint_path = Path(args.checkpoint).expanduser() if args.checkpoint.strip() else Path(f"/tmp/evh_instinct_import.client_{args.start_client_index}.checkpoint.json")
    counters = _new_counters()
    checkpoint = _load_checkpoint(checkpoint_path)
    requested_start_client_index = int(args.start_client_index or 0)
    resume_client_index = max(int(checkpoint.get("client_index") or requested_start_client_index or 0), requested_start_client_index)
    resume_patient_index = int(checkpoint.get("patient_index") or -1)
    resume_chart_index = int(checkpoint.get("chart_index") or -1)
    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.authenticate()
    accounts = list(adapter.iter_accounts())
    global RUN_TOTAL_CLIENTS
    RUN_TOTAL_CLIENTS = len(accounts)
    global RUN_DEFERRED_LOADED_CACHE
    RUN_DEFERRED_LOADED_CACHE = _load_deferred_loaded_cache(args.database_url)
    start_client_id = _parse_client_id_value(args.start_client_id)
    end_client_id = _parse_client_id_value(args.end_client_id)
    client_index_limit = requested_start_client_index + args.limit_clients if args.limit_clients else None
    _emit_milestone(
        "resume_window",
        requested_start_client_index=requested_start_client_index,
        checkpoint_client_index=int(checkpoint.get("client_index") or -1),
        resume_client_index=resume_client_index,
        client_index_limit=client_index_limit,
        checkpoint_path=str(checkpoint_path),
    )
    if client_index_limit is not None and resume_client_index >= client_index_limit:
        _emit_milestone(
            "resume_window_exhausted",
            requested_start_client_index=requested_start_client_index,
            checkpoint_client_index=int(checkpoint.get("client_index") or -1),
            resume_client_index=resume_client_index,
            client_index_limit=client_index_limit,
            checkpoint_path=str(checkpoint_path),
        )
        return 0

    processed_count = 0
    last_completed_client_index = resume_client_index - 1
    try:
        for client_index, account in iter_clients_from_index(accounts, resume_client_index):
            if client_index_limit is not None and client_index >= client_index_limit:
                break
            client_id = str(account.get("id") or "")
            client_id_value = _parse_client_id_value(client_id)
            if start_client_id is not None and client_id_value is not None and client_id_value < start_client_id:
                continue
            if end_client_id is not None and client_id_value is not None and client_id_value > end_client_id:
                break
            client_name = _resolve_client_name(account, client_id)
            last_patient_index = resume_patient_index
            last_chart_index = resume_chart_index
            _emit_milestone("client_start", client_name=client_name, client_index=client_index)
            for patient_index, patient in enumerate(adapter.iter_patients_for_account(client_id)):
                patient_id = str(patient.get("id") or "")
                if not patient_id:
                    continue
                patient_name = str(patient.get("name") or patient.get("patientName") or client_name or patient_id)
                _emit_milestone(
                    "patient_start",
                    patient_id=patient_id,
                    patient_name=patient_name,
                    client_index=client_index,
                    patient_index=patient_index,
                )
                if client_index == resume_client_index and patient_index < resume_patient_index:
                    continue
                last_patient_index = patient_index
                history = fetch_medical_history_visits(patient_id)
                charts_block = history.get("charts") if isinstance(history, dict) else []
                for chart_index, chart in enumerate(charts_block if isinstance(charts_block, list) else []):
                    chart_id = str(chart.get("id") or "")
                    if not chart_id:
                        continue
                    last_chart_index = chart_index
                    filename = str(chart.get("filename") or chart.get("label") or _stable_pdf_filename(chart_id))
                    if not _resume_after_item(
                        ChartWorkItem(
                            client_id=client_id,
                            client_name=client_name,
                            patient_id=patient_id,
                            patient_name=patient_name,
                            chart_id=chart_id,
                            filename=filename,
                            pdf_path=pdf_storage_dir / _stable_pdf_filename(chart_id),
                            client_index=client_index,
                            patient_index=patient_index,
                            chart_index=chart_index,
                        ),
                        resume_client_index=resume_client_index,
                        resume_patient_index=resume_patient_index,
                        resume_chart_index=resume_chart_index,
                    ):
                        continue
                    try:
                        pdf_url = create_chart_file_url(chart_id, inline=True)
                    except Exception as exc:
                        print(json.dumps({"status": "deferred", "client_index": client_index, "patient_id": patient_id, "chart_id": chart_id, "filename": filename, "error": str(exc)}), flush=True)
                        _write_document_identity_row(
                            database_url=database_url,
                            client_id=client_id,
                            patient_id=patient_id,
                            pdf_id=chart_id,
                            originalfilename=filename,
                        )
                        _write_deferred_row(
                            database_url=database_url,
                            source_name=f"{client_id}:{patient_id}:{filename}",
                            source_uri=None,
                            client_id=client_id,
                            patient_id=patient_id,
                            patient_name=patient_name,
                            pdf_id=chart_id,
                            filename=filename,
                            page_count=None,
                            reason=str(exc),
                            metadata={"client_id": client_id, "client_name": client_name},
                        )
                        continue
                    work_item = _build_work_item(
                        client_id=client_id,
                        client_name=client_name,
                        patient_id=patient_id,
                        patient_name=patient_name,
                        chart_id=chart_id,
                        filename=filename,
                        pdf_storage_dir=pdf_storage_dir,
                        client_index=client_index,
                        patient_index=patient_index,
                        chart_index=chart_index,
                    )
                    _process_chart_work_item(
                        work_item,
                        database_url=database_url or "",
                        checkpoint_path=checkpoint_path,
                        processed_dir=processed_dir,
                        deferred_dir=deferred_dir,
                        counters=counters,
                        pdf_url=pdf_url,
                        progress_index=processed_count + 1,
                    )
                    processed_count += 1
                    if args.limit_pdfs and processed_count >= args.limit_pdfs:
                        _write_checkpoint(
                            checkpoint_path,
                            {
                                "status": "document_complete",
                                "client_id": client_id,
                                "client_name": client_name,
                                "client_index": client_index,
                                "patient_id": patient_id,
                                "patient_name": patient_name,
                                "patient_index": patient_index,
                                "chart_id": chart_id,
                                "filename": filename,
                                "chart_index": chart_index,
                            },
                        )
                        return 0
            _write_checkpoint(
                checkpoint_path,
                {
                    "status": "client_complete",
                    "client_id": client_id,
                    "client_name": client_name,
                    "client_index": client_index,
                    "patient_index": last_patient_index,
                    "chart_index": last_chart_index,
                },
            )
            last_completed_client_index = client_index
    finally:
        if last_completed_client_index >= resume_client_index - 1:
            _write_checkpoint(
                checkpoint_path,
                {
                    "status": "client_resume",
                    "client_index": last_completed_client_index,
                    "patient_index": resume_patient_index,
                    "chart_index": resume_chart_index,
                },
            )

    return 0


def _run_supervised(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if "--supervise" in args:
        args.remove("--supervise")
    max_restarts = 0
    delay_seconds = 2.0
    filtered: list[str] = []
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--max-restarts" and index + 1 < len(args):
            try:
                max_restarts = int(args[index + 1])
            except ValueError:
                max_restarts = 0
            skip_next = True
            continue
        if arg == "--restart-delay-seconds" and index + 1 < len(args):
            try:
                delay_seconds = float(args[index + 1])
            except ValueError:
                delay_seconds = 2.0
            skip_next = True
            continue
        filtered.append(arg)

    restarts = 0
    while True:
        proc = subprocess.run([sys.executable, __file__, *filtered], check=False)
        code = proc.returncode
        if code == 0:
            return 0
        crashed = code < 0 or code in {128 + signal.SIGSEGV, 128 + signal.SIGABRT, 128 + signal.SIGBUS}
        if not crashed or restarts >= max_restarts:
            return code
        restarts += 1
        print(
            json.dumps(
                {
                    "status": "supervisor_restart",
                    "restart": restarts,
                    "max_restarts": max_restarts,
                    "exit_code": code,
                    "checkpoint_hint": "resume from the checkpoint file on next launch",
                }
            ),
            flush=True,
        )
        time.sleep(delay_seconds)


if __name__ == "__main__":
    raise SystemExit(_run_supervised() if "--supervise" in sys.argv[1:] else _main_once())
