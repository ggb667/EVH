#!/usr/bin/env python3
"""Launch the quiet fixed importer, write the real child PID, and record exit status."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


def _build_db_url() -> str:
    db_url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if db_url:
        return db_url
    user = os.environ["EVH_PGUSER"]
    pw = quote(os.environ["EVH_PGPASSWORD"], safe="")
    host = os.environ["EVH_PGHOST"]
    port = os.environ["EVH_PGPORT"]
    db = os.environ["EVH_PGDATABASE"]
    # RDS rejects the non-encrypted fallback; require TLS explicitly so a
    # bad credential cannot be masked by a misleading pg_hba/no-encryption
    # error on the second connection attempt.
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}?sslmode=require"


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    venv_python = project_root / ".venv" / "bin" / "python"
    log_file = Path("/tmp/evh_instinct_import_fixed.out")
    pid_file = Path("/tmp/evh_instinct_import_fixed.pid")
    status_file = Path("/tmp/evh_instinct_import_fixed.status")
    exitcode_file = Path("/tmp/evh_instinct_import_fixed.exitcode")
    launcher_pid_file = Path("/tmp/evh_instinct_import_fixed.launcher.pid")
    checkpoint = Path("/tmp/evh_instinct_import.checkpoint.json")
    output_dir = Path("/tmp/evh_instinct_import")
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file.write_text("", encoding="utf-8")
    status_file.write_text("", encoding="utf-8")
    exitcode_file.write_text("", encoding="utf-8")
    launcher_pid_file.write_text(str(os.getpid()), encoding="utf-8")

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/tmp/uv-cache")
    cmd = [
        str(venv_python if venv_python.exists() else Path(sys.executable)),
        str(project_root / "scripts" / "instinct_full_import_fixed.py"),
        "--database-url",
        _build_db_url(),
        "--output-dir",
        str(output_dir),
        "--checkpoint",
        str(checkpoint),
        "--embedding-model",
        "text-embedding-3-small",
        "--vector-dimensions",
        "1536",
        "--embedding-batch-size",
        "64",
        "--load-batch-size",
        "500",
        "--extraction-timeout",
        "45",
        "--delete-local-after-load",
        "--expected-clients",
        "12053",
        "--client-pdf-workers",
        "1",
        "--page-workers",
        "1",
        "--embedding-workers",
        "1",
    ]

    with log_file.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        pid_file.write_text(str(proc.pid), encoding="utf-8")
        print(
            f"started importer pid={proc.pid} python={cmd[0]} log={log_file} pidfile={pid_file}",
            flush=True,
        )
        print(
            f"launcher pid={os.getpid()} child pid={proc.pid} log={log_file} pidfile={pid_file}",
            flush=True,
        )
        rc = proc.wait()
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
