#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""Export canonical PDF identity rows to CSV without writing to the database.

This walks Instinct accounts -> patients -> chart files and emits a CSV with
the fields needed to populate rag_document_identity later.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_pdf_size_table import _chart_files_for_patient, _iter_accounts, _iter_patients_for_account, _normalize_text


def _safe(value: Any) -> str:
    text = _normalize_text(value)
    return text or ""


def _load_seen_client_ids(csv_path: Path) -> set[str]:
    if not csv_path.is_file():
        return set()
    seen: set[str] = set()
    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "client_id" not in reader.fieldnames:
                return seen
            for row in reader:
                client_id = _safe(row.get("client_id"))
                if client_id:
                    seen.add(client_id)
    except Exception:
        return set()
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Instinct document identity rows to CSV")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--output", default="/tmp/rag_document_identity.csv")
    parser.add_argument("--seed-csv", default="/tmp/rag_document_identity.csv")
    parser.add_argument("--limit-accounts", type=int, default=0)
    parser.add_argument("--limit-patients", type=int, default=0)
    args = parser.parse_args()

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials.")

    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.token = adapter.authenticate()

    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "pdf_id",
        "client_id",
        "patient_id",
        "originalfilename",
    ]

    rows = 0
    seed_path = Path(args.seed_csv).expanduser()
    seen_client_ids = _load_seen_client_ids(out_path) | _load_seen_client_ids(seed_path)
    print(
        json.dumps(
            {
                "startup_seen_client_ids": len(seen_client_ids),
                "seed_csv": str(seed_path),
                "output": str(out_path),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    accounts_seen = 0
    patients_seen = 0
    accounts_skipped = 0
    patients_skipped = 0
    file_mode = "a" if out_path.exists() and out_path.stat().st_size > 0 else "w"
    with out_path.open(file_mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if file_mode == "w":
            writer.writeheader()

        for account_index, account in enumerate(_iter_accounts(adapter), start=1):
            if args.limit_accounts and account_index > args.limit_accounts:
                break
            client_id = _safe(account.get("id"))
            if not client_id:
                continue
            if client_id in seen_client_ids:
                accounts_skipped += 1
                print(
                    json.dumps(
                        {
                            "skip_known_account": True,
                            "account_index": account_index,
                            "client_id": client_id,
                            "output": str(out_path),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                continue
            accounts_seen += 1

            for patient_index, patient in enumerate(_iter_patients_for_account(adapter, client_id), start=1):
                if args.limit_patients and patient_index > args.limit_patients:
                    break
                patient_id = _safe(patient.get("id"))
                if not patient_id:
                    continue
                patients_seen += 1

                charts = _chart_files_for_patient(adapter, patient_id)
                for chart in charts:
                    if not isinstance(chart, dict) or chart.get("__typename") != "ChartFile":
                        continue
                    pdf_id = _safe(chart.get("id"))
                    filename = _safe(chart.get("filename"))
                    if not pdf_id or not filename:
                        continue

                    writer.writerow(
                        {
                            "pdf_id": pdf_id,
                            "client_id": client_id,
                            "patient_id": patient_id,
                            "originalfilename": filename,
                        }
                    )
                    seen_client_ids.add(client_id)
                    rows += 1
                    if rows % 100 == 0:
                        print(
                            json.dumps(
                                {
                                    "rows_written": rows,
                                    "account_index": account_index,
                                    "patient_index": patient_index,
                                    "client_id": client_id,
                                    "patient_id": patient_id,
                                    "output": str(out_path),
                                },
                                sort_keys=True,
                            ),
                            flush=True,
                        )
    print(
        json.dumps(
            {
                "output": str(out_path),
                "rows": rows,
                "accounts_seen": accounts_seen,
                "patients_seen": patients_seen,
                "accounts_skipped": accounts_skipped,
                "patients_skipped": patients_skipped,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
