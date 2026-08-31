#!/usr/bin/env python3
"""Launch the fixed importer for RAG performance timing runs."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

_PROGRESS_LINE_RE = re.compile(r"^\x1b\[[0-9;]*m\s*\[client\s+\d+/~\d+\]")


def _strip_ansi(line: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", line)


def _echo_to_console(line: str) -> bool:
    """Return true for the reduced live console stream.

    The launcher still writes every child stdout/stderr line to the log file.
    The console is intentionally limited to errors, retries, high-level client
    progress lines, and successful/deferred PDF completion lines.
    """
    plain = _strip_ansi(line).strip()
    lowered = plain.lower()
    if not plain:
        return False
    if plain.startswith("[client ") or plain.startswith(" [client ") or _PROGRESS_LINE_RE.match(line):
        return True
    console_tokens = (
        "error",
        "exception",
        "traceback",
        "fatal",
        "failed",
        "retry",
        "will_retry",
        "loaded into aurora/postgres",
        "completed processing pdf successfully",
        "pdf deferred",
        "deferred",
        '"status": "loaded"',
        '"status_detail": "loaded"',
        '"status": "deferred"',
        '"status_detail": "deferred"',
    )
    return any(token in lowered for token in console_tokens)


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


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    data_root = project_root.parents[4] / "data"
    venv_python = project_root / ".venv" / "bin" / "python"
    log_file = Path("/tmp/evh_instinct_import_fixed.out")
    pid_file = Path("/tmp/evh_instinct_import_fixed.pid")
    status_file = Path("/tmp/evh_instinct_import_fixed.status")
    exitcode_file = Path("/tmp/evh_instinct_import_fixed.exitcode")
    launcher_pid_file = Path("/tmp/evh_instinct_import_fixed.launcher.pid")
    checkpoint = Path("/tmp/evh_instinct_import.checkpoint.json")
    output_dir = Path("/tmp/evh_instinct_import")
    pdf_storage_dir = data_root / "instinct-pdfs"
    deferred_pdf_dir = data_root / "instinct-pdfs-deferred"
    processed_pdf_dir = data_root / "instinct-pdfs-processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_storage_dir.mkdir(parents=True, exist_ok=True)
    deferred_pdf_dir.mkdir(parents=True, exist_ok=True)
    processed_pdf_dir.mkdir(parents=True, exist_ok=True)
    log_file.write_text("", encoding="utf-8")
    status_file.write_text("", encoding="utf-8")
    exitcode_file.write_text("", encoding="utf-8")
    launcher_pid_file.write_text(str(os.getpid()), encoding="utf-8")

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/tmp/uv-cache")
    cmd = [
        str(venv_python if venv_python.exists() else Path(sys.executable)),
        "-u",
        str(project_root / "scripts" / "instinct_full_import_fixed.py"),
        "--database-url",
        _build_db_url(),
        "--pdf-storage-dir",
        str(pdf_storage_dir),
        "--deferred-pdf-dir",
        str(deferred_pdf_dir),
        "--processed-pdf-dir",
        str(processed_pdf_dir),
        "--checkpoint",
        str(checkpoint),
        "--embedding-model",
        "text-embedding-3-small",
        "--vector-dimensions",
        "1536",
        "--expected-clients",
        "12053",
    ]

    with log_file.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        pid_file.write_text(str(proc.pid), encoding="utf-8")
        for launcher_line in (
            f"started importer pid={proc.pid} python={cmd[0]} log={log_file} pidfile={pid_file}",
            f"launcher pid={os.getpid()} child pid={proc.pid} log={log_file} pidfile={pid_file}",
        ):
            log.write(f"{launcher_line}\n")
        log.flush()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                log.write(line)
                log.flush()
                if _echo_to_console(line):
                    print(line, end="", flush=True)
            rc = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                rc = proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = proc.wait()
            rc = 130 if rc == 0 else rc
        if rc >= 0:
            status = f"exited:{rc}"
            code = rc
        else:
            status = f"signaled:{-rc}"
            code = 128 + (-rc)
        exitcode_file.write_text(str(code), encoding="utf-8")
        status_file.write_text(
            f"{status} child_pid={proc.pid} launcher_pid={os.getpid()}\n",
            encoding="utf-8",
        )
        return code


if __name__ == "__main__":
    raise SystemExit(main())
