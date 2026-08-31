"""Run the full live Instinct PDF import with loud progress output.

This walks:
- clients/accounts
- patients for each client
- chart files for each patient
- downloads each PDF one at a time
- OCRs image-only PDFs through the chunker fallback
- chunks and embeds with a real OpenAI embedding model
- loads chunks into Aurora Postgres/pgvector
- retains downloaded source PDFs in a stable on-disk store

The script prints a progress line for every significant step so long runs stay
visible and resumable by checkpoint file if needed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import shutil
from dataclasses import asdict, dataclass
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, deque
from statistics import mean
from pathlib import Path
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT.parents[4] / "data"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TRACE_FUNCTION_CALLS = os.environ.get("EVH_IMPORT_TRACE_CALLS", "").strip().lower() in {"1", "true", "yes", "on"}

_CHECKPOINT_SHUTDOWN_CALLBACK: Callable[[], None] | None = None

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_shard_utils import iter_clients_from_index
from scripts.instinct_pdf_chunker import (
    ChunkingConfig,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_DEFERRED_OCR_TABLE_NAME,
    EXTRACTOR_USAGE_COUNTS,
    DeferredOCRDocument,
    NoTextLayerError,
    PatientPdfSource,
    build_deferred_ocr_upsert_sql,
    chunk_patient_pdf_timed,
    fetch_processed_pdf_ids,
    load_into_postgres,
    has_processed_pdf_id,
    load_term_index,
    run_psql,
)
from scripts.instinct_pdf_family_sampler import create_chart_file_url, fetch_medical_history_visits

VERBOSE_LOGGING = False
@dataclass(frozen=True)
class ImportProgress:
    client_id: str
    patient_id: str
    pdf_id: str
    filename: str | None
    status: str
    page_count: int | None = None
    chunk_count: int | None = None
    content_length: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class PdfWorkItem:
    client_id: str
    client_name: str
    patient_id: str
    patient_name: str
    pdf_id: str
    filename: str
    source_uri: str
    pdf_path: Path
    client_index: int
    patient_index: int
    pdf_index: int


@dataclass(frozen=True)
class PdfWorkResult:
    client_id: str
    client_name: str
    patient_id: str
    patient_name: str
    pdf_id: str
    filename: str
    client_index: int
    patient_index: int
    pdf_index: int
    status: str
    page_count: int | None = None
    chunk_count: int | None = None
    detail: str | None = None
    timing: dict[str, float] | None = None


def _stable_pdf_filename(pdf_id: str) -> str:
    safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(pdf_id))
    return f"{safe_id or 'unknown'}.pdf"


def _extractor_usage_line() -> str:
    return "wins: " + ", ".join(
        f"{name}={EXTRACTOR_USAGE_COUNTS.get(name, 0)}"
        for name in ("pdftotext", "pypdf", "pymupdf", "pdftoppm", "pdftocairo", "gs", "tesseract")
    )


def _record_timing_extractor_wins(timing: dict[str, float] | None) -> None:
    if not timing:
        return
    text_method = str(timing.get("text_method") or "").strip()
    ocr_method = str(timing.get("ocr_method") or "").strip()
    if text_method in EXTRACTOR_USAGE_COUNTS:
        EXTRACTOR_USAGE_COUNTS[text_method] += 1
    if timing.get("ocr_used") and ocr_method in EXTRACTOR_USAGE_COUNTS:
        EXTRACTOR_USAGE_COUNTS[ocr_method] += 1
        if "tesseract" in EXTRACTOR_USAGE_COUNTS:
            EXTRACTOR_USAGE_COUNTS["tesseract"] += 1


def _current_pdf_size_bytes(pdf_id: str, *search_dirs: Path) -> int | None:
    candidate_name = _stable_pdf_filename(pdf_id)
    for directory in search_dirs:
        candidate = directory / candidate_name
        try:
            if candidate.is_file():
                return candidate.stat().st_size
        except OSError:
            continue
    return None


def _vprint(payload: dict[str, Any] | str) -> None:
    if not VERBOSE_LOGGING:
        return
    if isinstance(payload, str):
        print(payload, flush=True)
    else:
        print(json.dumps(payload, sort_keys=True), flush=True)


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


def _move_pdf_to_processed_dir(source_path: Path, processed_pdf_dir: Path) -> Path | None:
    if not source_path.is_file():
        return None
    processed_pdf_dir.mkdir(parents=True, exist_ok=True)
    destination = processed_pdf_dir / source_path.name
    if destination.exists():
        destination.unlink()
    shutil.move(str(source_path), str(destination))
    return destination


def _move_pdf_to_deferred_dir(source_path: Path, deferred_pdf_dir: Path) -> Path | None:
    if not source_path.is_file():
        return None
    deferred_pdf_dir.mkdir(parents=True, exist_ok=True)
    destination = deferred_pdf_dir / source_path.name
    if destination.exists():
        destination.unlink()
    shutil.move(str(source_path), str(destination))
    return destination


def trace_calls(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if TRACE_FUNCTION_CALLS:
            print(
                json.dumps(
                    {
                        "event": "function_enter",
                        "function": fn.__name__,
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
        try:
            result = fn(*args, **kwargs)
            if TRACE_FUNCTION_CALLS:
                print(
                    json.dumps(
                        {
                            "event": "function_exit",
                            "function": fn.__name__,
                        },
                                                sort_keys=True,
                    ),
                    flush=True,
                )
            return result
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "event": "function_error",
                        "function": fn.__name__,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
            raise

    return wrapper


@trace_calls
def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class InfrastructureFailure(RuntimeError):
    """A failure that retries cannot repair; stop before wasting more records."""


def _is_non_retryable_infrastructure_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "invalid_token",
        "unauthorized",
        "forbidden",
        "password authentication failed",
        "no pg_hba.conf entry",
        "no encryption",
        "connection refused",
        "could not connect",
        "connection failed",
        "ssl error",
        "certificate verify failed",
        "no module named",
    )
    return any(marker in text for marker in markers)


@trace_calls
def _chart_files_for_patient(
    patient_id: str,
    *,
    timeout_s: int = 5,
    max_attempts: int = 3,
    retry_delay_s: float = 5.0,
    progress_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if progress_state is not None:
        progress_state["current_stage"] = "f"
        progress_state["current_source_line"] = 1744
    print(
        json.dumps(
            {
                "status": "patient_history_fetch_start",
                "patient_id": patient_id,
            },
                        sort_keys=True,
        ),
        flush=True,
    )
    fetch_started = time.perf_counter()
    history = None
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        attempt_started = time.perf_counter()
        if progress_state is not None:
            progress_state["current_stage"] = "f"
            progress_state["current_source_line"] = 1745
        print(
            json.dumps(
                {
                    "status": "patient_history_fetch_attempt",
                    "patient_id": patient_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "timeout_seconds": timeout_s,
                },
                                sort_keys=True,
            ),
            flush=True,
        )
        try:
            if progress_state is not None:
                progress_state["current_stage"] = "f"
                progress_state["current_source_line"] = 1746
            history = fetch_medical_history_visits(patient_id, timeout=timeout_s)
            break
        except Exception as exc:
            last_exc = exc
            if progress_state is not None:
                progress_state["current_stage"] = "f"
                progress_state["current_source_line"] = 1747
            print(
                json.dumps(
                    {
                        "status": "patient_history_fetch_retry",
                        "patient_id": patient_id,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "attempt_elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "will_retry": attempt < max_attempts,
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
            if attempt < max_attempts:
                time.sleep(retry_delay_s)

    if history is None:
        elapsed = time.perf_counter() - fetch_started
        if last_exc is not None and _is_non_retryable_infrastructure_error(last_exc):
            print(
                json.dumps(
                    {
                        "status": "fatal_infrastructure_failure",
                        "reason": "patient_history_infrastructure_error",
                        "patient_id": patient_id,
                        "attempts": max_attempts,
                        "elapsed_seconds": round(elapsed, 3),
                        "error_type": type(last_exc).__name__,
                        "error": str(last_exc),
                        "action": "stop_importer",
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
            raise InfrastructureFailure(
                f"patient-history infrastructure failure after {max_attempts} attempts: {last_exc}"
            ) from last_exc
        print(
            json.dumps(
                {
                    "status": "patient_skip",
                    "reason": "medical_history_fetch_failed_after_retries",
                    "patient_id": patient_id,
                    "attempts": max_attempts,
                    "elapsed_seconds": round(elapsed, 3),
                    "error_type": type(last_exc).__name__ if last_exc else None,
                    "error": str(last_exc) if last_exc else "unknown error",
                },
                                sort_keys=True,
            ),
            flush=True,
        )
        return []

    patient_block = history.get("patient") if isinstance(history, dict) else None
    charts_block = history.get("charts") if isinstance(history, dict) else None
    if progress_state is not None:
        progress_state["current_stage"] = "f"
        progress_state["current_source_line"] = 1748
    chart_count = len(charts_block) if isinstance(charts_block, list) else None
    chart_type_counts: dict[str, int] = {}
    if isinstance(charts_block, list):
        if progress_state is not None:
            progress_state["current_stage"] = "f"
            progress_state["current_source_line"] = 1749
        for chart in charts_block:
            if isinstance(chart, dict):
                chart_type = _text(chart.get("__typename")) or "unknown"
                chart_type_counts[chart_type] = chart_type_counts.get(chart_type, 0) + 1

    if progress_state is not None:
        progress_state["current_stage"] = "f"
        progress_state["current_source_line"] = 1750
    print(
        json.dumps(
            {
                "status": "patient_history_received",
                "patient_id": patient_id,
                "elapsed_seconds": round(time.perf_counter() - fetch_started, 3),
                "has_patient": isinstance(patient_block, dict),
                "has_charts": isinstance(charts_block, list),
                "chart_count": chart_count,
                "chart_type_counts": chart_type_counts,
            },
                        sort_keys=True,
        ),
        flush=True,
    )

    charts = history.get("charts") or []
    results: list[dict[str, Any]] = []
    if progress_state is not None:
        progress_state["current_stage"] = "f"
        progress_state["current_source_line"] = 1751
    for chart in charts:
        if not isinstance(chart, dict) or chart.get("__typename") != "ChartFile":
            continue
        chart_id = _text(chart.get("id"))
        filename = _text(chart.get("filename"))
        if not chart_id or not filename:
            continue
        results.append(
            {
                "id": chart_id,
                "filename": filename,
                "label": _text(chart.get("label")),
                "type": _text(chart.get("type")),
            }
        )
    if progress_state is not None:
        progress_state["current_stage"] = "f"
        progress_state["current_source_line"] = 1752
    return results


@trace_calls
def _discovery_cache_path(default: str = "/tmp/evh_instinct_discovery_cache.json") -> Path:
    return Path(default)


@trace_calls
def _load_discovery_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


@trace_calls
def _write_discovery_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


@trace_calls
def _build_discovery_cache(adapter: InstinctApiAdapter, cache_path: Path, progress_state: dict[str, Any] | None = None) -> dict[str, Any]:
    cached = _load_discovery_cache(cache_path)
    if cached.get("accounts") and cached.get("patients_by_account"):
        return cached

    accounts: list[dict[str, Any]] = []
    patients_by_account: dict[str, list[dict[str, Any]]] = {}
    if progress_state is not None:
        progress_state["discovery_stage"] = "building"
        progress_state["discovery_accounts_seen"] = 0
        progress_state["discovery_patients_seen"] = 0
    print(
        json.dumps(
            {
                "status": "discovery_cache_building",
                "message": "Enumerating accounts and patients for cached discovery",
                "cache_path": str(cache_path),
            },
                        sort_keys=True,
        ),
        flush=True,
    )
    for account in adapter.iter_accounts():
        account_id = _text(account.get("id")) or ""
        if not account_id:
            continue
        if progress_state is not None:
            progress_state["discovery_accounts_seen"] = int(progress_state.get("discovery_accounts_seen") or 0) + 1
        print(
            json.dumps(
                {
                    "status": "discovery_cache_account",
                    "client_id": account_id,
                    "client_name": _text(account.get("name") or account.get("displayName") or account.get("businessName")) or account_id,
                },
                                sort_keys=True,
            ),
            flush=True,
        )
        accounts.append(account)
        patient_list = list(adapter.iter_patients_for_account(account_id))
        patients_by_account[account_id] = patient_list
        if progress_state is not None:
            progress_state["discovery_patients_seen"] = int(progress_state.get("discovery_patients_seen") or 0) + len(patient_list)
            progress_state["discovery_stage"] = f"account:{account_id}"
    cached = {"accounts": accounts, "patients_by_account": patients_by_account}
    _write_discovery_cache(cache_path, cached)
    if progress_state is not None:
        progress_state["discovery_stage"] = "ready"
    print(
        json.dumps(
            {
                "status": "discovery_cache_ready",
                "message": "Discovery cache built",
                "accounts_cached": len(accounts),
                "patient_lists_cached": len(patients_by_account),
                "cache_path": str(cache_path),
            },
                        sort_keys=True,
        ),
        flush=True,
    )
    return cached


@trace_calls
def _load_checkpoint(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _count_deferred_ocr_rows(database_url: str, table_name: str) -> int:
    completed = run_psql(
        database_url,
        f"SELECT count(*) FROM {table_name} WHERE status IN ('ocr_not_reached_deferred', 'deferred');",
    )
    for line in reversed((completed.stdout or "").splitlines()):
        stripped = line.strip()
        if stripped.isdigit():
            return int(stripped)
    return 0


def _count_pdf_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".pdf")


@trace_calls
def _write_checkpoint(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _load_skipped_pdf_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    values = payload.get("skipped_pdf_ids") if isinstance(payload, dict) else None
    return {str(value) for value in values or [] if str(value).strip()}


def _remember_skipped_pdf(path: Path | None, skipped_pdf_ids: set[str], pdf_id: str) -> None:
    skipped_pdf_ids.add(str(pdf_id))
    if path is not None:
        path.write_text(
            json.dumps({"skipped_pdf_ids": sorted(skipped_pdf_ids)}, sort_keys=True),
            encoding="utf-8",
        )


def _load_pdf_history_manifest(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    values = payload.get("slow_pdf_ids") if isinstance(payload, dict) else None
    return {str(value) for value in values or [] if str(value).strip()}


def _remember_pdf_history(path: Path | None, slow_pdf_ids: set[str], pdf_id: str) -> None:
    slow_pdf_ids.add(str(pdf_id))
    if path is not None:
        path.write_text(
            json.dumps({"slow_pdf_ids": sorted(slow_pdf_ids)}, sort_keys=True),
            encoding="utf-8",
        )


def _load_slow_pdf_history_from_log(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return set()
    slow_pdf_ids: set[str] = set()
    for line in lines:
        if "PDF text extraction exceeded 45 seconds" in line or "no extractable text layer found" in line:
            match = re.search(r'"pdf_id":\s*"(?P<pdf_id>\d+)"', line)
            if match:
                slow_pdf_ids.add(match.group("pdf_id"))
    return slow_pdf_ids


@trace_calls
def _install_crash_beacon() -> None:
    def _hook(exc_type, exc, tb):
        print(
            json.dumps(
                {
                    "status": "top_level_exception",
                    "error_type": getattr(exc_type, "__name__", str(exc_type)),
                    "error": str(exc),
                },
                                sort_keys=True,
            ),
            flush=True,
        )
        traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = _hook

    def _signal_handler(signum, frame):
        try:
            signal_name = signal.Signals(signum).name
        except Exception:
            signal_name = str(signum)
        print(
            json.dumps(
                {
                    "status": "signal_received",
                    "signal": signum,
                    "signal_name": signal_name,
                },
                                sort_keys=True,
            ),
            flush=True,
        )
        if _CHECKPOINT_SHUTDOWN_CALLBACK is not None:
            try:
                _CHECKPOINT_SHUTDOWN_CALLBACK()
            except Exception as checkpoint_exc:
                print(
                    json.dumps(
                        {
                            "status": "checkpoint_shutdown_save_failed",
                            "error_type": type(checkpoint_exc).__name__,
                            "error": str(checkpoint_exc),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _signal_handler)
        except Exception:
            pass


@trace_calls
def _require_table_exists(database_url: str, table_name: str) -> None:
    result = run_psql(
        database_url,
        f"""
