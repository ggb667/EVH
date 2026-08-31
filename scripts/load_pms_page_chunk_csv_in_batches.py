#!/usr/bin/env python3
"""Load pms_page_chunk CSV rows in batches with per-row recovery.

This avoids a single malformed CSV row or COPY parser issue from killing the
entire import. Rows are read with Python's CSV parser, then inserted in
batches. If a row fails to insert, the loader logs it, applies a small inline
repair pass, and skips forward instead of aborting the run. Commits happen on a
larger interval so the import stays fast without losing everything on one
failure.
"""

from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import quote

import psycopg


@dataclass(frozen=True)
class CsvRow:
    row_number: int
    source_name: str
    source_uri: str
    page_number: int
    chunk_index: int
    chunk_text: str
    chunk_hash: str
    embedding: str
    metadata: str


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


def _coerce_row(row_number: int, raw: list[str]) -> CsvRow | None:
    if len(raw) != 8:
        return None
    try:
        return CsvRow(
            row_number=row_number,
            source_name=raw[0],
            source_uri=raw[1],
            page_number=int(raw[2]),
            chunk_index=int(raw[3]),
            chunk_text=raw[4],
            chunk_hash=raw[5],
            embedding=raw[6],
            metadata=raw[7],
        )
    except Exception:
        return None


def _iter_csv_rows(path: Path) -> Iterator[CsvRow]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            return
        for row_number, raw in enumerate(reader, start=2):
            row = _coerce_row(row_number, raw)
            if row is not None:
                yield row
                continue
            # A small inline repair pass: if csv.reader split a logical record
            # badly, try to keep going by stripping NULs and balancing quotes.
            joined = ",".join(raw).replace("\x00", "")
            if joined.count('"') % 2 == 1:
                joined += '"'
            try:
                repaired = next(csv.reader([joined]))
                row = _coerce_row(row_number, repaired)
                if row is not None:
                    yield row
                    continue
            except Exception:
                pass
            print(f"skip_bad_row row={row_number} raw_columns={len(raw)}", flush=True)


def _batched(rows: Iterable[CsvRow], batch_size: int) -> Iterator[list[CsvRow]]:
    batch: list[CsvRow] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Load pms_page_chunk CSV rows in batches with periodic commits.")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--table-name", default="pms_page_chunk")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--commit-interval", type=int, default=10000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        args.database_url = _build_db_url()

    csv_path = Path(args.csv_path)
    conn = psycopg.connect(args.database_url, connect_timeout=30)
    conn.autocommit = False
    inserted = 0
    skipped = 0
    pending_in_txn = 0
    try:
        with conn.cursor() as cur:
            for batch_number, batch in enumerate(_batched(_iter_csv_rows(csv_path), max(1, args.batch_size)), start=1):
                print(f"batch_start batch={batch_number} rows={len(batch)} inserted={inserted} skipped={skipped}", flush=True)
                for row in batch:
                    if args.dry_run:
                        inserted += 1
                        print(f"row_ok row={row.row_number} chunk_index={row.chunk_index} inserted={inserted} dry_run=1", flush=True)
                        continue
                    try:
                        cur.execute("SAVEPOINT pms_page_chunk_row")
                        cur.execute(
                            f"""
                            INSERT INTO {args.table_name} (
                                source_name,
                                source_uri,
                                page_number,
                                chunk_index,
                                chunk_text,
                                chunk_hash,
                                embedding,
                                metadata
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (chunk_hash) DO UPDATE SET
                                source_uri = EXCLUDED.source_uri,
                                page_number = EXCLUDED.page_number,
                                chunk_index = EXCLUDED.chunk_index,
                                chunk_text = EXCLUDED.chunk_text,
                                embedding = EXCLUDED.embedding,
                                metadata = EXCLUDED.metadata
                            """,
                            (
                                row.source_name,
                                row.source_uri,
                                row.page_number,
                                row.chunk_index,
                                row.chunk_text,
                                row.chunk_hash,
                                row.embedding,
                                row.metadata,
                            ),
                        )
                        inserted += 1
                        pending_in_txn += 1
                        if pending_in_txn >= max(1, args.commit_interval):
                            conn.commit()
                            pending_in_txn = 0
                            print(f"commit_done inserted={inserted} skipped={skipped}", flush=True)
                        print(f"row_ok row={row.row_number} chunk_index={row.chunk_index} inserted={inserted}", flush=True)
                    except Exception as exc:
                        skipped += 1
                        try:
                            cur.execute("ROLLBACK TO SAVEPOINT pms_page_chunk_row")
                        except Exception:
                            conn.rollback()
                            pending_in_txn = 0
                        print(
                            f"row_fail row={row.row_number} chunk_index={row.chunk_index} error={type(exc).__name__}: {exc}",
                            flush=True,
                        )
                        continue
                print(f"batch_done batch={batch_number} inserted={inserted} skipped={skipped}", flush=True)
        if pending_in_txn > 0 and not args.dry_run:
            conn.commit()
            print(f"commit_done inserted={inserted} skipped={skipped}", flush=True)
        print(f"load_complete inserted={inserted} skipped={skipped}", flush=True)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
