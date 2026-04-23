from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from scripts.instinct_accounts import NormalizedAccount, WeaveContactProjection, normalize_account, project_account_to_weave_contact
from scripts.instinct_partner_client import InstinctPartnerClient

WEAVE_IMPORT_COLUMNS = (
    "unique_id",
    "first_name",
    "last_name",
    "mobile_phone",
    "home_phone",
    "work_phone",
    "email",
    "gender",
    "date_of_birth",
)


def _parse_iso8601(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def _format_iso8601(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_updated_since(watermark: Optional[str], overlap_seconds: int) -> Optional[str]:
    if not watermark:
        return None
    return _format_iso8601(_parse_iso8601(watermark) - timedelta(seconds=overlap_seconds))


def build_account_query(watermark: Optional[str], overlap_seconds: int) -> dict[str, Any]:
    query: dict[str, Any] = {"includeDeleted": "true"}
    updated_since = compute_updated_since(watermark, overlap_seconds)
    if updated_since:
        query["updatedSince"] = updated_since
        query["deletedSince"] = updated_since
    return query


def choose_event_timestamp(account: NormalizedAccount) -> Optional[str]:
    candidates = [value for value in (account.updated_at, account.deleted_at) if value]
    if not candidates:
        return None
    return max(candidates, key=_parse_iso8601)


def projection_to_weave_csv_row(projection: WeaveContactProjection) -> dict[str, str]:
    return {
        "unique_id": projection.source_account_id,
        "first_name": projection.first_name,
        "last_name": projection.last_name,
        "mobile_phone": projection.primary_phone,
        "home_phone": "",
        "work_phone": "",
        "email": projection.email or "",
        "gender": "",
        "date_of_birth": "",
    }


@dataclass
class SyncState:
    updated_since: Optional[str] = None
    exported_hashes: dict[str, str] = field(default_factory=dict)


class SyncStateStore(Protocol):
    def load(self) -> SyncState: ...

    def save(self, state: SyncState) -> None: ...


class JsonFileSyncStateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> SyncState:
        if not self.path.exists():
            return SyncState()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        exported_hashes = payload.get("exported_hashes")
        if not isinstance(exported_hashes, dict):
            exported_hashes = {}
        return SyncState(
            updated_since=payload.get("updated_since"),
            exported_hashes={str(key): str(value) for key, value in exported_hashes.items()},
        )

    def save(self, state: SyncState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ContactDestination(Protocol):
    def upsert(self, payload: dict[str, Any]) -> None: ...

    def finalize(self) -> list[str]: ...


class WeaveCsvContactDestination:
    def __init__(self, export_dir: str, *, chunk_size: int = 10000, file_prefix: str = "weave_contacts") -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size = max(1, chunk_size)
        self.file_prefix = file_prefix
        self._rows: list[dict[str, str]] = []
        self._written_files: list[str] = []

    def upsert(self, payload: dict[str, Any]) -> None:
        self._rows.append(projection_to_weave_csv_row(WeaveContactProjection(**payload)))

    def finalize(self) -> list[str]:
        self._written_files = []
        if not self._rows:
            return []

        for start in range(0, len(self._rows), self.chunk_size):
            batch = self._rows[start : start + self.chunk_size]
            path = self.export_dir / f"{self.file_prefix}_{(start // self.chunk_size) + 1:03d}.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=WEAVE_IMPORT_COLUMNS)
                writer.writeheader()
                writer.writerows(batch)
            self._written_files.append(str(path))
        return list(self._written_files)


@dataclass(frozen=True)
class SyncStats:
    scanned: int
    exported: int
    skipped_unchanged: int
    inactive: int
    files_written: list[str]
    watermark_out: Optional[str]


def run_contact_sync(
    client: InstinctPartnerClient,
    clinic_id: str,
    state_store: SyncStateStore,
    destination: ContactDestination,
    *,
    overlap_seconds: int = 300,
) -> SyncStats:
    state = state_store.load()
    query = build_account_query(state.updated_since, overlap_seconds)
    scanned = 0
    exported = 0
    skipped_unchanged = 0
    inactive = 0
    watermark_out = state.updated_since
    next_hashes = dict(state.exported_hashes)

    for raw_account in client.iter_accounts(query):
        scanned += 1
        normalized = normalize_account(raw_account)
        projection = project_account_to_weave_contact(normalized, clinic_id)
        if next_hashes.get(projection.source_account_id) == projection.payload_hash:
            skipped_unchanged += 1
        else:
            destination.upsert(asdict(projection))
            next_hashes[projection.source_account_id] = projection.payload_hash
            exported += 1
            if not projection.is_active:
                inactive += 1
        event_timestamp = choose_event_timestamp(normalized)
        if event_timestamp and (watermark_out is None or _parse_iso8601(event_timestamp) > _parse_iso8601(watermark_out)):
            watermark_out = event_timestamp

    files_written = destination.finalize()
    if watermark_out != state.updated_since or next_hashes != state.exported_hashes:
        state_store.save(SyncState(updated_since=watermark_out, exported_hashes=next_hashes))

    return SyncStats(
        scanned=scanned,
        exported=exported,
        skipped_unchanged=skipped_unchanged,
        inactive=inactive,
        files_written=files_written,
        watermark_out=watermark_out,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export incremental Instinct contacts into Weave-ready CSV files.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--clinic-id", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--chunk-size", type=int, default=10000)
    parser.add_argument("--file-prefix", default="weave_contacts")
    parser.add_argument("--overlap-seconds", type=int, default=300)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    client = InstinctPartnerClient(args.base_url, args.token)
    state_store = JsonFileSyncStateStore(args.state_file)
    destination = WeaveCsvContactDestination(args.export_dir, chunk_size=args.chunk_size, file_prefix=args.file_prefix)
    stats = run_contact_sync(
        client,
        args.clinic_id,
        state_store,
        destination,
        overlap_seconds=args.overlap_seconds,
    )
    print(json.dumps(asdict(stats), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
