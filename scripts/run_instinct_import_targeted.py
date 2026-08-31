#!/usr/bin/env python3
"""Run the fixed importer with optional client/patient targeting for ECS tests.

This is intended for:
- single very large client imports
- one-patient smoke tests
- crash/restart-friendly runs with checkpointing

It preserves the existing importer's restart model but lets us scope the run
with client/patient ids when the operator wants to test a single lane.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from scripts.evh_reminder_importer import InstinctApiAdapter


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the fixed importer with optional client/patient targeting.")
    parser.add_argument("--client-id", default="", help="Optional Instinct client id to target.")
    parser.add_argument("--patient-id", default="", help="Optional Instinct patient id to target.")
    parser.add_argument("--start-client-index", type=int, default=0)
    parser.add_argument("--limit-clients", type=int, default=0)
    parser.add_argument("--limit-pdfs", type=int, default=0)
    parser.add_argument("--checkpoint", default="/tmp/evh_instinct_import.checkpoint.json")
    parser.add_argument("--pdf-storage-dir", default="")
    parser.add_argument("--deferred-pdf-dir", default="")
    parser.add_argument("--processed-pdf-dir", default="")
    parser.add_argument("--extraction-timeout", default="45")
    parser.add_argument("--embedding-batch-size", default="64")
    parser.add_argument("--load-batch-size", default="500")
    parser.add_argument("--expected-clients", default="12053")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[1]
    venv_python = project_root / ".venv" / "bin" / "python"

    start_client_index = args.start_client_index
    limit_clients = args.limit_clients
    if args.client_id.strip():
        username = os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME")
        password = os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD")
        if not username or not password:
            raise SystemExit("Missing Instinct credentials for client targeting.")
        adapter = InstinctApiAdapter(os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"), username, password)
        accounts = list(adapter.iter_accounts())
        for idx, account in enumerate(accounts):
            account_id = str(account.get("id") or "").strip()
            if account_id == args.client_id.strip():
                start_client_index = idx
                limit_clients = 1
                break
        else:
            raise SystemExit(f"Unable to resolve client_id={args.client_id!r} to an account index.")

    cmd = [
        str(venv_python if venv_python.exists() else Path(sys.executable)),
        "-u",
        str(project_root / "scripts" / "instinct_full_import_fixed.py"),
        "--database-url",
        _build_db_url(),
        "--checkpoint",
        args.checkpoint,
        "--embedding-model",
        "text-embedding-3-small",
        "--vector-dimensions",
        "1536",
        "--embedding-batch-size",
        args.embedding_batch_size,
        "--load-batch-size",
        args.load_batch_size,
        "--extraction-timeout",
        args.extraction_timeout,
        "--expected-clients",
        args.expected_clients,
        "--client-pdf-workers",
        "1",
        "--page-workers",
        "1",
        "--embedding-workers",
        "1",
    ]

    if start_client_index:
        cmd.extend(["--start-client-index", str(start_client_index)])
    if limit_clients:
        cmd.extend(["--limit-clients", str(limit_clients)])
    if args.limit_pdfs:
        cmd.extend(["--limit-pdfs", str(args.limit_pdfs)])
    if args.pdf_storage_dir:
        cmd.extend(["--pdf-storage-dir", args.pdf_storage_dir])
    if args.deferred_pdf_dir:
        cmd.extend(["--deferred-pdf-dir", args.deferred_pdf_dir])
    if args.processed_pdf_dir:
        cmd.extend(["--processed-pdf-dir", args.processed_pdf_dir])

    # The fixed importer already has its own restart/checkpoint machinery.
    # We pass the target hints through environment variables for the worker
    # code to consult without baking them into the schedule.
    env = os.environ.copy()
    if args.client_id.strip():
        env["EVH_IMPORT_TARGET_CLIENT_ID"] = args.client_id.strip()
    if args.patient_id.strip():
        env["EVH_IMPORT_TARGET_PATIENT_ID"] = args.patient_id.strip()

    proc = subprocess.run(cmd, cwd=str(project_root), env=env, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
