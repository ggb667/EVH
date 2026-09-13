#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from scripts.instinct_cache_sync_pipeline import connect_db, emit, sync_clients
from scripts.instinct_identity_sync import InstinctApiSyncClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 1.1: sync Instinct clients into the owner cache")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--client-id", default=os.environ.get("INSTINCT_CLIENT_ID", ""))
    parser.add_argument("--client-secret", default=os.environ.get("INSTINCT_CLIENT_SECRET", ""))
    parser.add_argument("--log-file", default="etl_logs/instinct_step1_1_clients.log")
    args = parser.parse_args()
    log_path = Path(args.log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as logf:
        def log(line: str) -> None:
            print(line, flush=True)
            print(line, file=logf, flush=True)

        emit(log, "step_start", step="1.1", log_file=str(log_path))
        client = InstinctApiSyncClient(args.base_url, args.client_id, args.client_secret)
        with connect_db() as conn:
            summary = sync_clients(client, conn, log=log)
        emit(log, "step_done", step="1.1", **summary.__dict__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
