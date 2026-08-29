from __future__ import annotations

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from scripts.instinct_accounts import normalize_account
from scripts.instinct_appointments import normalize_appointment
from scripts.instinct_partner_client import InstinctPartnerClient


@dataclass
class SyncState:
    feed: str
    watermark_in: str | None
    watermark_out: str | None
    record_count: int
    records: list[dict[str, Any]]


@dataclass
class ExportRecord:
    source_system: str
    source_id: str
    source_type: str
    idempotency_key: str
    conflict_status: str
    payload: dict[str, Any]


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True, default=str))


def _state_key(feed: str) -> str:
    return f"{feed}_watermark"


def _stable_hash(value: dict[str, Any]) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _build_idempotency_key(source_type: str, source_id: str, watermark_in: str | None) -> str:
    basis = {"source_type": source_type, "source_id": source_id, "watermark_in": watermark_in}
    return _stable_hash(basis)


def _wrap_export(feed: str, source_id: str, watermark_in: str | None, payload: dict[str, Any], conflict_status: str) -> dict[str, Any]:
    return asdict(
        ExportRecord(
            source_system="instinct",
            source_id=source_id,
            source_type=feed[:-1] if feed.endswith("s") else feed,
            idempotency_key=_build_idempotency_key(feed, source_id, watermark_in),
            conflict_status=conflict_status,
            payload=payload,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run Instinct account and appointment sync feeds")
    parser.add_argument("--base-url", required=True, help="Instinct API base URL")
    parser.add_argument("--token", required=True, help="Bearer token for Instinct Partner API")
    parser.add_argument("--updated-since", help="Incremental watermark in ISO 8601 format")
    parser.add_argument("--state-file", type=Path, help="JSON file used to persist feed watermarks")
    parser.add_argument("--limit", type=int, default=100, help="Page size for list endpoints")
    parser.add_argument("--accounts", action="store_true", help="Include account feed")
    parser.add_argument("--appointments", action="store_true", help="Include appointment feed")
    parser.add_argument("--fetch-types", action="store_true", help="Fetch appointment type details for each appointment")
    parser.add_argument("--max-records", type=int, default=20, help="Maximum records per feed for dry-run output")
    parser.add_argument("--export-json", type=Path, help="Write structured export records to a JSON file")
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.accounts and not args.appointments:
        parser.error("Select at least one feed: --accounts and/or --appointments.")

    client = InstinctPartnerClient(args.base_url, args.token)
    persisted_state = load_state(args.state_file) if args.state_file else {}
    export_bundle: dict[str, list[dict[str, Any]]] = {}

    if args.accounts:
        watermark_in = args.updated_since or persisted_state.get(_state_key("accounts"))
        filters = {}
        if watermark_in:
            filters["updatedSince"] = watermark_in
        account_rows = []
        for record in client.iter_accounts(filters, limit=args.limit):
            normalized = asdict(normalize_account(record))
            normalized["source_hash"] = _stable_hash(normalized)
            account_rows.append(normalized)
            if len(account_rows) >= args.max_records:
                break
        watermark_out = watermark_in
        state = SyncState(
            feed="accounts",
            watermark_in=watermark_in,
            watermark_out=watermark_out,
            record_count=len(account_rows),
            records=account_rows,
        )
        print(json.dumps(asdict(state), indent=2, default=str))
        export_bundle["accounts"] = [
            _wrap_export("accounts", row["account_id"], watermark_in, row, "clear") for row in account_rows
        ]
        if args.state_file:
            persisted_state[_state_key("accounts")] = watermark_out
            save_state(args.state_file, persisted_state)

    if args.appointments:
        watermark_in = args.updated_since or persisted_state.get(_state_key("appointments"))
        filters = {}
        if watermark_in:
            filters["updatedSince"] = watermark_in
        appointment_rows = []
        for record in client.iter_appointments(filters, limit=args.limit):
            normalized = asdict(normalize_appointment(record))
            if args.fetch_types and normalized.get("appointment_type_id"):
                try:
                    normalized["appointment_type"] = client.fetch_appointment_type(int(normalized["appointment_type_id"]))
                except ValueError:
                    normalized["appointment_type"] = None
            normalized["source_hash"] = _stable_hash(normalized)
            normalized["conflict_status"] = "clear" if not normalized.get("is_canceled") else "needs_review"
            appointment_rows.append(normalized)
            if len(appointment_rows) >= args.max_records:
                break
        watermark_out = watermark_in
        state = SyncState(
            feed="appointments",
            watermark_in=watermark_in,
            watermark_out=watermark_out,
            record_count=len(appointment_rows),
            records=appointment_rows,
        )
        print(json.dumps(asdict(state), indent=2, default=str))
        export_bundle["appointments"] = [
            _wrap_export("appointments", row["appointment_id"], watermark_in, row, row["conflict_status"])
            for row in appointment_rows
        ]
        if args.state_file:
            persisted_state[_state_key("appointments")] = watermark_out
            save_state(args.state_file, persisted_state)

    if args.export_json:
        args.export_json.write_text(json.dumps(export_bundle, indent=2, sort_keys=True, default=str))

    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
