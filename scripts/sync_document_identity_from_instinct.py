#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""Sync canonical document identity rows into Postgres.

This supports two modes:

1. Walk Instinct accounts -> patients -> chart files and upsert the four
   canonical identity columns into rag_document_identity.
2. Tail a CSV file that is being written concurrently and upsert rows as they
   appear.

- document_pdf_id
- client_id
- patient_id
- originalfilename

No PDFs are downloaded.
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

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_pdf_size_table import _chart_files_for_patient, _iter_accounts, _iter_patients_for_account, _normalize_text


def _safe(value: Any) -> str:
    text = _normalize_text(value)
    return text or ""


def _build_db_url() -> str:
    db_url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if db_url:
        return db_url
    return (
        f"postgresql://{os.environ['EVH_PGUSER']}:{os.environ['EVH_PGPASSWORD']}"
        f"@{os.environ['EVH_PGHOST']}:{os.environ['EVH_PGPORT']}/{os.environ['EVH_PGDATABASE']}?sslmode=require"
    )


def _load_checkpoint(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {"account_index": 1, "patient_index": 1}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "account_index": max(1, int(payload.get("account_index", 1))),
            "patient_index": max(1, int(payload.get("patient_index", 1))),
        }
    except Exception:
        return {"account_index": 1, "patient_index": 1}