SELECT 1
FROM information_schema.tables
WHERE table_schema = current_schema()
  AND table_name = '{table_name}'
LIMIT 1;
""".strip(),
    )
    if result.stdout.strip():
        return
    raise RuntimeError(f"Required table {table_name!r} does not exist; provision schema outside this importer first.")


@trace_calls
def _supervise_import_threaded(argv: list[str] | None) -> int:
    child_args = [sys.executable, str(Path(__file__).resolve()), *(argv or sys.argv[1:])]
    log_path = Path("/tmp/evh_instinct_import.supervised.log")
    exitcode_path = Path("/tmp/evh_instinct_import.exitcode")
    log_path.write_text("", encoding="utf-8")
    exitcode_path.write_text("", encoding="utf-8")

    stop_event = threading.Event()
    proc_holder: dict[str, subprocess.Popen[str] | None] = {"proc": None}
    startup_deadline_s = 45
    silence_deadline_s = 70
    max_same_failures = 3
    same_failure_count = 0
    last_signature: tuple[int, str] | None = None

    def monitor() -> None:
        last_size = 0
        saw_startup = False
        last_progress = time.time()
        while not stop_event.is_set():
            proc = proc_holder["proc"]
            if proc is None:
                time.sleep(0.25)
                continue
            rc = proc.poll()
            if rc is not None:
                break
            try:
                size = log_path.stat().st_size
            except Exception:
                size = last_size
            if size > last_size:
                last_size = size
                last_progress = time.time()
                tail = _tail_text(log_path, 120)
                if '"status": "starting"' in tail or '"status": "importing"' in tail:
                    saw_startup = True
                print(
                    json.dumps(
                        {
                            "status": "supervisor_progress",
                            "reason": "log_growth",
                            "log_size": size,
                            "elapsed_since_progress": round(time.time() - last_progress, 3),
                            "saw_startup": saw_startup,
                            "tail_has_starting": '"status": "starting"' in tail,
                            "tail_has_importing": '"status": "importing"' in tail,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            elapsed = time.time() - last_progress
            if not saw_startup and elapsed > startup_deadline_s:
                print(
                    json.dumps(
                        {
                            "status": "supervisor_terminate",
                            "reason": "startup_silence",
                            "elapsed_since_progress": round(elapsed, 3),
                            "startup_deadline_s": startup_deadline_s,
                            "silence_deadline_s": silence_deadline_s,
                            "log_size": last_size,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                proc.terminate()
                time.sleep(5)
                if proc.poll() is None:
                    print(
                        json.dumps(
                            {
                                "status": "supervisor_kill",
                                "reason": "startup_silence_escalation",
                                "elapsed_since_progress": round(time.time() - last_progress, 3),
                                "log_size": last_size,
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    proc.kill()
                break
            if saw_startup and elapsed > silence_deadline_s:
                print(
                    json.dumps(
                        {
                            "status": "supervisor_terminate",
                            "reason": "silence_timeout",
                            "elapsed_since_progress": round(elapsed, 3),
                            "startup_deadline_s": startup_deadline_s,
                            "silence_deadline_s": silence_deadline_s,
                            "log_size": last_size,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                proc.terminate()
                time.sleep(5)
                if proc.poll() is None:
                    print(
                        json.dumps(
                            {
                                "status": "supervisor_kill",
                                "reason": "silence_timeout_escalation",
                                "elapsed_since_progress": round(time.time() - last_progress, 3),
                                "log_size": last_size,
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    proc.kill()
                break
            time.sleep(1)

    monitor_thread = threading.Thread(target=monitor, name="evh-import-supervisor", daemon=True)
    monitor_thread.start()

    attempt = 0
    while True:
        attempt += 1
        with log_path.open("a", encoding="utf-8") as logf:
            logf.write(f"==== threaded supervisor attempt {attempt} starting child ====\n")
            logf.flush()
            proc_holder["proc"] = subprocess.Popen(
                child_args,
                stdout=logf,
                stderr=subprocess.STDOUT,
                env={**os.environ, "EVH_IMPORT_CHILD": "1"},
                cwd=str(PROJECT_ROOT),
            )
            rc = proc_holder["proc"].wait()
            print(
                json.dumps(
                    {
                        "status": "supervisor_child_exit",
                        "attempt": attempt,
                        "returncode": rc,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            tail = _tail_text(log_path, 40).strip()
            signature = (int(rc), tail.splitlines()[-1] if tail else "")
            if last_signature == signature:
                same_failure_count += 1
            else:
                same_failure_count = 1
                last_signature = signature
            exitcode_path.write_text(str(rc), encoding="utf-8")
            logf.write(f"==== threaded supervisor attempt {attempt} rc={rc} same_failure_count={same_failure_count} ====\n")
            logf.flush()
        if rc == 0:
            print(
                json.dumps(
                    {
                        "status": "supervisor_done",
                        "attempt": attempt,
                        "reason": "child_completed",
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            stop_event.set()
            monitor_thread.join(timeout=10)
            return 0
        if same_failure_count >= max_same_failures:
            print(
                json.dumps(
                    {
                        "status": "supervisor_done",
                        "attempt": attempt,
                        "reason": "max_same_failures",
                        "same_failure_count": same_failure_count,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            stop_event.set()
            monitor_thread.join(timeout=10)
            return rc
        time.sleep(5)


@trace_calls
def _tail_text(path: Path, lines: int = 40) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return "\n".join(data.splitlines()[-lines:])


@trace_calls
def _supervise_child_process(child_args: list[str], log_path: Path, exitcode_path: Path) -> int:
    same_failure_count = 0
    last_signature: tuple[int, str] | None = None
    max_same_failures = 3
    startup_deadline_s = 45
    silence_deadline_s = 70

    attempt = 0
    while True:
        attempt += 1
        log_path.parent.mkdir(parents=True, exist_ok=True)
        exitcode_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as logf:
            logf.write(f"==== attempt {attempt} starting child ====\n")
            logf.flush()
            proc = subprocess.Popen(
                child_args,
                stdout=logf,
                stderr=subprocess.STDOUT,
                env={**os.environ, "EVH_IMPORT_CHILD": "1"},
                cwd=str(PROJECT_ROOT / "pony" / "worktrees" / "rd"),
            )
            start = time.time()
            saw_startup = False
            last_size = log_path.stat().st_size
            while True:
                rc = proc.poll()
                if rc is not None:
                    break
                time.sleep(1)
                try:
                    size = log_path.stat().st_size
                except Exception:
                    size = last_size
                if size > last_size:
                    last_size = size
                    tail = _tail_text(log_path, 120)
                    if '"status": "starting"' in tail or '"status": "importing"' in tail:
                        saw_startup = True
                elapsed = time.time() - start
                if not saw_startup and elapsed > startup_deadline_s:
                    logf.write("==== no startup log observed; terminating child ====\n")
                    logf.flush()
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        proc.kill()
                    rc = proc.wait()
                    break
                if saw_startup and elapsed > startup_deadline_s and size == last_size:
                    logf.write("==== child silent after startup; terminating child ====\n")
                    logf.flush()
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        proc.kill()
                    rc = proc.wait()
                    break
            tail = _tail_text(log_path, 40).strip()
            exitcode_path.write_text(str(rc), encoding="utf-8")
            signature = (int(rc), tail.splitlines()[-1] if tail else "")
            if last_signature == signature:
                same_failure_count += 1
            else:
                same_failure_count = 1
                last_signature = signature
            if rc == 0:
                return 0
            if same_failure_count >= max_same_failures:
                return rc
            time.sleep(5)


@trace_calls
def _checkpoint_payload(
    *,
    client_id: str | None = None,
    patient_id: str | None = None,
    pdf_id: str | None = None,
    filename: str | None = None,
    loaded_count: int = 0,
    skipped_count: int = 0,
    deferred_count: int = 0,
    pdf_count: int = 0,
    total_pdf_count: int | None = None,
    error: dict[str, Any] | None = None,
    retry_attempts: int = 0,
    client_seen_count: int = 0,
    patient_seen_count: int = 0,
    client_index: int | None = None,
    patient_index: int | None = None,
    pdf_index: int | None = None,
    client_name: str | None = None,
    patient_name: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "loaded_count": loaded_count,
        "skipped_count": skipped_count,
        "deferred_count": deferred_count,
        "pdf_count": pdf_count,
        "total_pdf_count": total_pdf_count if total_pdf_count is not None else loaded_count + deferred_count,
        "client_seen_count": client_seen_count,
        "patient_seen_count": patient_seen_count,
        "current_client_id": client_id,
        "current_patient_id": patient_id,
        "current_pdf_id": pdf_id,
        "current_client_index": client_index,
        "current_patient_index": patient_index,
        "current_pdf_index": pdf_index,
        "current_filename": filename,
        "current_client_name": client_name,
        "current_patient_name": patient_name,
        "retry_attempts": retry_attempts,
    }
    if error is not None:
        payload["last_error"] = error
    return payload


@trace_calls
def _print_progress(item: ImportProgress) -> None:
    print(
        json.dumps(asdict(item), sort_keys=True),
        flush=True,
    )


def _is_sql_syntax_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "syntax error" in text or "column" in text and "does not exist" in text or "relation" in text and "does not exist" in text


def _is_connection_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "could not connect",
            "connection refused",
            "connection timed out",
            "timeout expired",
            "server closed the connection unexpectedly",
            "could not send data to server",
            "no route to host",
            "network is unreachable",
            "fe_sendauth",
        )
    )


@trace_calls
def _record_deferred_ocr_best_effort(
    *,
    database_url: str,
    deferred_ocr_table_name: str,
    source_name: str,
    source_uri: str,
    patient_id: str,
    patient_name: str,
    pdf_id: str,
    filename: str,
    page_count: int | None,
    reason: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        run_psql(
            database_url,
            build_deferred_ocr_upsert_sql(
                deferred_ocr_table_name,
                source_name=source_name,
                source_uri=source_uri,
                client_id=source_name.split(":", 1)[0] if ":" in source_name else None,
                patient_id=patient_id,
                patient_name=patient_name,
                pdf_id=pdf_id,
                filename=filename,
                page_count=page_count,
                reason=reason,
                status="ocr_needed" if reason != "already loaded; skipped by resume guard" else "skipped_already_loaded",
                metadata=metadata,
            ),
        )
        return None
    except subprocess.CalledProcessError as exc:
        if _is_sql_syntax_error(exc):
            raise
        if _is_connection_error(exc):
            return {
                "stage": "deferred_ocr_record_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        raise


@trace_calls
def _record_skipped_pdf_best_effort(
    *,
    database_url: str,
    deferred_ocr_table_name: str,
    source_name: str,
    source_uri: str,
    client_id: str,
    patient_id: str,
    patient_name: str,
    pdf_id: str,
    filename: str,
    page_count: int | None,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        run_psql(
            database_url,
            build_deferred_ocr_upsert_sql(
                deferred_ocr_table_name,
                source_name=source_name,
                source_uri=source_uri,
                client_id=client_id,
                patient_id=patient_id,
                patient_name=patient_name,
                pdf_id=pdf_id,
                filename=filename,
                page_count=page_count,
                reason="already loaded; skipped by resume guard",
                status="skipped_already_loaded",
                metadata={**metadata, "status": "skipped_already_loaded"},
            ),
        )
        return None
    except subprocess.CalledProcessError as exc:
        if _is_sql_syntax_error(exc):
            raise
        if _is_connection_error(exc):
            return {
                "stage": "skipped_pdf_record_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        raise


@trace_calls
def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "unknown"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


def _format_recent_rate(count: int, window_seconds: float) -> str:
    if count <= 0:
        return "0 in the last 0s"
    window_seconds = max(window_seconds, 1.0)
    if window_seconds < 60:
        return f"{count} in the last {int(round(window_seconds))}s"
    minutes = int(window_seconds // 60)
    seconds = int(round(window_seconds % 60))
    if minutes < 60:
        return f"{count} in the last {minutes}:{seconds:02d}"
    hours = minutes // 60
    rem_minutes = minutes % 60
    return f"{count} in the last {hours}h{rem_minutes:02d}m"


def _format_throughput_per_hour(count: int, window_seconds: float) -> str:
    if count <= 0:
        return "0.0/hr"
    hours = max(window_seconds, 1.0) / 3600.0
    return f"{count / hours:.1f}/hr"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


@trace_calls
def _print_stage(stage: str, **fields: Any) -> None:
    payload = {"stage": stage, **fields}
    print(json.dumps(payload, sort_keys=True), flush=True)


@trace_calls
def _print_timing(stage: str, seconds: float, **fields: Any) -> None:
    _print_stage(stage, elapsed_seconds=round(seconds, 3), **fields)


@trace_calls
def iter_all_patients(
    cache: dict[str, Any],
    *,
    resume_client_index: int = 0,
    resume_patient_index: int = 0,
    history_timeout_s: int = 5,
    history_max_attempts: int = 3,
    history_retry_delay_s: float = 5.0,
) -> Iterable[tuple[int, int, dict[str, Any], dict[str, Any]]]:
    accounts = list(cache.get("accounts") or [])
    for account_index, account in enumerate(accounts):
        if account_index < resume_client_index:
            continue
        client_id = _text(account.get("id"))
        if not client_id:
            continue
        client_name = _text(account.get("name") or account.get("displayName") or account.get("businessName")) or client_id
        print(json.dumps({"status": "client_start", "client_id": client_id, "client_name": client_name}), flush=True)
        patients = list(cache.get("patients_by_account", {}).get(client_id, []))
        for patient_index, patient in enumerate(patients):
            if account_index == resume_client_index and patient_index < resume_patient_index:
                continue
            patient_id = _text(patient.get("id"))
            if not patient_id:
                continue
            patient_name = _text(patient.get("name") or patient.get("patientName")) or patient_id
            print(
                json.dumps(
                    {
                        "status": "patient_start",
                        "client_id": client_id,
                        "patient_id": patient_id,
                        "patient_name": patient_name,
                    },
                                    ),
                flush=True,
            )
            yield account_index, patient_index, account, patient


def _process_pdf_work_item(
    item: PdfWorkItem,
    *,
    progress_state: dict[str, Any] | None,
    database_url: str,
    table_name: str,
    source_document_table_name: str,
    embedding_model: str,
    vector_dimensions: int,
    embedding_batch_size: int,
    load_batch_size: int,
    extraction_timeout: int,
    page_workers: int,
    term_index: Iterable[DictionaryTerm],
    chunk_size: int,
    chunk_overlap: int,
    deferred_pdf_dir: Path,
    processed_pdf_dir: Path,
) -> PdfWorkResult:
    worker_name = threading.current_thread().name
    job_started_at = time.perf_counter()
    if progress_state is not None:
        progress_state["current_stage"] = "w"
        progress_state["current_aux_stage"] = "k"
        progress_state["current_source_line"] = 1930
    _vprint({
        "status": "pdf_worker_start",
        "worker": worker_name,
        "client_id": item.client_id,
        "patient_id": item.patient_id,
        "pdf_id": item.pdf_id,
        "filename": item.filename,
        "pdf_path": str(item.pdf_path),
    })
    stored_pdf_path = item.pdf_path
    if progress_state is not None and progress_state.get("current_pdf") != item.filename:
        progress_state["current_pdf"] = item.filename
    if progress_state is not None and progress_state.get("current_pdf_size") is None:
        progress_state["current_pdf_size"] = stored_pdf_path.stat().st_size if stored_pdf_path.is_file() else None
    pdf_url: str | None = None
    download_seconds = 0.0
    if not (stored_pdf_path.is_file() and stored_pdf_path.stat().st_size > 0):
        if progress_state is not None:
            progress_state["current_stage"] = "w"
            progress_state["current_aux_stage"] = "k"
            progress_state["current_source_line"] = 1931
            progress_state["current_pdf_stage"] = "1"
            progress_state["current_pdf_size"] = "DOWNLOADING"
        download_start = time.perf_counter()
        if progress_state is not None:
            progress_state["current_source_line"] = 1932
        pdf_url = create_chart_file_url(item.pdf_id, inline=True)
        if progress_state is not None:
            progress_state["current_source_line"] = 1933
        _download_pdf_to_path(pdf_url, stored_pdf_path)
        download_seconds = time.perf_counter() - download_start
        print(
            json.dumps(
                {
                    "status": "pdf_download_timing",
                    "client_id": item.client_id,
                    "patient_id": item.patient_id,
                    "pdf_id": item.pdf_id,
                    "filename": item.filename,
                    "elapsed_seconds": round(download_seconds, 3),
                    "pdf_size_bytes": stored_pdf_path.stat().st_size if stored_pdf_path.is_file() else None,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if progress_state is not None:
            progress_state["current_pdf_size"] = stored_pdf_path.stat().st_size if stored_pdf_path.is_file() else None
    source = PatientPdfSource(
        patient_id=item.patient_id,
        patient_name=item.patient_name,
        pdf_id=item.pdf_id,
        pdf_path=stored_pdf_path,
        pdf_url=None,
    )
    config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if progress_state is not None:
        progress_state["current_stage"] = "w"
        progress_state["current_aux_stage"] = "k"
        progress_state["current_source_line"] = 1934
        progress_state["current_pdf_stage"] = "2"
    chunk_start = time.perf_counter()
    chunk_timing: dict[str, float] = {}
    if progress_state is not None:
        progress_state["current_source_line"] = 1935
    chunk_docs, _page_count, chunk_timing = chunk_patient_pdf_timed(
        source,
        config,
        term_index=term_index,
        extraction_timeout_s=extraction_timeout,
        page_workers=page_workers,
        progress_state=progress_state,
    )
    chunk_seconds = time.perf_counter() - chunk_start
    print(
        json.dumps(
            {
                "status": "pdf_chunk_invocation_timing",
                "client_id": item.client_id,
                "patient_id": item.patient_id,
                "pdf_id": item.pdf_id,
                "filename": item.filename,
                "elapsed_seconds": round(chunk_seconds, 3),
                "chunk_count": len(chunk_docs),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if progress_state is not None:
        progress_state["current_source_line"] = 1936
    if not chunk_docs:
        total_seconds = time.perf_counter() - job_started_at
        print(
            f"{0}->{chunk_seconds:.3f}s, {item.client_id} "
            f"{round(download_seconds, 3)}dl->{download_seconds:.3f}sec2dl, "
            f"{chunk_timing.get('extraction_seconds', 0.0):.3f}s->2xtract, "
            f"{item.filename} 0.000s2load {stored_pdf_path.stat().st_size if stored_pdf_path.is_file() else 0}bytes {item.patient_id} {item.pdf_id} "
            f"pdf_wrkr_done deferred {total_seconds:.3f}s {worker_name}",
            flush=True,
        )
        return PdfWorkResult(
            client_id=item.client_id,
            client_name=item.client_name,
            patient_id=item.patient_id,
            patient_name=item.patient_name,
            pdf_id=item.pdf_id,
            filename=item.filename,
            client_index=item.client_index,
            patient_index=item.patient_index,
            pdf_index=item.pdf_index,
            status="deferred",
            page_count=None,
            chunk_count=0,
            detail="no chunk documents produced",
            timing=chunk_timing,
        )
    load_start = time.perf_counter()
    if progress_state is not None:
        progress_state["current_stage"] = "w"
        progress_state["current_aux_stage"] = "k"
        progress_state["current_source_line"] = 1937
        progress_state["current_pdf_stage"] = "3"
    if progress_state is not None:
        progress_state["current_source_line"] = 1938
    print(
        json.dumps(
            {
                "status": "pdf_phase_begin",
                "phase": "load_into_postgres",
                "client_id": item.client_id,
                "patient_id": item.patient_id,
                "pdf_id": item.pdf_id,
                "filename": item.filename,
                "chunk_count": len(chunk_docs),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    load_into_postgres(
        database_url=database_url,
        table_name=table_name,
        source_document_table_name=source_document_table_name,
        source_name=f"{item.client_id}:{item.patient_id}:{item.filename}",
        source_uri=pdf_url or str(stored_pdf_path),
        documents=chunk_docs,
        embedding_model=embedding_model,
        vector_dimensions=vector_dimensions,
        embedding_batch_size=embedding_batch_size,
        load_batch_size=load_batch_size,
    )
    load_seconds = time.perf_counter() - load_start
    print(
        json.dumps(
            {
                "status": "pdf_phase_done",
                "phase": "load_into_postgres",
                "client_id": item.client_id,
                "patient_id": item.patient_id,
                "pdf_id": item.pdf_id,
                "filename": item.filename,
                "elapsed_seconds": round(load_seconds, 3),
                "chunk_count": len(chunk_docs),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if progress_state is not None:
        progress_state["current_source_line"] = 1939
    moved_to = _move_pdf_to_processed_dir(stored_pdf_path, processed_pdf_dir)
    move_seconds = time.perf_counter() - job_started_at - download_seconds - chunk_seconds - load_seconds
    print(
        json.dumps(
            {
                "status": "pdf_phase_done",
                "phase": "move_pdf_to_processed",
                "client_id": item.client_id,
                "patient_id": item.patient_id,
                "pdf_id": item.pdf_id,
                "filename": item.filename,
                "elapsed_seconds": round(move_seconds, 3),
                "moved": moved_to is not None,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    total_seconds = time.perf_counter() - job_started_at
    if progress_state is not None:
        progress_state["current_source_line"] = 1940
    if progress_state is not None:
        progress_state["current_source_line"] = 1941
    print(
        f"{len(chunk_docs)}->{chunk_seconds:.3f}s, {item.client_id} "
        f"{round(download_seconds, 3)}dl->{download_seconds:.3f}sec2dl, "
        f"{chunk_timing.get('extraction_seconds', 0.0):.3f}s->2xtract, "
        f"{item.filename} {load_seconds:.3f}s2load {stored_pdf_path.stat().st_size if stored_pdf_path.is_file() else 0}bytes {item.patient_id} {item.pdf_id} "
        f"pdf_wrkr_done loaded {total_seconds:.3f}s {worker_name}",
        flush=True,
    )
    if moved_to is not None:
        if progress_state is not None:
            progress_state["current_source_line"] = 1942
        print(json.dumps({"status": "pdf_moved_to_processed", "pdf_id": item.pdf_id, "path": str(moved_to)}, sort_keys=True), flush=True)
    if progress_state is not None:
        progress_state["current_source_line"] = 1943
        progress_state["current_aux_stage"] = "l"
    return PdfWorkResult(
        client_id=item.client_id,
        client_name=item.client_name,
        patient_id=item.patient_id,
        patient_name=item.patient_name,
        pdf_id=item.pdf_id,
        filename=item.filename,
        client_index=item.client_index,
        patient_index=item.patient_index,
        pdf_index=item.pdf_index,
        status="loaded",
        page_count=None,
        chunk_count=len(chunk_docs),
        timing=chunk_timing,
    )


def _defer_reason_bucket(detail: str | None) -> str:
    if not detail:
        return "unknown"
    if detail.startswith("preflight giant-doc heuristic"):
        return "giant_doc_heuristic"
    if detail.startswith("PDF skipped: no extractable text layer found."):
        return "no_text_layer"
    if detail.startswith("PDF text extraction exceeded"):
        return "text_timeout"
    if detail.startswith("PDF text extraction crashed"):
        return "text_crash"
    if detail.startswith("PDF text extraction failed and pdftotext fallback failed"):
        return "text_fallback_failed"
    if "RemoteDisconnected" in detail or "Connection aborted" in detail:
        return "remote_disconnected"
    if detail.startswith("HTTP Error 500"):
        return "http_500"
    if detail.startswith("502 Server Error"):
        return "http_502"
    if detail.startswith("The read operation timed out"):
        return "read_timeout"
    return "other"


class CountingHeartbeat:
    def __init__(
        self,
        label: str = "importing",
        interval_s: int = 10,
        state: dict[str, Any] | None = None,
    ) -> None:
        self.label = label
        self.interval_s = interval_s
        self.state = state or {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    def _marker(self) -> str:
        aux_stage = str(self.state.get("current_aux_stage") or "").strip().lower()
        pdf_stage = str(self.state.get("current_pdf_stage") or "").strip()
        loop_stage = str(self.state.get("current_stage") or "").strip()
        ocr_state = str(self.state.get("current_ocr_stage") or "").strip().lower()
        source_line = self.state.get("current_source_line")
        line_suffix = f"{source_line}" if source_line is not None else ""
        raw_stage = loop_stage
        if pdf_stage:
            raw_stage = f"{raw_stage}/{pdf_stage}" if raw_stage else pdf_stage
        if ocr_state:
            raw_stage = f"{raw_stage}/{ocr_state.upper()}" if raw_stage else ocr_state.upper()
        if aux_stage:
            raw_stage = f"{raw_stage}/{aux_stage}" if raw_stage else aux_stage

        if loop_stage in {"ready_for_import", "discovered", "checkpoint_resume", "preflight"}:
            return ("0" if not raw_stage else f"0[{raw_stage}]") + line_suffix
        if loop_stage == "s":
            return ("S" if not raw_stage else f"S[{raw_stage}]") + line_suffix
        if loop_stage == "b":
            return ("B" if not raw_stage else f"B[{raw_stage}]") + line_suffix
        if loop_stage in {"m", "n"}:
            return ("N" if not raw_stage else f"N[{raw_stage}]") + line_suffix
        if aux_stage == "l":
            return ("L" if not raw_stage else f"L[{raw_stage}]") + line_suffix
        if ocr_state in {"first", "a", "second", "b", "third", "c"}:
            return ("O" if not raw_stage else f"O[{raw_stage}]") + line_suffix
        if pdf_stage == "1":
            return ("D" if not raw_stage else f"D[{raw_stage}]") + line_suffix
        if pdf_stage in {"2", "3"}:
            return ("X" if not raw_stage else f"X[{raw_stage}]") + line_suffix
        if loop_stage == "d":
            return ("D" if not raw_stage else f"D[{raw_stage}]") + line_suffix
        if loop_stage in {"f", "c", "w"}:
            return ("X" if not raw_stage else f"X[{raw_stage}]") + line_suffix
        if aux_stage in {"z", "k"}:
            return ("X" if not raw_stage else f"X[{raw_stage}]") + line_suffix
        return (raw_stage or "?") + line_suffix

    def _run(self) -> None:
        tick = 0
        while not self._stop.wait(self.interval_s):
            tick += 1
            if tick == 1:
                print(
                    json.dumps(
                        {
                            "status": self.label,
                            "message": "Import in progress",
                            "heartbeat": tick,
                            "interval_seconds": self.interval_s,
                            "clients_seen": self.state.get("clients_seen", 0),
                            "patients_seen": self.state.get("patients_seen", 0),
                            "pdfs_seen": self.state.get("pdfs_seen", 0),
                            "current_client": self.state.get("current_client_name"),
                            "current_patient": self.state.get("current_patient_name"),
                            "current_pdf": self.state.get("current_pdf_name"),
                            "current_pdf_size": self.state.get("current_pdf_size"),
                            "current_page_count": self.state.get("current_page_count"),
                            "current_aux_stage": self.state.get("current_aux_stage"),
                            "current_pdf_stage": self.state.get("current_pdf_stage"),
                            "current_source_line": self.state.get("current_source_line"),
                            "current_stage": self.state.get("current_stage"),
                            "current_loop_stage": self.state.get("current_stage"),
                            "discovery_stage": self.state.get("discovery_stage"),
                            "discovery_accounts_seen": self.state.get("discovery_accounts_seen", 0),
                            "discovery_patients_seen": self.state.get("discovery_patients_seen", 0),
                            "eta": self.state.get("eta", "unknown"),
                            "eta_seconds": self.state.get("eta_seconds"),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            else:
                print(self._marker(), end="", flush=True)


@trace_calls
def main(argv: list[str] | None = None) -> int:
    _install_crash_beacon()
    parser = argparse.ArgumentParser(description="Run the full Instinct PDF ingest with progress output.")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--database-url", default=os.environ.get("EVH_PGDATABASE_URL", ""))
    parser.add_argument(
        "--start-client-index",
        type=int,
        default=0,
        help="0-based starting client index for this batch shard.",
    )
    parser.add_argument(
        "--pdf-storage-dir",
        default=os.environ.get(
            "EVH_PDF_STORAGE_DIR",
            str(DATA_ROOT / "instinct-pdfs"),
        ),
        help="Permanent storage directory for downloaded source PDFs.",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="Optional explicit checkpoint path; defaults to a start-client-index-specific filename.",
    )
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument(
        "--page-workers",
        type=int,
        default=int(os.environ.get("EVH_IMPORT_PAGE_WORKERS", "4")),
        help="Parallel workers for page-level text detection/chunking.",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--vector-dimensions", type=int, default=DEFAULT_EMBEDDING_DIMENSIONS)
    parser.add_argument("--embedding-batch-size", type=int, default=64, help="Batch size for embedding API requests.")
    parser.add_argument(
        "--embedding-workers",
        type=int,
        default=int(os.environ.get("EVH_IMPORT_EMBED_WORKERS", "2")),
        help="Parallel workers for embedding batch requests.",
    )
    parser.add_argument(
        "--client-pdf-workers",
        type=int,
        default=int(os.environ.get("EVH_IMPORT_CLIENT_PDF_WORKERS", "4")),
        help="Parallel workers for PDFs within a single client.",
    )
    parser.add_argument("--load-batch-size", type=int, default=500, help="Batch size for pgvector upserts.")
    parser.add_argument(
        "--delete-local-after-load",
        action="store_true",
        default=True,
        help="Legacy compatibility flag; source PDFs are always retained.",
    )
    parser.add_argument("--keep-local", action="store_true")
    parser.add_argument("--expected-clients", type=int, default=12053, help="Expected live client/account total for ETA math.")
    parser.add_argument("--dictionary-csv", default="")
    parser.add_argument("--table-name", default="pms_page_chunk")
    parser.add_argument("--source-document-table-name", default="rag_source_document")
    parser.add_argument("--deferred-ocr-table-name", default=DEFAULT_DEFERRED_OCR_TABLE_NAME)
    parser.add_argument(
        "--deferred-pdf-dir",
        default=str(DATA_ROOT / "instinct-pdfs-deferred"),
        help="Move unprocessed/deferred PDFs here when OCR/load cannot finish yet.",
    )
    parser.add_argument(
        "--processed-pdf-dir",
        default=str(DATA_ROOT / "instinct-pdfs-processed"),
        help="Move successfully processed PDFs here after load completes.",
    )
    parser.add_argument("--limit-clients", type=int, default=0, help="Optional cap for testing.")
    parser.add_argument("--limit-patients", type=int, default=0, help="Optional cap for testing.")
    parser.add_argument("--limit-pdfs", type=int, default=0, help="Optional cap for testing.")
    parser.add_argument("--history-timeout", type=int, default=5, help="Seconds before a patient history request is interrupted.")
    parser.add_argument("--history-attempts", type=int, default=3, help="Total attempts per patient history request.")
    parser.add_argument("--history-retry-delay", type=float, default=5.0, help="Seconds between patient history attempts.")
    parser.add_argument("--extraction-timeout", type=int, default=10, help="Seconds before PDF text extraction is deferred.")
    parser.add_argument("--verbose", action="store_true", help="Show detailed per-step import logging.")
    args = parser.parse_args(argv)
    global VERBOSE_LOGGING
    VERBOSE_LOGGING = bool(args.verbose)

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials: set INSTINCT_CLIENT_ID/SECRET or pass --username/--password.")
    if not args.database_url:
        raise SystemExit("Missing --database-url or EVH_PGDATABASE_URL.")

    _vprint({
        "status": "starting",
        "message": "Booting full Instinct import runner",
        "embedding_model": args.embedding_model,
        "vector_dimensions": args.vector_dimensions,
    })

    pdf_storage_dir = Path(args.pdf_storage_dir).expanduser()
    pdf_storage_dir.mkdir(parents=True, exist_ok=True)
    deferred_pdf_dir = Path(args.deferred_pdf_dir).expanduser()
    deferred_pdf_dir.mkdir(parents=True, exist_ok=True)
    processed_pdf_dir = Path(args.processed_pdf_dir).expanduser()
    checkpoint_path = (
        Path(args.checkpoint)
        if args.checkpoint
        else Path(f"/tmp/evh_instinct_import.client_{args.start_client_index}.checkpoint.json")
    )
    checkpoint = _load_checkpoint(checkpoint_path)
    processed: set[str] = set()
    seen_document_keys: set[tuple[str, str, str]] = set()
    skipped_manifest_path = (
        checkpoint_path.with_name(f"{checkpoint_path.name}.skipped.json")
        if checkpoint_path is not None
        else None
    )
    skipped_pdf_ids = _load_skipped_pdf_ids(skipped_manifest_path)
    slow_manifest_path = (
        checkpoint_path.with_name(f"{checkpoint_path.name}.slow.json")
        if checkpoint_path is not None
        else None
    )
    slow_pdf_ids = _load_pdf_history_manifest(slow_manifest_path)
    slow_pdf_ids.update(_load_slow_pdf_history_from_log(Path("/tmp/evh_instinct_import_fixed.out")))
    resume_failed_pdf = checkpoint.get("current_pdf_id") if checkpoint.get("last_error") else None
    resume_retry_attempts = int(checkpoint.get("retry_attempts") or 0)
    resume_cursor = (
        checkpoint.get("current_client_id"),
        checkpoint.get("current_patient_id"),
        checkpoint.get("current_pdf_id"),
    )
    resume_client_index = int(checkpoint.get("current_client_index") or 0)
    if not all(resume_cursor):
        resume_client_index = int(args.start_client_index)
    resume_patient_index = int(checkpoint.get("current_patient_index") or 0)
    resume_pdf_index = int(checkpoint.get("current_pdf_index") or 0)
    resume_reached = not all(resume_cursor)
    if checkpoint.get("last_error"):
        print(
            json.dumps(
                {
                    "status": "resuming_after_error",
                    "last_error": checkpoint.get("last_error"),
                    "current_client_id": checkpoint.get("current_client_id"),
                    "current_patient_id": checkpoint.get("current_patient_id"),
                    "current_pdf_id": checkpoint.get("current_pdf_id"),
                    "current_filename": checkpoint.get("current_filename"),
                    "retry_attempts": resume_retry_attempts,
                },
                                sort_keys=True,
            ),
            flush=True,
        )
    if not resume_reached:
        _vprint({
            "status": "resume_cursor",
            "current_client_id": resume_cursor[0],
            "current_patient_id": resume_cursor[1],
            "current_pdf_id": resume_cursor[2],
            "current_client_index": resume_client_index,
            "current_patient_index": resume_patient_index,
            "current_pdf_index": resume_pdf_index,
            "retry_attempts": resume_retry_attempts,
        })

    checkpoint_state = _load_checkpoint(checkpoint_path)
    progress_state: dict[str, Any] = {
        "clients_seen": int(checkpoint_state.get("client_seen_count") or 0),
        "patients_seen": int(checkpoint_state.get("patient_seen_count") or 0),
        "pdfs_seen": int(checkpoint_state.get("pdf_count") or 0),
        "current_client_name": checkpoint_state.get("current_client_name"),
        "current_patient_name": checkpoint_state.get("current_patient_name"),
        "current_pdf_name": checkpoint_state.get("current_filename"),
        "current_page_count": checkpoint_state.get("current_page_count"),
        "current_aux_stage": checkpoint_state.get("current_aux_stage"),
        "current_pdf_stage": checkpoint_state.get("current_pdf_stage"),
        "current_source_line": checkpoint_state.get("current_source_line"),
        "current_stage": "checkpoint_resume",
        "discovery_stage": "pending",
        "discovery_accounts_seen": 0,
        "discovery_patients_seen": 0,
        "eta": "unknown",
        "eta_seconds": None,
    }
    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.token = adapter.authenticate()
    # The chart-history helper reads the process-level TOKEN; keep it in sync
    # with the freshly authenticated adapter instead of reusing a stale token.
    os.environ["TOKEN"] = adapter.token
    _vprint({"status": "authenticated", "message": "Instinct token acquired"})
    term_index = load_term_index(Path(args.dictionary_csv) if args.dictionary_csv else None)
    config = ChunkingConfig(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    _vprint({
        "status": "discovery_cache",
        "message": "Loading or building client/patient discovery cache",
        "cache_path": str(_discovery_cache_path()),
    })
    _vprint({
        "status": "importing",
        "message": "Streaming live import with rolling ETA",
        "expected_clients": args.expected_clients,
    })
    discovery_cache_path = _discovery_cache_path()
    if not discovery_cache_path.exists():
        _vprint({
            "status": "discovery_cache_build",
            "message": "Building client/patient discovery cache once",
            "cache_path": str(discovery_cache_path),
        })
        discovery_cache = _build_discovery_cache(adapter, discovery_cache_path, progress_state)
    else:
        progress_state["discovery_stage"] = "loading_cache"
        discovery_cache = _load_discovery_cache(discovery_cache_path)
        if not discovery_cache.get("accounts") or not discovery_cache.get("patients_by_account"):
            print(
                json.dumps(
                    {
                        "status": "discovery_cache_refresh",
                        "message": "Refreshing incomplete client/patient discovery cache",
                        "cache_path": str(discovery_cache_path),
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
            discovery_cache = _build_discovery_cache(adapter, discovery_cache_path, progress_state)
    progress_state["discovery_stage"] = "ready"
    progress_state["current_stage"] = "preflight"
    progress_state["current_aux_stage"] = "z"
    progress_state["current_source_line"] = 1553
    print(
        "stage_map: 0=preflight z=size_known k=page_count_known 1=first_pdf 2=second_pdf 3=third_pdf A=ocr_1 B=ocr_2 C=ocr_3 l=load_complete b=checkpoint_write m=next_patient f=fetch_history c=client_preflight d=dispatch n=next_client",
        flush=True,
    )
    heartbeat = CountingHeartbeat(interval_s=10, state=progress_state)
    heartbeat.start()
    accounts = list(discovery_cache.get("accounts") or [])
    patients_by_account = discovery_cache.get("patients_by_account") or {}
    base_client_seen = int(checkpoint_state.get("client_seen_count") or 0)
    base_patient_seen = int(checkpoint_state.get("patient_seen_count") or 0)
    base_pdf_count = int(checkpoint_state.get("pdf_count") or 0)
    base_loaded_count = 0
    base_skipped_count = 0
    base_deferred_count = 0
    pdf_count = base_pdf_count
    loaded_count = base_loaded_count
    skipped_count = base_skipped_count
    deferred_count = base_deferred_count
    started_at = time.perf_counter()
    active_client_id: str | None = None
    active_client_started_at: float | None = None
    last_checkpointed_client_id: str | None = None
    completed_client_durations: list[float] = []
    recent_client_durations: deque[float] = deque(maxlen=5)
    processed_timestamps: deque[float] = deque()
    loaded_timestamps: deque[float] = deque()
    client_completion_timestamps: deque[float] = deque()
    ocr_count: int = 0
    ocr_succeeded_count: int = 0
    ocr_failed_count: int = 0
    defer_reason_counts: Counter[str] = Counter()
    counted_pdf_ids: set[str] = set()
    client_processed_pdf_cache: dict[str, set[str]] = {}
    seen_clients: set[str] = set()
    seen_patients: set[str] = set()

    checkpoint_context: dict[str, Any] = {
        "client_id": checkpoint_state.get("current_client_id"),
        "patient_id": checkpoint_state.get("current_patient_id"),
        "pdf_id": checkpoint_state.get("current_pdf_id"),
        "filename": checkpoint_state.get("current_filename"),
        "client_index": checkpoint_state.get("current_client_index"),
        "patient_index": checkpoint_state.get("current_patient_index"),
        "pdf_index": checkpoint_state.get("current_pdf_index"),
        "client_name": checkpoint_state.get("current_client_name"),
        "patient_name": checkpoint_state.get("current_patient_name"),
    }

    def client_seen_count_for(index: int | None = None) -> int:
        candidate = index if index is not None else checkpoint_context.get("client_index")
        if isinstance(candidate, int) and candidate >= 0:
            # account_index is the global traversal position, so it remains
            # correct when resuming from a checkpoint with an old counter.
            return candidate + 1
        return base_client_seen + len(seen_clients)

    def save_checkpoint(*, error: dict[str, Any] | None = None) -> None:
        progress_state["current_stage"] = "b"
        progress_state["current_aux_stage"] = "b"
        progress_state["current_source_line"] = 1612
        checkpoint_started_at = time.perf_counter()
        _write_checkpoint(
            checkpoint_path,
            _checkpoint_payload(
                client_id=checkpoint_context.get("client_id"),
                patient_id=checkpoint_context.get("patient_id"),
                pdf_id=checkpoint_context.get("pdf_id"),
                filename=checkpoint_context.get("filename"),
                loaded_count=loaded_count,
                skipped_count=skipped_count,
                deferred_count=deferred_count,
                pdf_count=pdf_count,
                total_pdf_count=loaded_count + skipped_count + deferred_count + ocr_count,
                retry_attempts=0,
                client_seen_count=client_seen_count_for(),
                patient_seen_count=base_patient_seen + len(seen_patients),
                client_index=checkpoint_context.get("client_index"),
                patient_index=checkpoint_context.get("patient_index"),
                pdf_index=checkpoint_context.get("pdf_index"),
                client_name=checkpoint_context.get("client_name"),
                patient_name=checkpoint_context.get("patient_name"),
                error=error,
            ),
        )
        print(
            json.dumps(
                {
                    "status": "checkpoint_write_complete",
                    "elapsed_seconds": round(time.perf_counter() - checkpoint_started_at, 3),
                    "client_id": checkpoint_context.get("client_id"),
                    "patient_id": checkpoint_context.get("patient_id"),
                    "pdf_id": checkpoint_context.get("pdf_id"),
                    "filename": checkpoint_context.get("filename"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        progress_state["current_aux_stage"] = None

    def save_checkpoint_on_shutdown() -> None:
        save_checkpoint()

    global _CHECKPOINT_SHUTDOWN_CALLBACK
    _CHECKPOINT_SHUTDOWN_CALLBACK = save_checkpoint_on_shutdown

    source_restart_count = 0
    while True:
        _vprint({
            "status": "loop_enter",
            "source_restart_count": source_restart_count,
            "clients_seen": client_seen_count_for(),
            "patients_seen": base_patient_seen + len(seen_patients),
            "pdfs_seen": pdf_count,
            "resume_reached": resume_reached,
            "current_stage": progress_state.get("current_stage"),
        })
        pass_pdf_start = pdf_count
        for account_index, patient_index, account, patient in iter_all_patients(
            discovery_cache,
            resume_client_index=resume_client_index if not resume_reached else 0,
            resume_patient_index=resume_patient_index if not resume_reached else 0,
        ):
            client_id = _text(account.get("id")) or ""
            patient_id = _text(patient.get("id")) or ""
            client_name = _text(account.get("name") or account.get("displayName") or account.get("businessName")) or client_id
            patient_name = _text(patient.get("name") or patient.get("patientName")) or patient_id
            if not client_id or not patient_id:
                continue
            if args.limit_clients and len(seen_clients) >= args.limit_clients:
                print(json.dumps({"status": "loop_break", "reason": "limit_clients", "clients_seen": client_seen_count_for(), "patients_seen": base_patient_seen + len(seen_patients), "pdfs_seen": pdf_count}, sort_keys=True), flush=True)
                break
            if args.limit_patients and len(seen_patients) >= args.limit_patients:
                print(json.dumps({"status": "loop_break", "reason": "limit_patients", "clients_seen": client_seen_count_for(), "patients_seen": base_patient_seen + len(seen_patients), "pdfs_seen": pdf_count}, sort_keys=True), flush=True)
                break
            if args.limit_pdfs and pdf_count >= args.limit_pdfs:
                print(json.dumps({"status": "loop_break", "reason": "limit_pdfs", "clients_seen": client_seen_count_for(), "patients_seen": base_patient_seen + len(seen_patients), "pdfs_seen": pdf_count}, sort_keys=True), flush=True)
                break
            if client_id not in seen_clients:
                seen_clients.add(client_id)
            if patient_id not in seen_patients:
                seen_patients.add(patient_id)
            progress_state["current_client_name"] = client_name
            progress_state["current_patient_name"] = patient_name
            progress_state["current_stage"] = "m"
            progress_state["current_source_line"] = 1698

            if not resume_reached:
                progress_state["current_source_line"] = 1699
                if (client_id, patient_id) == (resume_cursor[0], resume_cursor[1]):
                    progress_state["current_source_line"] = 1700
                    resume_reached = True
                else:
                    progress_state["current_source_line"] = 1701
                    continue

            if active_client_id != client_id:
                handoff_started_at = time.perf_counter()
                progress_state["current_source_line"] = 1702
                if active_client_id is not None and active_client_id != last_checkpointed_client_id:
                    progress_state["current_source_line"] = 1703
                    save_checkpoint()
                    progress_state["current_source_line"] = 1704
                    last_checkpointed_client_id = active_client_id
                if active_client_started_at is not None:
                    progress_state["current_source_line"] = 1705
                    completed_duration = time.perf_counter() - active_client_started_at
                    completed_client_durations.append(completed_duration)
                    recent_client_durations.append(completed_duration)
                active_client_id = client_id
                active_client_started_at = time.perf_counter()
                progress_state["current_stage"] = "m"
                progress_state["current_source_line"] = 1706
                print(
                    json.dumps(
                        {
                            "status": "client_handoff_complete",
                            "elapsed_seconds": round(time.perf_counter() - handoff_started_at, 3),
                            "client_id": client_id,
                            "patient_id": patient_id,
                            "client_name": client_name,
                            "patient_name": patient_name,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            checkpoint_context.update(
                {
                    "client_id": client_id,
                    "patient_id": patient_id,
                    "client_index": account_index,
                    "patient_index": patient_index,
                    "client_name": client_name,
                    "patient_name": patient_name,
                }
            )
            progress_state["current_source_line"] = 1707

            history_started_at = time.perf_counter()
            progress_state["current_stage"] = "f"
            progress_state["current_source_line"] = 1744
            charts = _chart_files_for_patient(
                patient_id,
                timeout_s=args.history_timeout,
                max_attempts=args.history_attempts,
                retry_delay_s=args.history_retry_delay,
                progress_state=progress_state,
            )
            print(
                json.dumps(
                    {
                        "status": "history_fetch_complete",
                        "elapsed_seconds": round(time.perf_counter() - history_started_at, 3),
                        "client_id": client_id,
                        "patient_id": patient_id,
                        "chart_count": len(charts),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            charts = sorted(charts, key=lambda chart: int(_text(chart.get("id")) or 0))
            client_pdf_ids = [pdf_id for pdf_id in (_text(chart.get("id")) or "" for chart in charts) if pdf_id]
            if client_id not in client_processed_pdf_cache:
                preflight_started_at = time.perf_counter()
                client_processed_pdf_cache[client_id] = fetch_processed_pdf_ids(
                    args.database_url,
                    args.source_document_table_name,
                    args.table_name,
                    client_pdf_ids,
                )
                print(
                    json.dumps(
                        {
                            "status": "client_preflight_existing_ids",
                            "client_id": client_id,
                            "client_name": client_name,
                            "client_index": account_index,
                            "pdf_count": len(client_pdf_ids),
                            "existing_pdf_count": len(client_processed_pdf_cache[client_id]),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                print(
                    json.dumps(
                        {
                            "status": "preflight_lookup_complete",
                            "elapsed_seconds": round(time.perf_counter() - preflight_started_at, 3),
                            "client_id": client_id,
                            "pdf_count": len(client_pdf_ids),
                            "existing_pdf_count": len(client_processed_pdf_cache[client_id]),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            client_processed_pdf_ids = client_processed_pdf_cache[client_id]
            client_work_items: list[PdfWorkItem] = []
            for pdf_index, chart in enumerate(charts):
                pdf_id = _text(chart.get("id")) or ""
                filename = _text(chart.get("filename")) or f"{pdf_id}.pdf"
                if not pdf_id:
                    continue
                if resume_reached and pdf_index < resume_pdf_index and client_id == resume_cursor[0] and patient_id == resume_cursor[1]:
                    continue

                progress_state["current_pdf_name"] = filename
                progress_state["current_pdf_size"] = _current_pdf_size_bytes(
                    pdf_id,
                    pdf_storage_dir,
                    deferred_pdf_dir,
                    processed_pdf_dir,
                )
                progress_state["current_stage"] = "c"
                progress_state["current_aux_stage"] = "z" if progress_state["current_pdf_size"] is not None else None
                progress_state["current_source_line"] = 1818
                checkpoint_context.update(
                    {
                        "pdf_id": pdf_id,
                        "filename": filename,
                        "pdf_index": pdf_index,
                    }
                )

                if pdf_id in processed or pdf_id in skipped_pdf_ids or pdf_id in slow_pdf_ids:
                    progress_state["current_stage"] = "s"
                    progress_state["current_aux_stage"] = "k"
                    pdf_count += 1
                    processed.add(pdf_id)
                    skipped_count += 1
                    if pdf_id in slow_pdf_ids:
                        _remember_pdf_history(slow_manifest_path, slow_pdf_ids, pdf_id)
                    _record_skipped_pdf_best_effort(
                        database_url=args.database_url,
                        deferred_ocr_table_name=args.deferred_ocr_table_name,
                        source_name=f"{client_id}:{patient_id}:{filename}",
                        source_uri=str(pdf_storage_dir / _stable_pdf_filename(pdf_id)),
                        client_id=client_id,
                        patient_id=patient_id,
                        patient_name=patient_name,
                        pdf_id=pdf_id,
                        filename=filename,
                        page_count=None,
                        metadata={"status": "skipped_already_loaded", "reason": "resume_guard"},
                    )
                    progress_state["clients_seen"] = client_seen_count_for()
                    progress_state["patients_seen"] = base_patient_seen + len(seen_patients)
                    progress_state["pdfs_seen"] = pdf_count
                    _print_progress(ImportProgress(client_id, patient_id, pdf_id, filename, "skipped_already_loaded"))
                    continue

                document_key = (client_id, patient_id, pdf_id)
                if document_key in seen_document_keys:
                    progress_state["current_stage"] = "s"
                    progress_state["current_aux_stage"] = "k"
                    pdf_count += 1
                    print(
                        json.dumps(
                            {
                                "status": "already_seen_this_run",
                                "client_id": client_id,
                                "patient_id": patient_id,
                                "pdf_id": pdf_id,
                                "filename": filename,
                                "action": "skip_before_signed_url",
                            },
                                                        sort_keys=True,
                        ),
                        flush=True,
                    )
                    progress_state["clients_seen"] = client_seen_count_for()
                    progress_state["patients_seen"] = base_patient_seen + len(seen_patients)
                    progress_state["pdfs_seen"] = pdf_count
                    _print_progress(ImportProgress(client_id, patient_id, pdf_id, filename, "skipped_already_loaded"))
                    continue
                seen_document_keys.add(document_key)

                # Salvage completed work even when the local checkpoint is
                # stale or was rebuilt: the Instinct PDF ID is the durable
                # external identity in PostgreSQL metadata.
                if pdf_id in client_processed_pdf_ids:
                    progress_state["current_stage"] = "s"
                    progress_state["current_aux_stage"] = "k"
                    pdf_count += 1
                    processed.add(pdf_id)
                    skipped_count += 1
                    _remember_pdf_history(slow_manifest_path, slow_pdf_ids, pdf_id)
                    _record_skipped_pdf_best_effort(
                        database_url=args.database_url,
                        deferred_ocr_table_name=args.deferred_ocr_table_name,
                        source_name=f"{client_id}:{patient_id}:{filename}",
                        source_uri=str(pdf_storage_dir / _stable_pdf_filename(pdf_id)),
                        client_id=client_id,
                        patient_id=patient_id,
                        patient_name=patient_name,
                        pdf_id=pdf_id,
                        filename=filename,
                        page_count=None,
                        metadata={"status": "skipped_already_loaded", "reason": "client_preflight_existing_ids"},
                    )
                    progress_state["clients_seen"] = client_seen_count_for()
                    progress_state["patients_seen"] = base_patient_seen + len(seen_patients)
                    progress_state["pdfs_seen"] = pdf_count
                    _print_progress(ImportProgress(client_id, patient_id, pdf_id, filename, "skipped_already_loaded"))
                    continue

                client_work_items.append(
                    PdfWorkItem(
                        client_id=client_id,
                        client_name=client_name,
                        patient_id=patient_id,
                        patient_name=patient_name,
                        pdf_id=pdf_id,
                        filename=filename,
                        source_uri=str(pdf_storage_dir / _stable_pdf_filename(pdf_id)),
                        pdf_path=pdf_storage_dir / _stable_pdf_filename(pdf_id),
                        client_index=account_index,
                        patient_index=patient_index,
                        pdf_index=pdf_index,
                    )
                )
                selected_pdf_path = pdf_storage_dir / _stable_pdf_filename(pdf_id)
                progress_state["current_pdf"] = filename
                progress_state["current_pdf_size"] = selected_pdf_path.stat().st_size if selected_pdf_path.is_file() else None
                progress_state["current_stage"] = "d"
                progress_state["current_aux_stage"] = "k"
                progress_state["current_source_line"] = 1926
                continue
            if not client_work_items:
                continue
            progress_state["current_stage"] = "w"
            progress_state["current_source_line"] = 1931
            worker_count = max(1, min(args.client_pdf_workers, len(client_work_items)))
            progress_state["current_source_line"] = 1932
            print(
                json.dumps(
                    {
                        "status": "client_parallel_start",
                        "client_id": client_id,
                        "client_name": client_name,
                        "client_index": account_index,
                        "pdf_count": len(client_work_items),
                        "worker_count": worker_count,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            progress_state["current_source_line"] = 1933
            client_batch_started_at = time.perf_counter()
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="rd-client-pdf") as client_pool:
                progress_state["current_source_line"] = 1934
                future_map = {
                    client_pool.submit(
                        _process_pdf_work_item,
                        work_item,
                        progress_state=progress_state,
                        database_url=args.database_url,
                        table_name=args.table_name,
                        source_document_table_name=args.source_document_table_name,
                        embedding_model=args.embedding_model,
                        vector_dimensions=args.vector_dimensions,
                        embedding_batch_size=args.embedding_batch_size,
                        load_batch_size=args.load_batch_size,
                        extraction_timeout=args.extraction_timeout,
                        page_workers=args.page_workers,
                        term_index=term_index,
                        chunk_size=args.chunk_size,
                        chunk_overlap=args.chunk_overlap,
                        deferred_pdf_dir=deferred_pdf_dir,
                        processed_pdf_dir=processed_pdf_dir,
                    ): work_item
                    for work_item in client_work_items
                }
                progress_state["current_source_line"] = 1935
                for future in as_completed(future_map):
                    progress_state["current_source_line"] = 1936
                    work_item = future_map[future]
                    try:
                        progress_state["current_source_line"] = 1937
                        result = future.result()
                        _record_timing_extractor_wins(result.timing)
                    except NoTextLayerError as exc:
                        progress_state["current_source_line"] = 1938
                        ocr_count += 1
                        result = PdfWorkResult(
                            client_id=work_item.client_id,
                            client_name=work_item.client_name,
                            patient_id=work_item.patient_id,
                            patient_name=work_item.patient_name,
                            pdf_id=work_item.pdf_id,
                            filename=work_item.filename,
                            client_index=work_item.client_index,
                            patient_index=work_item.patient_index,
                            pdf_index=work_item.pdf_index,
                            status="ocr_needed",
                            page_count=getattr(exc, "page_count", None),
                            chunk_count=0,
                            detail=str(exc),
                        )
                    except DeferredOCRDocument as exc:
                        progress_state["current_source_line"] = 1939
                        ocr_count += 1
                        result = PdfWorkResult(
                            client_id=work_item.client_id,
                            client_name=work_item.client_name,
                            patient_id=work_item.patient_id,
                            patient_name=work_item.patient_name,
                            pdf_id=work_item.pdf_id,
                            filename=work_item.filename,
                            client_index=work_item.client_index,
                            patient_index=work_item.patient_index,
                            pdf_index=work_item.pdf_index,
                            status="ocr_needed",
                            page_count=getattr(exc, "page_count", None),
                            chunk_count=0,
                            detail=getattr(exc, "reason", str(exc)),
                        )
                    except Exception as exc:
                        progress_state["current_source_line"] = 1940
                        if not _is_non_retryable_infrastructure_error(exc):
                            ocr_bucket = _defer_reason_bucket(str(exc)) == "no_text_layer"
                            if ocr_bucket:
                                ocr_count += 1
                            final_status = "ocr_needed" if ocr_bucket else "ocr_not_reached_deferred"
                            result = PdfWorkResult(
                                client_id=work_item.client_id,
                                client_name=work_item.client_name,
                                patient_id=work_item.patient_id,
                                patient_name=work_item.patient_name,
                                pdf_id=work_item.pdf_id,
                                filename=work_item.filename,
                                client_index=work_item.client_index,
                                patient_index=work_item.patient_index,
                                pdf_index=work_item.pdf_index,
                                status=final_status,
                                detail=str(exc),
                            )
                            _record_timing_extractor_wins(result.timing)
                        else:
                            print(
                                json.dumps(
                                    {
                                        "status": "client_parallel_failed",
                                        "client_id": work_item.client_id,
                                        "patient_id": work_item.patient_id,
                                        "pdf_id": work_item.pdf_id,
                                        "filename": work_item.filename,
                                        "error_type": type(exc).__name__,
                                        "error": str(exc),
                                    },
                                    sort_keys=True,
                                ),
                                flush=True,
                            )
                            raise
                    pdf_count += 1
                    processed_timestamps.append(time.perf_counter())
                    progress_state["clients_seen"] = client_seen_count_for()
                    progress_state["patients_seen"] = base_patient_seen + len(seen_patients)
                    progress_state["pdfs_seen"] = pdf_count
                    now = time.perf_counter()
                    while processed_timestamps and now - processed_timestamps[0] > 3600:
                        processed_timestamps.popleft()
                    while client_completion_timestamps and now - client_completion_timestamps[0] > 3600:
                        client_completion_timestamps.popleft()
                    recent_window_seconds = now - processed_timestamps[0] if processed_timestamps else 0.0
                    recent_window_count = len(processed_timestamps)
                    recent_client_window_seconds = now - client_completion_timestamps[0] if client_completion_timestamps else 0.0
                    recent_client_window_count = len(client_completion_timestamps)
                    elapsed = max(time.perf_counter() - started_at, 0.001)
                    client_count = client_seen_count_for()
                    patient_count = base_patient_seen + len(seen_patients)
                    if recent_client_window_count > 0 and recent_client_window_seconds > 0.0 and args.expected_clients > 0:
                        client_rate_per_second = recent_client_window_count / recent_client_window_seconds
                        remaining_client_count = max(args.expected_clients - client_seen_count_for(), 0)
                        eta_seconds = remaining_client_count / client_rate_per_second if client_rate_per_second > 0 else None
                        if eta_seconds is not None:
                            progress_state["eta_seconds"] = int(round(eta_seconds))
                            progress_state["eta"] = _format_eta(eta_seconds)
                        else:
                            progress_state["eta_seconds"] = None
                            progress_state["eta"] = "unknown"
                    else:
                        progress_state["eta_seconds"] = None
                        progress_state["eta"] = "unknown"

                    checkpoint_context.update(
                        {
                            "client_id": result.client_id,
                            "patient_id": result.patient_id,
                            "pdf_id": result.pdf_id,
                            "filename": result.filename,
                            "client_index": result.client_index,
                            "patient_index": result.patient_index,
                            "pdf_index": result.pdf_index,
                            "client_name": result.client_name,
                            "patient_name": result.patient_name,
                        }
                    )
                    if result.pdf_id in counted_pdf_ids:
                        continue
                    counted_pdf_ids.add(result.pdf_id)
                    if result.status == "loaded":
                        progress_state["current_stage"] = "w"
                        progress_state["current_pdf_stage"] = None
                        progress_state["current_aux_stage"] = "l"
                        loaded_count += 1
                        if result.timing and result.timing.get("ocr_used"):
                            ocr_succeeded_count += 1
                        processed.add(result.pdf_id)
                        loaded_timestamps.append(time.perf_counter())
                        progress_state["current_stage"] = "load_complete"
                        progress_state["current_source_line"] = 2101
                        print(f"    loaded into Aurora/Postgres; source_pdf_retained={result.pdf_id}", flush=True)
                        _print_progress(
                            ImportProgress(
                                result.client_id,
                                result.patient_id,
                                result.pdf_id,
                                result.filename,
                                "loaded",
                                page_count=result.page_count,
                                chunk_count=result.chunk_count,
                            )
                        )
                        progress_state["current_stage"] = "m"
                        progress_state["current_source_line"] = 1698
                        progress_state["current_aux_stage"] = None
                    else:
                        progress_state["current_stage"] = "w"
                        progress_state["current_pdf_stage"] = None
                        progress_state["current_aux_stage"] = "l"
                        progress_state["current_source_line"] = 2118
                        if result.status == "ocr_needed":
                            ocr_count += 1
                            if result.timing and result.timing.get("ocr_used"):
                                ocr_failed_count += 1
                        else:
                            skipped_count += 1
                            deferred_count += 1
                            if result.timing and result.timing.get("ocr_used"):
                                ocr_failed_count += 1
                        defer_reason = (result.detail or result.status or "unknown").strip()
                        defer_reason_counts[defer_reason] += 1
                        processed.add(result.pdf_id)
                        if result.status in {"ocr_needed", "ocr_not_reached_deferred", "deferred"}:
                            _record_deferred_ocr_best_effort(
                                database_url=args.database_url,
                                deferred_ocr_table_name=args.deferred_ocr_table_name,
                                source_name=f"{result.client_id}:{result.patient_id}:{result.filename}",
                                source_uri=str(pdf_storage_dir / _stable_pdf_filename(result.pdf_id)),
                                patient_id=result.patient_id,
                                patient_name=result.patient_name,
                                pdf_id=result.pdf_id,
                                filename=result.filename,
                                page_count=result.page_count,
                                reason=result.detail or result.status,
                                metadata={
                                    "status": result.status,
                                    "detail": result.detail,
                                    "client_id": result.client_id,
                                    "client_name": result.client_name,
                                    "patient_id": result.patient_id,
                                    "patient_name": result.patient_name,
                                    "pdf_id": result.pdf_id,
                                    "filename": result.filename,
                                },
                            )
                        if result.status != "ocr_needed":
                            _move_pdf_to_deferred_dir(pdf_storage_dir / _stable_pdf_filename(result.pdf_id), deferred_pdf_dir)
                            _remember_skipped_pdf(skipped_manifest_path, skipped_pdf_ids, result.pdf_id)
                            _remember_pdf_history(slow_manifest_path, slow_pdf_ids, result.pdf_id)
                        _print_progress(
                            ImportProgress(
                                result.client_id,
                                result.patient_id,
                                result.pdf_id,
                                result.filename,
                                result.status,
                                page_count=result.page_count,
                                chunk_count=result.chunk_count,
                                detail=result.detail,
                            )
                        )
                        progress_state["current_stage"] = "m"
                        progress_state["current_source_line"] = 1698
                        progress_state["current_aux_stage"] = None
                    _write_checkpoint(
                        checkpoint_path,
                        _checkpoint_payload(
                            client_id=checkpoint_context.get("client_id"),
                            patient_id=checkpoint_context.get("patient_id"),
                            pdf_id=checkpoint_context.get("pdf_id"),
                            filename=checkpoint_context.get("filename"),
                            loaded_count=loaded_count,
                            skipped_count=skipped_count,
                            deferred_count=deferred_count,
                            pdf_count=pdf_count,
                            total_pdf_count=loaded_count + skipped_count + deferred_count + ocr_count,
                            retry_attempts=0,
                            client_seen_count=client_seen_count_for(),
                            patient_seen_count=base_patient_seen + len(seen_patients),
                            client_index=checkpoint_context.get("client_index"),
                            patient_index=checkpoint_context.get("patient_index"),
                            pdf_index=checkpoint_context.get("pdf_index"),
                            client_name=checkpoint_context.get("client_name"),
                            patient_name=checkpoint_context.get("patient_name"),
                        ),
                    )
                    progress_line = (
                        f"[client {client_count}/~{args.expected_clients}] "
                        f"[patient {patient_count}] "
                        f"[file {pdf_count}] {result.filename} "
                        f"| loaded={loaded_count} deferred={deferred_count} ocr_needed={ocr_count} skipped_already_loaded={skipped_count} "
                        f"ocr_succeeded={ocr_succeeded_count} ocr_failed={ocr_failed_count} "
                        f"| pdfs/hr={_format_throughput_per_hour(recent_window_count, recent_window_seconds)} "
                        f"| clients/hr={_format_throughput_per_hour(recent_client_window_count, recent_client_window_seconds)} "
                        f"| elapsed={_format_eta(elapsed)} eta={progress_state['eta']}"
                    )
                    if defer_reason_counts:
                        defer_reasons = ", ".join(
                            f"{name}:{count}" for name, count in defer_reason_counts.most_common()
                        )
                        progress_line += f" ocr_reasons={defer_reasons}"
                    if sys.stdout.isatty():
                        progress_line = f"\x1b[1m\x1b[36m{progress_line}\x1b[0m"
                    print(progress_line, flush=True)
                    print(_extractor_usage_line(), flush=True)
                    print(flush=True)
            client_batch_elapsed = time.perf_counter() - client_batch_started_at
            if VERBOSE_LOGGING:
                print(
                    f"[client_done] {client_id} {account_index} {client_name} "
                    f"pdfs={len(client_work_items)} workers={worker_count} "
                    f"elapsed={client_batch_elapsed:.3f}s loaded={loaded_count} "
                    f"skipped_already_loaded={skipped_count} deferred={deferred_count} ocr_needed={ocr_count} "
                    f"ocr_succeeded={ocr_succeeded_count} ocr_failed={ocr_failed_count} total={loaded_count + deferred_count + ocr_count}",
                    flush=True,
                )
            client_completion_timestamps.append(time.perf_counter())
            completed_client_durations.append(time.perf_counter() - active_client_started_at if active_client_started_at is not None else 0.0)
            recent_client_durations.append(completed_client_durations[-1])
            client_work_items = []
            continue

        # Durability boundary: a client is checkpointed only after its yielded
        # patients and PDFs have been handled.  Per-PDF success state remains
        # in memory until this boundary; OCR-needed and retry-critical
        # failures still save immediately above.
        if active_client_id is not None and active_client_id != last_checkpointed_client_id:
            save_checkpoint()
            last_checkpointed_client_id = active_client_id

        if args.limit_clients or args.limit_patients or args.limit_pdfs:
            print(
                json.dumps(
                    {
                        "status": "loop_exit",
                        "reason": "limit_reached",
                        "clients_seen": client_seen_count_for(),
                        "patients_seen": base_patient_seen + len(seen_patients),
                        "pdfs_seen": pdf_count,
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
            break
        new_pdfs_this_pass = pdf_count - pass_pdf_start
        if new_pdfs_this_pass <= 0:
            print(
                json.dumps(
                    {
                        "status": "source_end",
                        "message": "Live source pass ended with no new PDFs; stopping.",
                        "restart_count": source_restart_count,
                        "clients_seen": client_seen_count_for(),
                        "patients_seen": base_patient_seen + len(seen_patients),
                        "pdfs_seen": pdf_count,
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
            print(
                json.dumps(
                    {
                        "status": "loop_exit",
                        "reason": "source_end_no_new_pdfs",
                        "clients_seen": client_seen_count_for(),
                        "patients_seen": base_patient_seen + len(seen_patients),
                        "pdfs_seen": pdf_count,
                    },
                                        sort_keys=True,
                ),
                flush=True,
            )
            break
        source_restart_count += 1
        print(
            json.dumps(
                {
                    "status": "source_restart",
                    "message": "Live source pass ended; restarting traversal to keep going.",
                    "restart_count": source_restart_count,
                    "clients_seen": client_seen_count_for(),
                    "patients_seen": base_patient_seen + len(seen_patients),
                    "pdfs_seen": pdf_count,
                    "new_pdfs_this_pass": new_pdfs_this_pass,
                },
                                sort_keys=True,
            ),
            flush=True,
        )
        adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
        adapter.token = adapter.authenticate()
        os.environ["TOKEN"] = adapter.token
    heartbeat.stop()

    print(
        json.dumps(
            {
                "status": "complete",
                "clients_seen": client_seen_count_for(),
                "patients_seen": base_patient_seen + len(seen_patients),
                "pdfs_seen": pdf_count,
                "loaded": loaded_count,
                "skipped": skipped_count,
                "checkpoint": str(checkpoint_path) if checkpoint_path else None,
                "embedding_model": args.embedding_model,
                "vector_dimensions": args.vector_dimensions,
                "eta": progress_state.get("eta"),
            },
                        sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
