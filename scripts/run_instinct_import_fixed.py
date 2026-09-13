#!/usr/bin/env python3
"""Launch the quiet fixed importer, write the real child PID, and record exit status."""

from __future__ import annotations

import os
import subprocess
import sys
import json
from pathlib import Path
from urllib.parse import quote


def _build_db_url() -> str:
    db_url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if db_url:
        return db_url

    required = ("EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD")
    if not all(os.environ.get(name, "").strip() for name in required):
        secret_arn = os.environ.get("DB_SECRET_ARN", "").strip()
        if not secret_arn:
            missing = ", ".join(name for name in required if not os.environ.get(name, "").strip())
            raise RuntimeError(
                "Missing EVH_PG* env vars and DB_SECRET_ARN is not set. "
                f"Missing vars: {missing or 'unknown'}"
            )
        proc = subprocess.run(
            [
                "aws",
                "secretsmanager",
                "get-secret-value",
                "--region",
                os.environ.get("AWS_REGION", "us-east-1"),
                "--secret-id",
                secret_arn,
                "--query",
                "SecretString",
                "--output",
                "text",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "").strip() or f"Failed to read Secrets Manager secret {secret_arn}.")
        secret = str(proc.stdout or "").strip()
        if not secret:
            raise RuntimeError(f"Secrets Manager returned an empty secret for {secret_arn!r}.")
        data = json.loads(secret)
        if not isinstance(data, dict):
            raise RuntimeError("Secret must be a JSON object")

        host = str(data.get("host") or data.get("hostname") or data.get("PGHOST") or "").strip()
        port = str(data.get("port") or data.get("PGPORT") or "5432").strip()
        db = str(data.get("dbname") or data.get("database") or data.get("PGDATABASE") or "").strip()
        user = str(data.get("username") or data.get("user") or data.get("PGUSER") or "").strip()
        password = str(data.get("password") or data.get("PGPASSWORD") or "").strip()
        if not all([host, port, db, user, password]):
            raise RuntimeError("Secret did not contain the full Postgres tuple. Need host, port, dbname, user, and password.")

        os.environ["EVH_PGHOST"] = host
        os.environ["EVH_PGPORT"] = port
        os.environ["EVH_PGDATABASE"] = db
        os.environ["EVH_PGUSER"] = user
        os.environ["EVH_PGPASSWORD"] = password

    host = os.environ["EVH_PGHOST"]
    port = os.environ["EVH_PGPORT"]
    db = os.environ["EVH_PGDATABASE"]
    user = os.environ["EVH_PGUSER"]
    password = quote(os.environ["EVH_PGPASSWORD"], safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}?sslmode=require"


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    venv_python = project_root / ".venv" / "bin" / "python"
    log_file = Path("/tmp/evh_instinct_import_fixed.out")
    pid_file = Path("/tmp/evh_instinct_import_fixed.pid")
    status_file = Path("/tmp/evh_instinct_import_fixed.status")
    exitcode_file = Path("/tmp/evh_instinct_import_fixed.exitcode")
    launcher_pid_file = Path("/tmp/evh_instinct_import_fixed.launcher.pid")
    checkpoint = Path("/tmp/evh_instinct_import.checkpoint.json")
    log_file.write_text("", encoding="utf-8")
    status_file.write_text("", encoding="utf-8")
    exitcode_file.write_text("", encoding="utf-8")
    launcher_pid_file.write_text(str(os.getpid()), encoding="utf-8")

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/tmp/uv-cache")
    env["EVH_PDF_STORAGE_DIR"] = "/tmp/evh_instinct_import/pdfs"
    env["EVH_DEFERRED_PDF_DIR"] = "/tmp/evh_instinct_import/deferred"
    env["EVH_PROCESSED_PDF_DIR"] = "/tmp/evh_instinct_import/processed"
    cmd = [
        str(venv_python if venv_python.exists() else Path(sys.executable)),
        str(project_root / "scripts" / "instinct_full_import_fixed.py"),
        "--database-url",
        _build_db_url(),
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
