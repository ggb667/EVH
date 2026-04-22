from __future__ import annotations

import csv
from pathlib import Path

from scripts.instinct_accounts import normalize_account, project_account_to_weave_contact
from scripts.instinct_partner_client import InstinctPartnerClient
from scripts.weave_contact_sync import (
    SyncState,
    WeaveCsvContactDestination,
    build_account_query,
    choose_event_timestamp,
    compute_updated_since,
    projection_to_weave_csv_row,
    run_contact_sync,
)


class InMemoryStateStore:
    def __init__(self, updated_since: str | None = None, exported_hashes: dict[str, str] | None = None) -> None:
        self.state = SyncState(updated_since=updated_since, exported_hashes=exported_hashes or {})
        self.saved: list[SyncState] = []

    def load(self) -> SyncState:
        return self.state

    def save(self, state: SyncState) -> None:
        self.state = state
        self.saved.append(state)


def _read_csv_rows(path: str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_project_account_to_weave_contact_marks_deleted_accounts_inactive():
    normalized = normalize_account(
        {
            "id": "acct-1",
            "pimsCode": "9758",
            "primaryContact": {
                "nameFirst": "Nathan",
                "nameLast": "Deschenes",
                "communicationDetails": [
                    {"type": "mobile", "value": "(555) 010-1212"},
                    {"type": "email", "value": "nathan@example.com"},
                ],
            },
            "updatedAt": "2026-04-20T12:00:00Z",
            "deletedAt": "2026-04-21T08:00:00Z",
        }
    )

    projection = project_account_to_weave_contact(normalized, "evh-main")

    assert projection.clinic_id == "evh-main"
    assert projection.display_name == "Nathan Deschenes"
    assert projection.primary_phone == "5550101212"
    assert projection.email == "nathan@example.com"
    assert projection.is_active is False
    assert projection.deleted_at == "2026-04-21T08:00:00Z"
    assert projection.payload_hash


def test_projection_to_weave_csv_row_maps_required_fields():
    projection = project_account_to_weave_contact(
        normalize_account(
            {
                "id": "acct-1",
                "pimsCode": "9758",
                "primaryContact": {
                    "nameFirst": "Nathan",
                    "nameLast": "Deschenes",
                    "communicationDetails": [{"type": "mobile", "value": "(555) 010-1212"}],
                },
            }
        ),
        "evh-main",
    )

    assert projection_to_weave_csv_row(projection) == {
        "unique_id": "acct-1",
        "first_name": "Nathan",
        "last_name": "Deschenes",
        "mobile_phone": "5550101212",
        "home_phone": "",
        "work_phone": "",
        "email": "",
        "gender": "",
        "date_of_birth": "",
    }


def test_compute_updated_since_applies_overlap_window():
    assert compute_updated_since("2026-04-21T10:05:00Z", 300) == "2026-04-21T10:00:00Z"


def test_build_account_query_includes_deleted_filters():
    assert build_account_query("2026-04-21T10:05:00Z", 300) == {
        "includeDeleted": True,
        "updatedSince": "2026-04-21T10:00:00Z",
        "deletedSince": "2026-04-21T10:00:00Z",
    }


def test_choose_event_timestamp_prefers_latest_deleted_or_updated_time():
    normalized = normalize_account(
        {
            "id": "acct-1",
            "pimsCode": "9758",
            "primaryContact": {},
            "updatedAt": "2026-04-20T12:00:00Z",
            "deletedAt": "2026-04-21T08:00:00Z",
        }
    )

    assert choose_event_timestamp(normalized) == "2026-04-21T08:00:00Z"


def test_run_contact_sync_exports_only_changed_contacts_and_advances_watermark(monkeypatch, tmp_path):
    client = InstinctPartnerClient("https://partner.instinctvet.com", "token")
    destination = WeaveCsvContactDestination(str(tmp_path), chunk_size=10, file_prefix="contacts")
    unchanged_projection = project_account_to_weave_contact(
        normalize_account(
            {
                "id": "acct-1",
                "pimsCode": "9758",
                "pimsId": "stable-1",
                "primaryContact": {
                    "nameFirst": "Nathan",
                    "nameLast": "Deschenes",
                    "communicationDetails": [{"type": "mobile", "value": "(555) 010-1212"}],
                },
                "updatedAt": "2026-04-21T10:07:00Z",
            }
        ),
        "evh-main",
    )
    state_store = InMemoryStateStore(
        updated_since="2026-04-21T10:05:00Z",
        exported_hashes={"acct-1": unchanged_projection.payload_hash},
    )
    calls: list[dict[str, object]] = []

    def fake_iter_accounts(self, params=None, limit=100):
        calls.append(dict(params or {}))
        return iter(
            [
                {
                    "id": "acct-1",
                    "pimsCode": "9758",
                    "pimsId": "stable-1",
                    "primaryContact": {
                        "nameFirst": "Nathan",
                        "nameLast": "Deschenes",
                        "communicationDetails": [{"type": "mobile", "value": "(555) 010-1212"}],
                    },
                    "updatedAt": "2026-04-21T10:07:00Z",
                },
                {
                    "id": "acct-2",
                    "pimsCode": "9759",
                    "primaryContact": {
                        "nameFirst": "Greg",
                        "nameLast": "Test",
                        "communicationDetails": [{"type": "email", "value": "greg@example.com"}],
                    },
                    "updatedAt": "2026-04-21T10:06:00Z",
                    "deletedAt": "2026-04-21T10:08:00Z",
                },
            ]
        )

    monkeypatch.setattr(InstinctPartnerClient, "iter_accounts", fake_iter_accounts)

    stats = run_contact_sync(client, "evh-main", state_store, destination, overlap_seconds=300)

    assert calls == [
        {
            "includeDeleted": True,
            "updatedSince": "2026-04-21T10:00:00Z",
            "deletedSince": "2026-04-21T10:00:00Z",
        }
    ]
    assert stats.scanned == 2
    assert stats.exported == 1
    assert stats.skipped_unchanged == 1
    assert stats.inactive == 1
    assert stats.watermark_out == "2026-04-21T10:08:00Z"
    assert len(stats.files_written) == 1
    assert state_store.saved == [
        SyncState(
            updated_since="2026-04-21T10:08:00Z",
            exported_hashes={
                "acct-1": unchanged_projection.payload_hash,
                "acct-2": state_store.state.exported_hashes["acct-2"],
            },
        )
    ]
    assert _read_csv_rows(stats.files_written[0]) == [
        {
            "unique_id": "acct-2",
            "first_name": "Greg",
            "last_name": "Test",
            "mobile_phone": "",
            "home_phone": "",
            "work_phone": "",
            "email": "greg@example.com",
            "gender": "",
            "date_of_birth": "",
        }
    ]


def test_csv_destination_chunks_large_exports(tmp_path):
    destination = WeaveCsvContactDestination(str(tmp_path), chunk_size=2, file_prefix="contacts")

    for account_id in ("acct-1", "acct-2", "acct-3"):
        projection = project_account_to_weave_contact(
            normalize_account(
                {
                    "id": account_id,
                    "pimsCode": account_id,
                    "primaryContact": {"nameFirst": account_id, "nameLast": "Owner"},
                }
            ),
            "evh-main",
        )
        destination.upsert(projection.__dict__)

    files = destination.finalize()

    assert len(files) == 2
    assert [row["unique_id"] for row in _read_csv_rows(files[0])] == ["acct-1", "acct-2"]
    assert [row["unique_id"] for row in _read_csv_rows(files[1])] == ["acct-3"]