def _save_checkpoint(path: Path, *, account_index: int, patient_index: int, rows_collected: int, rows_written: int) -> None:
    payload = {
        "account_index": account_index,
        "patient_index": patient_index,
        "rows_collected": rows_collected,
        "rows_written": rows_written,
        "updated_at_unix": time.time(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_csv_checkpoint(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {"row_number": 1}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {"row_number": max(1, int(payload.get("row_number", 1)))}
    except Exception:
        return {"row_number": 1}


def _save_csv_checkpoint(path: Path, *, row_number: int, rows_collected: int, rows_written: int) -> None:
    payload = {
        "row_number": row_number,
        "rows_collected": rows_collected,
        "rows_written": rows_written,
        "updated_at_unix": time.time(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _upsert_batch(cur, batch: list[tuple[str, str, str, str]]) -> None:
    if not batch:
        return
    print(f"upsert_start | batch_size={len(batch)}", flush=True)
    sql = """
        INSERT INTO rag_document_identity (document_pdf_id, client_id, patient_id, originalfilename)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (document_pdf_id) DO UPDATE SET
            client_id = EXCLUDED.client_id,
            patient_id = EXCLUDED.patient_id,
            originalfilename = EXCLUDED.originalfilename
    """
    for idx, row in enumerate(batch, start=1):
        if idx == 1 or idx == len(batch) or idx % 10 == 0:
            print(f"upsert_row | index={idx}/{len(batch)} | document_document_pdf_id={row[0]}", flush=True)
        cur.execute(sql, row)
    print(f"upsert_done | batch_size={len(batch)}", flush=True)


def _read_complete_csv_text(path: Path) -> str:
    raw = path.read_bytes()
    if not raw:
        return ""
    if raw.endswith(b"\n"):
        return raw.decode("utf-8", errors="replace")
    last_newline = raw.rfind(b"\n")
    if last_newline < 0:
        return ""
    return raw[: last_newline + 1].decode("utf-8", errors="replace")


def _stream_csv_rows(
    *,
    csv_path: Path,
    checkpoint_path: Path,
    batch_size: int,
    poll_interval_s: float,
    idle_timeout_s: float,
    dry_run: bool,
    conn,
) -> tuple[int, int]:
    checkpoint = _load_csv_checkpoint(checkpoint_path)
    row_number = checkpoint["row_number"]
    total_rows = 0
    rows_written = 0
    started_at = time.monotonic()
    batch: list[tuple[str, str, str, str]] = []
    last_size = -1
    last_progress_at = time.monotonic()
    print(f"csv_tail_start | csv_path={csv_path} | batch_size={batch_size} | idle_timeout_s={idle_timeout_s} | poll_interval_s={poll_interval_s}", flush=True)

    with conn.cursor() as cur:
        while True:
            if not csv_path.exists():
                print(f"csv_wait_missing | csv_path={csv_path}", flush=True)
                if time.monotonic() - last_progress_at >= idle_timeout_s:
                    break
                time.sleep(poll_interval_s)
                continue

            size = csv_path.stat().st_size
            print(f"csv_probe | size={size} | last_size={last_size} | row_number={row_number} | rows_collected={total_rows} | rows_written={rows_written}", flush=True)
            if size == last_size and time.monotonic() - last_progress_at >= idle_timeout_s:
                print("csv_idle_timeout_reached", flush=True)
                break
            last_size = size

            csv_text = _read_complete_csv_text(csv_path)
            if not csv_text:
                print("csv_no_complete_lines_yet", flush=True)
                time.sleep(poll_interval_s)
                continue

            reader = csv.DictReader(csv_text.splitlines())
            if reader.fieldnames is None:
                print("csv_missing_header", flush=True)
                time.sleep(poll_interval_s)
                continue
            print(f"csv_header | fields={reader.fieldnames}", flush=True)
            for current_row_number, row in enumerate(reader, start=2):
                if current_row_number < row_number:
                    continue
                document_pdf_id = _safe(row.get("document_pdf_id"))
                client_id = _safe(row.get("client_id"))
                patient_id = _safe(row.get("patient_id"))
                originalfilename = _safe(row.get("originalfilename") or row.get("filename"))
                if not document_pdf_id or not client_id or not patient_id or not originalfilename:
                    print(f"csv_skip_row | row_number={current_row_number} | document_pdf_id={document_pdf_id!r} | client_id={client_id!r} | patient_id={patient_id!r} | originalfilename={originalfilename!r}", flush=True)
                    continue
                batch.append((document_pdf_id, client_id, patient_id, originalfilename))
                total_rows += 1
                row_number = current_row_number + 1
                last_progress_at = time.monotonic()
                print(f"csv_row_ok | row_number={current_row_number} | document_pdf_id={document_pdf_id} | batch_count={len(batch)} | total_rows={total_rows}", flush=True)

                if len(batch) >= batch_size:
                    print(f"csv_batch_ready | row_number={row_number} | batch_size={len(batch)}", flush=True)
                    if not dry_run:
                        _upsert_batch(cur, batch)
                    rows_written += len(batch)
                    elapsed = time.monotonic() - started_at
                    print(
                        f"csv_batch_flush | row_number={row_number} | rows_collected={total_rows} | "
                        f"rows_written={rows_written} | elapsed_s={elapsed:.1f}",
                        flush=True,
                    )
                    batch.clear()
                    _save_csv_checkpoint(checkpoint_path, row_number=row_number, rows_collected=total_rows, rows_written=rows_written)

            print("csv_poll_sleep", flush=True)
            time.sleep(poll_interval_s)

        if batch:
            print(f"csv_final_batch_ready | batch_size={len(batch)}", flush=True)
            if not dry_run:
                _upsert_batch(cur, batch)
            rows_written += len(batch)
            elapsed = time.monotonic() - started_at
            print(
                f"csv_final_flush | row_number={row_number} | rows_collected={total_rows} | "
                f"rows_written={rows_written} | elapsed_s={elapsed:.1f}",
                flush=True,
            )
            _save_csv_checkpoint(checkpoint_path, row_number=row_number, rows_collected=total_rows, rows_written=rows_written)

    if not dry_run:
        conn.commit()

    if checkpoint_path.exists() and not dry_run:
        try:
            checkpoint_path.unlink()
        except OSError:
            pass

    return total_rows, rows_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Instinct document identity rows into Postgres")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--database-url", default="")
    parser.add_argument("--limit-accounts", type=int, default=0)
    parser.add_argument("--limit-patients", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--checkpoint-file", default="")
    parser.add_argument("--csv-file", default="", help="Tail this CSV file and upsert rows as it grows.")
    parser.add_argument("--csv-idle-timeout-s", type=float, default=10.0, help="Stop after this many idle seconds while tailing CSV.")
    parser.add_argument("--csv-poll-interval-s", type=float, default=1.0, help="How often to poll the CSV file while tailing.")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials.")

    db_url = args.database_url.strip() or _build_db_url()
    if args.csv_file.strip():
        checkpoint_path = Path(args.checkpoint_file).expanduser() if args.checkpoint_file.strip() else Path("/tmp/rag_document_identity_csv_tail.checkpoint.json")
        csv_path = Path(args.csv_file).expanduser()
        print(f"csv_mode_start | csv_path={csv_path} | exists={csv_path.exists()} | size={(csv_path.stat().st_size if csv_path.exists() else 0)}", flush=True)
        with psycopg.connect(db_url, row_factory=dict_row) as conn:
            print("db_connected", flush=True)
            rows_collected, rows_written = _stream_csv_rows(
                csv_path=csv_path,
                checkpoint_path=checkpoint_path,
                batch_size=args.batch_size,
                poll_interval_s=args.csv_poll_interval_s,
                idle_timeout_s=args.csv_idle_timeout_s,
                dry_run=args.dry_run,
                conn=conn,
            )
        print(
            {
                "mode": "csv_tail",
                "csv_file": str(csv_path),
                "rows_collected": rows_collected,
                "rows_written": rows_written,
                "dry_run": args.dry_run,
            }
        )
        return 0

    checkpoint_path = Path(args.checkpoint_file).expanduser() if args.checkpoint_file.strip() else Path("/tmp/rag_document_identity_walk.checkpoint.json")
    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.token = adapter.authenticate()
    checkpoint = {"account_index": 1, "patient_index": 1} if args.no_resume else _load_checkpoint(checkpoint_path)

    total_rows = 0
    inserted_or_updated = 0
    started_at = time.monotonic()
    accounts_seen = 0
    patients_seen = 0
    accounts_skipped = 0
    patients_skipped = 0

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            batch: list[tuple[str, str, str, str]] = []

            for account_index, account in enumerate(_iter_accounts(adapter), start=1):
                if account_index < checkpoint["account_index"]:
                    accounts_skipped += 1
                    continue
                if args.limit_accounts and account_index > args.limit_accounts:
                    break
                client_id = _safe(account.get("id"))
                if not client_id:
                    continue
                accounts_seen += 1
                print(f"account_start | account_index={account_index} | accounts_seen={accounts_seen} | rows_collected={total_rows} | rows_written={inserted_or_updated} | client_id={client_id}", flush=True)

                for patient_index, patient in enumerate(_iter_patients_for_account(adapter, client_id), start=1):
                    if account_index == checkpoint["account_index"] and patient_index < checkpoint["patient_index"]:
                        patients_skipped += 1
                        continue
                    if args.limit_patients and patient_index > args.limit_patients:
                        break
                    patient_id = _safe(patient.get("id"))
                    if not patient_id:
                        continue
                    patients_seen += 1
                    print(f"patient_start | account_index={account_index} | patient_index={patient_index} | accounts_seen={accounts_seen} | patients_seen={patients_seen} | rows_collected={total_rows} | rows_written={inserted_or_updated} | client_id={client_id} | patient_id={patient_id}", flush=True)

                    charts = _chart_files_for_patient(adapter, patient_id)
                    for chart in charts:
                        if not isinstance(chart, dict) or chart.get("__typename") != "ChartFile":
                            continue
                        document_pdf_id = _safe(chart.get("id"))
                        originalfilename = _safe(chart.get("filename"))
                        if not document_pdf_id or not originalfilename:
                            continue
                        batch.append((document_pdf_id, client_id, patient_id, originalfilename))
                        total_rows += 1

                        if len(batch) >= args.batch_size:
                            if not args.dry_run:
                                cur.executemany(
                                    """
                                    INSERT INTO rag_document_identity (document_pdf_id, client_id, patient_id, originalfilename)
                                    VALUES (%s, %s, %s, %s)
                                    ON CONFLICT (document_pdf_id) DO UPDATE SET
                                        client_id = EXCLUDED.client_id,
                                        patient_id = EXCLUDED.patient_id,
                                        originalfilename = EXCLUDED.originalfilename
                                    """,
                                    batch,
                                )
                            inserted_or_updated += len(batch)
                            elapsed = time.monotonic() - started_at
                            print(f"batch_flush | rows_collected={total_rows} | rows_written={inserted_or_updated} | elapsed_s={elapsed:.1f}", flush=True)
                            batch.clear()
                            _save_checkpoint(checkpoint_path, account_index=account_index, patient_index=patient_index, rows_collected=total_rows, rows_written=inserted_or_updated)
                    _save_checkpoint(checkpoint_path, account_index=account_index, patient_index=patient_index + 1, rows_collected=total_rows, rows_written=inserted_or_updated)

            if batch:
                if not args.dry_run:
                    cur.executemany(
                        """
                        INSERT INTO rag_document_identity (document_pdf_id, client_id, patient_id, originalfilename)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (document_pdf_id) DO UPDATE SET
                            client_id = EXCLUDED.client_id,
                            patient_id = EXCLUDED.patient_id,
                            originalfilename = EXCLUDED.originalfilename
                        """,
                        batch,
                    )
                inserted_or_updated += len(batch)
                elapsed = time.monotonic() - started_at
                print(f"final_flush | rows_collected={total_rows} | rows_written={inserted_or_updated} | elapsed_s={elapsed:.1f}", flush=True)
                _save_checkpoint(checkpoint_path, account_index=account_index, patient_index=patient_index, rows_collected=total_rows, rows_written=inserted_or_updated)

        if not args.dry_run:
            conn.commit()

    if checkpoint_path.exists() and not args.dry_run:
        try:
            checkpoint_path.unlink()
        except OSError:
            pass

    elapsed = time.monotonic() - started_at
    print(
        {
            "rows_collected": total_rows,
            "rows_written": inserted_or_updated,
            "accounts_seen": accounts_seen,
            "patients_seen": patients_seen,
            "accounts_skipped": accounts_skipped,
            "patients_skipped": patients_skipped,
            "elapsed_s": round(elapsed, 1),
            "checkpoint_file": str(checkpoint_path),
            "dry_run": args.dry_run,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
