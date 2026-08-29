"""Run the full live Instinct PDF import with loud progress output.

This walks:
- clients/accounts
- patients for each client
- chart files for each patient
- downloads each PDF one at a time
- OCRs image-only PDFs through the chunker fallback
- chunks and embeds with a real OpenAI embedding model
- loads chunks into Aurora Postgres/pgvector
- optionally deletes the local PDF after a successful load

The script prints a progress line for every significant step so long runs stay
visible and resumable by checkpoint file if needed.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Iterable
from multiprocessing import get_context

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TRACE_FUNCTION_CALLS = os.environ.get("EVH_IMPORT_TRACE_CALLS", "").strip().lower() in {"1", "true", "yes", "on"}

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_pdf_chunker import (
    ChunkingConfig,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_DEFERRED_OCR_TABLE_NAME,
    DeferredOCRDocument,
    NoTextLayerError,
    PatientPdfSource,
    build_deferred_ocr_upsert_sql,
    chunk_patient_pdf_timed,
    load_into_postgres,
    load_term_index,
    run_psql,
)
from scripts.instinct_pdf_family_sampler import create_chart_file_url, fetch_medical_history_visits


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
                    indent=2,
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
                        indent=2,
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
                    indent=2,
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


class PatientHistoryTimeout(TimeoutError):
    pass


def _patient_history_worker(patient_id: str, queue) -> None:
    try:
        from scripts.instinct_pdf_family_sampler import fetch_medical_history_visits

        payload = fetch_medical_history_visits(patient_id)
        queue.put(("ok", payload))
    except Exception as exc:  # pragma: no cover - child process
        queue.put(
            (
                "err",
                {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
        )


@contextmanager
def _deadline(seconds: int):
    """Interrupt a blocking call on Linux when it exceeds the deadline."""
    if seconds <= 0:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("_deadline must run in the main thread")

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(signum, frame):
        raise PatientHistoryTimeout(f"operation exceeded {seconds} seconds")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


@trace_calls
def _chart_files_for_patient(
    patient_id: str,
    *,
    timeout_s: int = 5,
    max_attempts: int = 3,
    retry_delay_s: float = 5.0,
) -> list[dict[str, Any]]:
    print(
        json.dumps(
            {
                "status": "patient_history_fetch_start",
                "patient_id": patient_id,
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    fetch_started = time.perf_counter()
    history = None
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        attempt_started = time.perf_counter()
        print(
            json.dumps(
                {
                    "status": "patient_history_fetch_attempt",
                    "patient_id": patient_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "timeout_seconds": timeout_s,
                },
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
        try:
            ctx = get_context("spawn")
            queue = ctx.Queue()
            proc = ctx.Process(target=_patient_history_worker, args=(patient_id, queue), daemon=True)
            proc.start()
            proc.join(timeout_s)
            if proc.is_alive():
                proc.terminate()
                proc.join(10)
                if proc.is_alive():
                    proc.kill()
                    proc.join(5)
                raise PatientHistoryTimeout(f"operation exceeded {timeout_s} seconds")
            if queue.empty():
                raise RuntimeError("patient-history worker returned no payload")
            status, payload = queue.get()
            if status != "ok":
                raise RuntimeError(
                    f"patient-history worker failed: {payload.get('error_type')}: {payload.get('error')}"
                )
            history = payload
            break
        except PatientHistoryTimeout as exc:
            last_exc = exc
            print(
                json.dumps(
                    {
                        "status": "patient_history_fetch_timeout",
                        "patient_id": patient_id,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "attempt_elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "timeout_seconds": timeout_s,
                        "will_retry": attempt < max_attempts,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                flush=True,
            )
            if attempt < max_attempts:
                time.sleep(retry_delay_s)
        except Exception as exc:
            last_exc = exc
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
                    indent=2,
                    sort_keys=True,
                ),
                flush=True,
            )
            if attempt < max_attempts:
                time.sleep(retry_delay_s)

    if history is None:
        elapsed = time.perf_counter() - fetch_started
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
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
        return []

    patient_block = history.get("patient") if isinstance(history, dict) else None
    charts_block = history.get("charts") if isinstance(history, dict) else None
    chart_count = len(charts_block) if isinstance(charts_block, list) else None
    chart_type_counts: dict[str, int] = {}
    if isinstance(charts_block, list):
        for chart in charts_block:
            if isinstance(chart, dict):
                chart_type = _text(chart.get("__typename")) or "unknown"
                chart_type_counts[chart_type] = chart_type_counts.get(chart_type, 0) + 1

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
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )

    charts = history.get("charts") or []
    results: list[dict[str, Any]] = []
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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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
            indent=2,
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
                indent=2,
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
            indent=2,
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


@trace_calls
def _write_checkpoint(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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
                indent=2,
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
                indent=2,
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
            elapsed = time.time() - last_progress
            if not saw_startup and elapsed > startup_deadline_s:
                proc.terminate()
                time.sleep(5)
                if proc.poll() is None:
                    proc.kill()
                break
            if saw_startup and elapsed > silence_deadline_s:
                proc.terminate()
                time.sleep(5)
                if proc.poll() is None:
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
            stop_event.set()
            monitor_thread.join(timeout=10)
            return 0
        if same_failure_count >= max_same_failures:
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
    processed_pdf_ids: set[str],
    client_id: str | None = None,
    patient_id: str | None = None,
    pdf_id: str | None = None,
    filename: str | None = None,
    loaded_count: int = 0,
    skipped_count: int = 0,
    pdf_count: int = 0,
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
        "processed_pdf_ids": sorted(processed_pdf_ids),
        "loaded_count": loaded_count,
        "skipped_count": skipped_count,
        "pdf_count": pdf_count,
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
        json.dumps(asdict(item), indent=2, sort_keys=True),
        flush=True,
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
                patient_id=patient_id,
                patient_name=patient_name,
                pdf_id=pdf_id,
                filename=filename,
                page_count=page_count,
                reason=reason,
                metadata=metadata,
            ),
        )
        return None
    except Exception as exc:  # pragma: no cover - best-effort durability path
        return {
            "stage": "deferred_ocr_record_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


@trace_calls
def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "unknown"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


@trace_calls
def _print_stage(stage: str, **fields: Any) -> None:
    payload = {"stage": stage, **fields}
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)


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
        print(json.dumps({"status": "client_start", "client_id": client_id, "client_name": client_name}, indent=2), flush=True)
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
                    indent=2,
                ),
                flush=True,
            )
            yield account_index, patient_index, account, patient


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

    def _run(self) -> None:
        tick = 0
        while not self._stop.wait(self.interval_s):
            tick += 1
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
                        "current_stage": self.state.get("current_stage"),
                        "discovery_stage": self.state.get("discovery_stage"),
                        "discovery_accounts_seen": self.state.get("discovery_accounts_seen", 0),
                        "discovery_patients_seen": self.state.get("discovery_patients_seen", 0),
                        "eta": self.state.get("eta", "unknown"),
                        "eta_seconds": self.state.get("eta_seconds"),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                flush=True,
            )


@trace_calls
def main(argv: list[str] | None = None) -> int:
    _install_crash_beacon()
    parser = argparse.ArgumentParser(description="Run the full Instinct PDF ingest with progress output.")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--database-url", default=os.environ.get("EVH_PGDATABASE_URL", ""))
    parser.add_argument("--output-dir", default="/tmp/evh_instinct_import")
    parser.add_argument("--checkpoint", default="/tmp/evh_instinct_import.checkpoint.json")
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--vector-dimensions", type=int, default=DEFAULT_EMBEDDING_DIMENSIONS)
    parser.add_argument("--embedding-batch-size", type=int, default=64, help="Batch size for embedding API requests.")
    parser.add_argument("--load-batch-size", type=int, default=500, help="Batch size for pgvector upserts.")
    parser.add_argument("--extraction-timeout", type=int, default=45, help="Seconds before PDF text extraction is deferred.")
    parser.add_argument("--delete-local-after-load", action="store_true", default=True)
    parser.add_argument("--keep-local", action="store_true")
    parser.add_argument("--expected-clients", type=int, default=12053, help="Expected live client/account total for ETA math.")
    parser.add_argument("--dictionary-csv", default="")
    parser.add_argument("--table-name", default="pms_page_chunk")
    parser.add_argument("--source-document-table-name", default="rag_source_document")
    parser.add_argument("--deferred-ocr-table-name", default=DEFAULT_DEFERRED_OCR_TABLE_NAME)
    parser.add_argument("--limit-clients", type=int, default=0, help="Optional cap for testing.")
    parser.add_argument("--limit-patients", type=int, default=0, help="Optional cap for testing.")
    parser.add_argument("--limit-pdfs", type=int, default=0, help="Optional cap for testing.")
    parser.add_argument("--history-timeout", type=int, default=5, help="Seconds before a patient history request is interrupted.")
    parser.add_argument("--history-attempts", type=int, default=3, help="Total attempts per patient history request.")
    parser.add_argument("--history-retry-delay", type=float, default=5.0, help="Seconds between patient history attempts.")
    args = parser.parse_args(argv)

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials: set INSTINCT_CLIENT_ID/SECRET or pass --username/--password.")
    if not args.database_url:
        raise SystemExit("Missing --database-url or EVH_PGDATABASE_URL.")

    print(
        json.dumps(
            {
                "status": "starting",
                "message": "Booting full Instinct import runner",
                "embedding_model": args.embedding_model,
                "vector_dimensions": args.vector_dimensions,
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else None
    checkpoint = _load_checkpoint(checkpoint_path)
    processed = set(checkpoint.get("processed_pdf_ids") or [])
    resume_failed_pdf = checkpoint.get("current_pdf_id") if checkpoint.get("last_error") else None
    resume_retry_attempts = int(checkpoint.get("retry_attempts") or 0)
    resume_cursor = (
        checkpoint.get("current_client_id"),
        checkpoint.get("current_patient_id"),
        checkpoint.get("current_pdf_id"),
    )
    resume_client_index = int(checkpoint.get("current_client_index") or 0)
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
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
    if not resume_reached:
        print(
            json.dumps(
                {
                    "status": "resume_cursor",
                    "current_client_id": resume_cursor[0],
                    "current_patient_id": resume_cursor[1],
                    "current_pdf_id": resume_cursor[2],
                    "current_client_index": resume_client_index,
                    "current_patient_index": resume_patient_index,
                    "current_pdf_index": resume_pdf_index,
                    "retry_attempts": resume_retry_attempts,
                },
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )

    checkpoint_state = _load_checkpoint(checkpoint_path)
    progress_state: dict[str, Any] = {
        "clients_seen": int(checkpoint_state.get("client_seen_count") or 0),
        "patients_seen": int(checkpoint_state.get("patient_seen_count") or 0),
        "pdfs_seen": int(checkpoint_state.get("pdf_count") or 0),
        "current_client_name": checkpoint_state.get("current_client_name"),
        "current_patient_name": checkpoint_state.get("current_patient_name"),
        "current_pdf_name": checkpoint_state.get("current_filename"),
        "current_stage": "checkpoint_resume",
        "discovery_stage": "pending",
        "discovery_accounts_seen": 0,
        "discovery_patients_seen": 0,
        "eta": "unknown",
        "eta_seconds": None,
    }
    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.token = adapter.authenticate()
    print(json.dumps({"status": "authenticated", "message": "Instinct token acquired"}, indent=2, sort_keys=True), flush=True)
    term_index = load_term_index(Path(args.dictionary_csv) if args.dictionary_csv else None)
    config = ChunkingConfig(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print(
        json.dumps(
            {
                "status": "discovery_cache",
                "message": "Loading or building client/patient discovery cache",
                "cache_path": str(_discovery_cache_path()),
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    print(
        json.dumps(
            {
                "status": "importing",
                "message": "Streaming live import with rolling ETA",
                "expected_clients": args.expected_clients,
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    discovery_cache_path = _discovery_cache_path()
    if not discovery_cache_path.exists():
        print(
            json.dumps(
                {
                    "status": "discovery_cache_build",
                    "message": "Building client/patient discovery cache once",
                    "cache_path": str(discovery_cache_path),
                },
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
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
                    indent=2,
                    sort_keys=True,
                ),
                flush=True,
            )
            discovery_cache = _build_discovery_cache(adapter, discovery_cache_path, progress_state)
    progress_state["discovery_stage"] = "ready"
    progress_state["current_stage"] = "ready_for_import"
    heartbeat = CountingHeartbeat(interval_s=10, state=progress_state)
    heartbeat.start()
    base_client_seen = int(checkpoint_state.get("client_seen_count") or 0)
    base_patient_seen = int(checkpoint_state.get("patient_seen_count") or 0)
    base_pdf_count = int(checkpoint_state.get("pdf_count") or 0)
    base_loaded_count = int(checkpoint_state.get("loaded_count") or 0)
    base_skipped_count = int(checkpoint_state.get("skipped_count") or 0)
    pdf_count = base_pdf_count
    loaded_count = base_loaded_count
    skipped_count = base_skipped_count
    started_at = time.perf_counter()
    estimated_total_pdfs = None
    seen_clients: set[str] = set()
    seen_patients: set[str] = set()

    source_restart_count = 0
    while True:
        print(
            json.dumps(
                {
                    "status": "loop_enter",
                    "source_restart_count": source_restart_count,
                    "clients_seen": base_client_seen + len(seen_clients),
                    "patients_seen": base_patient_seen + len(seen_patients),
                    "pdfs_seen": pdf_count,
                    "resume_reached": resume_reached,
                    "current_stage": progress_state.get("current_stage"),
                },
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
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
                print(json.dumps({"status": "loop_break", "reason": "limit_clients", "clients_seen": base_client_seen + len(seen_clients), "patients_seen": base_patient_seen + len(seen_patients), "pdfs_seen": pdf_count}, indent=2, sort_keys=True), flush=True)
                break
            if args.limit_patients and len(seen_patients) >= args.limit_patients:
                print(json.dumps({"status": "loop_break", "reason": "limit_patients", "clients_seen": base_client_seen + len(seen_clients), "patients_seen": base_patient_seen + len(seen_patients), "pdfs_seen": pdf_count}, indent=2, sort_keys=True), flush=True)
                break
            if args.limit_pdfs and pdf_count >= args.limit_pdfs:
                print(json.dumps({"status": "loop_break", "reason": "limit_pdfs", "clients_seen": base_client_seen + len(seen_clients), "patients_seen": base_patient_seen + len(seen_patients), "pdfs_seen": pdf_count}, indent=2, sort_keys=True), flush=True)
                break
            if client_id not in seen_clients:
                seen_clients.add(client_id)
            if patient_id not in seen_patients:
                seen_patients.add(patient_id)
            progress_state["current_client_name"] = client_name
            progress_state["current_patient_name"] = patient_name
            progress_state["current_stage"] = "discovered"

            if not resume_reached:
                if (client_id, patient_id) == (resume_cursor[0], resume_cursor[1]):
                    resume_reached = True
                else:
                    continue

            charts = _chart_files_for_patient(
                patient_id,
                timeout_s=args.history_timeout,
                max_attempts=args.history_attempts,
                retry_delay_s=args.history_retry_delay,
            )
            for pdf_index, chart in enumerate(charts):
                pdf_id = _text(chart.get("id")) or ""
                filename = _text(chart.get("filename")) or f"{pdf_id}.pdf"
                if not pdf_id:
                    continue
                if resume_reached and pdf_index < resume_pdf_index and client_id == resume_cursor[0] and patient_id == resume_cursor[1]:
                    continue

                progress_state["current_pdf_name"] = filename

                if pdf_id in processed:
                    skipped_count += 1
                    _print_progress(ImportProgress(client_id, patient_id, pdf_id, filename, "already_processed"))
                    _write_checkpoint(
                        checkpoint_path,
                        _checkpoint_payload(
                            processed_pdf_ids=processed,
                            client_id=client_id,
                            patient_id=patient_id,
                            pdf_id=pdf_id,
                            filename=filename,
                            loaded_count=loaded_count,
                            skipped_count=skipped_count,
                            pdf_count=pdf_count,
                            client_seen_count=base_client_seen + len(seen_clients),
                            patient_seen_count=base_patient_seen + len(seen_patients),
                            client_index=account_index,
                            patient_index=patient_index,
                            pdf_index=pdf_index,
                            client_name=client_name,
                            patient_name=patient_name,
                        ),
                    )
                    continue

                pdf_count += 1
                progress_state["clients_seen"] = base_client_seen + len(seen_clients)
                progress_state["patients_seen"] = base_patient_seen + len(seen_patients)
                progress_state["pdfs_seen"] = pdf_count
                elapsed = max(time.perf_counter() - started_at, 0.001)
                rate = pdf_count / elapsed
                client_count = base_client_seen + len(seen_clients)
                patient_count = base_patient_seen + len(seen_patients)
                if client_count > 0 and args.expected_clients > 0:
                    observed_pdfs_per_client = pdf_count / client_count
                    estimated_total_pdfs = max(pdf_count, int(round(observed_pdfs_per_client * args.expected_clients)))
                if estimated_total_pdfs and rate > 0:
                    remaining = max(estimated_total_pdfs - pdf_count, 0)
                    eta_seconds = remaining / rate
                    progress_state["eta_seconds"] = int(round(eta_seconds))
                    progress_state["eta"] = _format_eta(eta_seconds)
                else:
                    progress_state["eta_seconds"] = None
                    progress_state["eta"] = "unknown"
                print(
                    f"[client {client_count}/~{args.expected_clients}] "
                    f"[patient {patient_count}] "
                    f"[file {pdf_count}] {filename} "
                    f"| elapsed={_format_eta(elapsed)} eta={progress_state['eta']}",
                    flush=True,
                )
                _print_progress(ImportProgress(client_id, patient_id, pdf_id, filename, "start"))
                _print_stage(
                    "fetch_url",
                    client_id=client_id,
                    patient_id=patient_id,
                    pdf_id=pdf_id,
                    filename=filename,
                )
                progress_state["current_stage"] = "fetch_url"
                _write_checkpoint(
                    checkpoint_path,
                    _checkpoint_payload(
                        processed_pdf_ids=processed,
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                        loaded_count=loaded_count,
                        skipped_count=skipped_count,
                        pdf_count=pdf_count,
                        client_seen_count=base_client_seen + len(seen_clients),
                        patient_seen_count=base_patient_seen + len(seen_patients),
                        client_index=account_index,
                        patient_index=patient_index,
                        pdf_index=pdf_index,
                        client_name=client_name,
                        patient_name=patient_name,
                    ),
                )
                is_retry_target = pdf_id == resume_failed_pdf and resume_retry_attempts < 1
                try:
                    signed_url_start = time.perf_counter()
                    _print_stage(
                        "signed_url",
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                    )
                    progress_state["current_stage"] = "signed_url"
                    pdf_url = create_chart_file_url(pdf_id, inline=True)
                    _print_timing(
                        "timing_signed_url",
                        time.perf_counter() - signed_url_start,
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                    )
                    _print_progress(ImportProgress(client_id, patient_id, pdf_id, filename, "url_ready"))
                    _print_stage(
                        "process_pdf",
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                        action="download_chunk_embed_load",
                    )
                    progress_state["current_stage"] = "process_pdf"
                    source = PatientPdfSource(
                        patient_id=patient_id,
                        patient_name=_text(patient.get("name") or patient.get("patientName")) or patient_id,
                        pdf_url=pdf_url,
                    )
                    process_pdf_start = time.perf_counter()
                    _print_stage(
                        "chunk_start",
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                    )
                    try:
                        chunk_docs, page_count, timing = chunk_patient_pdf_timed(
                            source,
                            config,
                            term_index=term_index,
                            extraction_timeout_s=args.extraction_timeout,
                        )
                        progress_state["current_stage"] = "chunk_complete"
                        _print_timing(
                            "timing_extract_chunk",
                            timing["download_seconds"] + timing["extraction_seconds"] + timing["chunking_seconds"],
                            download_seconds=round(timing["download_seconds"], 3),
                            extraction_seconds=round(timing["extraction_seconds"], 3),
                            chunking_seconds=round(timing["chunking_seconds"], 3),
                            summary_seconds=round(timing["summary_seconds"], 3),
                            client_id=client_id,
                            patient_id=patient_id,
                            pdf_id=pdf_id,
                            filename=filename,
                        )
                    except DeferredOCRDocument as deferred_exc:
                        deferred_record_started = time.perf_counter()
                        print(
                            json.dumps(
                                {
                                    "status": "deferred",
                                    "stage": "defer_large_no_text_pdf",
                                    "client_id": client_id,
                                    "patient_id": patient_id,
                                    "pdf_id": pdf_id,
                                    "filename": filename,
                                    "page_count": deferred_exc.page_count,
                                    "reason": deferred_exc.reason,
                                },
                                indent=2,
                                sort_keys=True,
                            ),
                            flush=True,
                        )
                        deferred_record_error = _record_deferred_ocr_best_effort(
                            database_url=args.database_url,
                            deferred_ocr_table_name=args.deferred_ocr_table_name,
                            source_name=f"{client_id}:{patient_id}:{filename}",
                            source_uri=pdf_url,
                            patient_id=patient_id,
                            patient_name=patient_name,
                            pdf_id=pdf_id,
                            filename=filename,
                            page_count=deferred_exc.page_count,
                            reason=deferred_exc.reason,
                            metadata=deferred_exc.metadata,
                        )
                        _print_timing(
                            "timing_deferred_ocr_record",
                            time.perf_counter() - deferred_record_started,
                            client_id=client_id,
                            patient_id=patient_id,
                            pdf_id=pdf_id,
                            filename=filename,
                        )
                        skipped_count += 1
                        processed.add(pdf_id)
                        _write_checkpoint(
                            checkpoint_path,
                            _checkpoint_payload(
                                processed_pdf_ids=processed,
                                client_id=client_id,
                                patient_id=patient_id,
                                pdf_id=pdf_id,
                                filename=filename,
                                loaded_count=loaded_count,
                                skipped_count=skipped_count,
                                pdf_count=pdf_count,
                                retry_attempts=0,
                                client_seen_count=base_client_seen + len(seen_clients),
                                patient_seen_count=base_patient_seen + len(seen_patients),
                                client_index=account_index,
                                patient_index=patient_index,
                                pdf_index=pdf_index,
                                client_name=client_name,
                                patient_name=patient_name,
                                error={
                                    "error_type": "DeferredOCRDocument",
                                    "error": deferred_exc.reason,
                                    "action": "deferred_for_later_ocr",
                                    **({"deferred_ocr_record_error": deferred_record_error} if deferred_record_error else {}),
                                },
                            ),
                        )
                        _print_progress(
                            ImportProgress(
                                client_id,
                                patient_id,
                                pdf_id,
                                filename,
                                "deferred",
                                detail=deferred_exc.reason,
                            )
                        )
                        continue
                    except NoTextLayerError as no_text_exc:
                        reason = "unexpected pdf structure"
                        deferred_record_started = time.perf_counter()
                        print(
                            json.dumps(
                                {
                                    "status": "deferred",
                                    "stage": "defer_no_text_pdf",
                                    "client_id": client_id,
                                    "patient_id": patient_id,
                                    "pdf_id": pdf_id,
                                    "filename": filename,
                                    "page_count": getattr(no_text_exc, "page_count", None),
                                    "reason": reason,
                                },
                                indent=2,
                                sort_keys=True,
                            ),
                            flush=True,
                        )
                        deferred_record_error = _record_deferred_ocr_best_effort(
                            database_url=args.database_url,
                            deferred_ocr_table_name=args.deferred_ocr_table_name,
                            source_name=f"{client_id}:{patient_id}:{filename}",
                            source_uri=pdf_url,
                            patient_id=patient_id,
                            patient_name=patient_name,
                            pdf_id=pdf_id,
                            filename=filename,
                            page_count=getattr(no_text_exc, "page_count", None),
                            reason=reason,
                            metadata={
                                "patient_id": patient_id,
                                "patient_name": patient_name,
                                "pdf_id": pdf_id,
                                "filename": filename,
                                "client_id": client_id,
                                "client_name": client_name,
                                "action": "deferred_no_text_pdf",
                            },
                        )
                        _print_timing(
                            "timing_deferred_ocr_record",
                            time.perf_counter() - deferred_record_started,
                            client_id=client_id,
                            patient_id=patient_id,
                            pdf_id=pdf_id,
                            filename=filename,
                        )
                        skipped_count += 1
                        processed.add(pdf_id)
                        _write_checkpoint(
                            checkpoint_path,
                            _checkpoint_payload(
                                processed_pdf_ids=processed,
                                client_id=client_id,
                                patient_id=patient_id,
                                pdf_id=pdf_id,
                                filename=filename,
                                loaded_count=loaded_count,
                                skipped_count=skipped_count,
                                pdf_count=pdf_count,
                                retry_attempts=0,
                                client_seen_count=base_client_seen + len(seen_clients),
                                patient_seen_count=base_patient_seen + len(seen_patients),
                                client_index=account_index,
                                patient_index=patient_index,
                                pdf_index=pdf_index,
                                client_name=client_name,
                                patient_name=patient_name,
                                error={
                                    "error_type": "NoTextLayerError",
                                    "error": reason,
                                    "action": "deferred_no_text_pdf",
                                    **({"deferred_ocr_record_error": deferred_record_error} if deferred_record_error else {}),
                                },
                            ),
                        )
                        _print_progress(
                            ImportProgress(
                                client_id,
                                patient_id,
                                pdf_id,
                                filename,
                                "deferred",
                                detail=reason,
                            )
                        )
                        continue
                    except RuntimeError as chunk_exc:
                        chunk_error = str(chunk_exc)
                        if "PDF text extraction crashed with signal 11" in chunk_error or "PDF text extraction exceeded" in chunk_error:
                            deferred_record_started = time.perf_counter()
                            print(
                                json.dumps(
                                    {
                                        "status": "deferred",
                                        "stage": "defer_problem_pdf",
                                        "client_id": client_id,
                                        "patient_id": patient_id,
                                        "pdf_id": pdf_id,
                                        "filename": filename,
                                        "reason": chunk_error,
                                    },
                                    indent=2,
                                    sort_keys=True,
                                ),
                                flush=True,
                            )
                            deferred_record_error = _record_deferred_ocr_best_effort(
                                database_url=args.database_url,
                                deferred_ocr_table_name=args.deferred_ocr_table_name,
                                source_name=f"{client_id}:{patient_id}:{filename}",
                                source_uri=pdf_url,
                                patient_id=patient_id,
                                patient_name=patient_name,
                                pdf_id=pdf_id,
                                filename=filename,
                                page_count=None,
                                reason=chunk_error,
                                metadata={
                                    "patient_id": patient_id,
                                    "patient_name": patient_name,
                                    "pdf_id": pdf_id,
                                    "filename": filename,
                                    "client_id": client_id,
                                    "client_name": client_name,
                                    "action": "deferred_problem_pdf",
                                },
                            )
                            _print_timing(
                                "timing_deferred_ocr_record",
                                time.perf_counter() - deferred_record_started,
                                client_id=client_id,
                                patient_id=patient_id,
                                pdf_id=pdf_id,
                                filename=filename,
                            )
                            skipped_count += 1
                            processed.add(pdf_id)
                            _write_checkpoint(
                                checkpoint_path,
                                _checkpoint_payload(
                                    processed_pdf_ids=processed,
                                    client_id=client_id,
                                    patient_id=patient_id,
                                    pdf_id=pdf_id,
                                    filename=filename,
                                    loaded_count=loaded_count,
                                    skipped_count=skipped_count,
                                    pdf_count=pdf_count,
                                    retry_attempts=0,
                                    client_seen_count=base_client_seen + len(seen_clients),
                                    patient_seen_count=base_patient_seen + len(seen_patients),
                                    client_index=account_index,
                                    patient_index=patient_index,
                                    pdf_index=pdf_index,
                                    client_name=client_name,
                                    patient_name=patient_name,
                                    error={
                                        "error_type": type(chunk_exc).__name__,
                                        "error": chunk_error,
                                        "action": "deferred_problem_pdf",
                                        **({"deferred_ocr_record_error": deferred_record_error} if deferred_record_error else {}),
                                    },
                                ),
                            )
                            _print_progress(
                                ImportProgress(
                                    client_id,
                                    patient_id,
                                    pdf_id,
                                    filename,
                                    "deferred",
                                    detail=chunk_error,
                                )
                            )
                            continue
                        raise
                    except Exception as chunk_exc:
                        print(
                            json.dumps(
                                {
                                    "status": "failed",
                                    "stage": "chunk_patient_pdf",
                                    "client_id": client_id,
                                    "patient_id": patient_id,
                                    "pdf_id": pdf_id,
                                    "filename": filename,
                                    "error_type": type(chunk_exc).__name__,
                                    "error": str(chunk_exc),
                                },
                                indent=2,
                                sort_keys=True,
                            ),
                            flush=True,
                        )
                        traceback.print_exc()
                        raise
                    _print_stage(
                        "chunk_complete",
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                        page_count=page_count,
                        chunk_count=len(chunk_docs),
                    )
                    term_summary = chunk_docs[0].metadata.get("term_summary", {}) if chunk_docs else {}
                    if isinstance(term_summary, dict):
                        keywords = ", ".join(sorted(term_summary.keys())) or "none"
                    else:
                        keywords = "none"
                    _print_progress(
                        ImportProgress(
                            client_id,
                            patient_id,
                            pdf_id,
                            filename,
                            "chunked",
                            page_count=page_count,
                            chunk_count=len(chunk_docs),
                        )
                    )
                    print(
                        f"    size=streamed chunks={len(chunk_docs)} keywords={keywords} summary_saved=yes",
                        flush=True,
                    )
                    _print_stage(
                        "embed_load",
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                        embedding_model=args.embedding_model,
                        vector_dimensions=args.vector_dimensions,
                    )
                    progress_state["current_stage"] = "embed_load"
                    load_start = time.perf_counter()
                    load_into_postgres(
                        database_url=args.database_url,
                        table_name=args.table_name,
                        source_document_table_name=args.source_document_table_name,
                        source_name=f"{client_id}:{patient_id}:{filename}",
                        source_uri=pdf_url,
                        documents=chunk_docs,
                        embedding_model=args.embedding_model,
                        vector_dimensions=args.vector_dimensions,
                        embedding_batch_size=args.embedding_batch_size,
                        load_batch_size=args.load_batch_size,
                    )
                    _print_timing(
                        "timing_embed_load",
                        time.perf_counter() - load_start,
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                        embedding_model=args.embedding_model,
                        vector_dimensions=args.vector_dimensions,
                    )
                    _print_timing(
                        "timing_process_pdf_total",
                        time.perf_counter() - process_pdf_start,
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                    )
                    loaded_count += 1
                    print(f"    loaded into Aurora/Postgres; deleting_local={args.delete_local_after_load and not args.keep_local}", flush=True)
                    _print_stage(
                        "load_complete",
                        client_id=client_id,
                        patient_id=patient_id,
                        pdf_id=pdf_id,
                        filename=filename,
                        loaded=True,
                    )
                    progress_state["current_stage"] = "load_complete"
                    _print_progress(
                        ImportProgress(
                            client_id,
                            patient_id,
                            pdf_id,
                            filename,
                            "loaded",
                            page_count=page_count,
                            chunk_count=len(chunk_docs),
                        )
                    )
                    if args.delete_local_after_load and not args.keep_local:
                        local_path = output_dir / client_id / patient_id / filename
                        if local_path.exists():
                            local_path.unlink(missing_ok=True)
                            print(f"    deleted local file {local_path}", flush=True)
                    processed.add(pdf_id)
                    _write_checkpoint(
                        checkpoint_path,
                        _checkpoint_payload(
                            processed_pdf_ids=processed,
                            client_id=client_id,
                            patient_id=patient_id,
                            pdf_id=pdf_id,
                            filename=filename,
                            loaded_count=loaded_count,
                            skipped_count=skipped_count,
                            pdf_count=pdf_count,
                            retry_attempts=0,
                            client_seen_count=len(seen_clients),
                            patient_seen_count=len(seen_patients),
                            client_index=account_index,
                            patient_index=patient_index,
                            pdf_index=pdf_index,
                            client_name=client_name,
                            patient_name=patient_name,
                        ),
                    )
                except Exception as exc:
                    print(
                        json.dumps(
                            {
                                "status": "failed",
                                "client_id": client_id,
                                "patient_id": patient_id,
                                "pdf_id": pdf_id,
                                "filename": filename,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                            indent=2,
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    traceback.print_exc()
                    if is_retry_target:
                        processed.add(pdf_id)
                        skipped_count += 1
                        _write_checkpoint(
                            checkpoint_path,
                            _checkpoint_payload(
                                processed_pdf_ids=processed,
                                client_id=client_id,
                                patient_id=patient_id,
                                pdf_id=pdf_id,
                                filename=filename,
                                loaded_count=loaded_count,
                                skipped_count=skipped_count,
                                pdf_count=pdf_count,
                                retry_attempts=1,
                                client_seen_count=base_client_seen + len(seen_clients),
                                patient_seen_count=base_patient_seen + len(seen_patients),
                                client_index=account_index,
                                patient_index=patient_index,
                                pdf_index=pdf_index,
                                client_name=client_name,
                                patient_name=patient_name,
                                error={
                                    "error_type": type(exc).__name__,
                                    "error": str(exc),
                                    "action": "skipped_after_retry",
                                },
                            ),
                        )
                    else:
                        _write_checkpoint(
                            checkpoint_path,
                            _checkpoint_payload(
                                processed_pdf_ids=processed,
                                client_id=client_id,
                                patient_id=patient_id,
                                pdf_id=pdf_id,
                                filename=filename,
                                loaded_count=loaded_count,
                                skipped_count=skipped_count,
                                pdf_count=pdf_count,
                                retry_attempts=0,
                                client_seen_count=len(seen_clients),
                                patient_seen_count=len(seen_patients),
                                client_index=account_index,
                                patient_index=patient_index,
                                pdf_index=pdf_index,
                                client_name=client_name,
                                patient_name=patient_name,
                                error={
                                    "error_type": type(exc).__name__,
                                    "error": str(exc),
                                    "action": "retry_once_on_restart",
                                },
                            ),
                        )
                    _print_progress(
                        ImportProgress(
                            client_id,
                            patient_id,
                            pdf_id,
                            filename,
                            "failed",
                            detail=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    continue

        if args.limit_clients or args.limit_patients or args.limit_pdfs:
            print(
                json.dumps(
                    {
                        "status": "loop_exit",
                        "reason": "limit_reached",
                        "clients_seen": base_client_seen + len(seen_clients),
                        "patients_seen": base_patient_seen + len(seen_patients),
                        "pdfs_seen": pdf_count,
                    },
                    indent=2,
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
                        "clients_seen": base_client_seen + len(seen_clients),
                        "patients_seen": base_patient_seen + len(seen_patients),
                        "pdfs_seen": pdf_count,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                flush=True,
            )
            print(
                json.dumps(
                    {
                        "status": "loop_exit",
                        "reason": "source_end_no_new_pdfs",
                        "clients_seen": base_client_seen + len(seen_clients),
                        "patients_seen": base_patient_seen + len(seen_patients),
                        "pdfs_seen": pdf_count,
                    },
                    indent=2,
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
                    "clients_seen": base_client_seen + len(seen_clients),
                    "patients_seen": base_patient_seen + len(seen_patients),
                    "pdfs_seen": pdf_count,
                    "new_pdfs_this_pass": new_pdfs_this_pass,
                },
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
        adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
        adapter.token = adapter.authenticate()
    heartbeat.stop()

    print(
        json.dumps(
            {
                "status": "complete",
                "clients_seen": base_client_seen + len(seen_clients),
                "patients_seen": base_patient_seen + len(seen_patients),
                "pdfs_seen": pdf_count,
                "loaded": loaded_count,
                "skipped": skipped_count,
                "checkpoint": str(checkpoint_path) if checkpoint_path else None,
                "embedding_model": args.embedding_model,
                "vector_dimensions": args.vector_dimensions,
                "eta": progress_state.get("eta"),
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
