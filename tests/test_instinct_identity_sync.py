from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from scripts import instinct_identity_sync as sync


class DummyCursor:
    def __init__(self):
        self.sql = []
        self.rows = []

    def execute(self, sql, params=None):
        self.sql.append((sql.strip(), params))

    def executemany(self, sql, rows):
        self.sql.append((sql.strip(), list(rows)))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyConn:
    def __init__(self):
        self.cursor_obj = DummyCursor()
        self.commit_count = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commit_count += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeClient:
    def __init__(self, accounts=None, patients=None):
        self._accounts = accounts or []
        self._patients = patients or []

    def iter_accounts(self):
        return list(self._accounts), 0.0

    def iter_patients(self):
        return list(self._patients), 0.0


def test_instinct_api_sync_client_pages_accounts_and_patients(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    class DummyResp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        method = req.method
        if method == "POST" and url.endswith("/v1/auth/token"):
            return DummyResp({"access_token": "tok"})
        query = {k: v[-1] for k, v in parse_qs(urlparse(url).query).items()}
        calls.append((url, query))
        if "/v1/accounts" in url:
            if "pageCursor" in url:
                return DummyResp({"data": [{"id": "acct-2"}], "metadata": {"after": None}})
            return DummyResp({"data": [{"id": "acct-1"}], "metadata": {"after": "cursor-1"}})
        if "pageCursor" in url:
            return DummyResp({"data": [{"id": 2}], "metadata": {"after": None}})
        return DummyResp({"data": [{"id": 1}], "metadata": {"after": "cursor-2"}})

    monkeypatch.setattr(sync.urllib_request, "urlopen", fake_urlopen)

    client = sync.InstinctApiSyncClient("https://partner.instinctvet.com", "cid", "secret")
    accounts, _ = client.iter_accounts()
    patients, _ = client.iter_patients()
    assert [row["id"] for row in accounts] == ["acct-1", "acct-2"]
    assert [row["id"] for row in patients] == [1, 2]
    assert calls[0][1]["limit"] == "100"
    assert "pageCursor" in calls[1][1]
    assert calls[2][1]["limit"] == "100"
    assert "pageCursor" in calls[3][1]


def test_account_payload_preserves_deleted_and_updated():
    payload = sync._account_payload(
        {
            "id": "acct-1",
            "pimsCode": "P001",
            "deletedAt": "2026-08-25T12:00:00Z",
            "updatedAt": "2026-08-25T12:34:56Z",
            "primaryContact": {
                "nameFirst": "Deborah",
                "nameLast": "Burchill",
                "communicationDetails": [
                    {"type": "phone", "value": "(555) 555-1212"},
                    {"type": "email", "value": "deb@example.test"},
                ],
            },
        }
    )
    assert payload["account_id"] == "acct-1"
    assert payload["owner_name"] == "Deborah Burchill"
    assert payload["updated_at"].isoformat().startswith("2026-08-25T12:34:56")
    assert payload["deleted_at"].isoformat().startswith("2026-08-25T12:00:00")
    assert payload["merged_into_account_id"] is None


def test_patient_payload_preserves_merge_and_deleted():
    payload = sync._patient_payload(
        {
            "id": 7,
            "accountId": "acct-1",
            "name": "Milo",
            "pimsCode": "PET007",
            "updatedAt": "2026-08-25T12:34:56Z",
            "deletedAt": "2026-08-25T13:00:00Z",
            "mergedIntoPatientId": 9,
            "species": {"label": "Canine"},
            "breed": {"label": "Poodle"},
            "weight": 13.2,
            "account": {
                "primaryContact": {
                    "nameFirst": "Deborah",
                    "nameLast": "Burchill",
                    "communicationDetails": [{"type": "phone", "value": "555-1212"}],
                }
            },
        }
    )
    assert payload["patient_id"] == 7
    assert payload["account_id"] == "acct-1"
    assert payload["patient_name"] == "Milo"
    assert payload["merged_into_patient_id"] == 9
    assert payload["deleted_at"].isoformat().startswith("2026-08-25T13:00:00")


def test_refresh_identity_tables_builds_and_swaps_atomically(monkeypatch):
    conn = DummyConn()
    client = FakeClient(
        accounts=[
            {"id": "acct-1", "pimsCode": "P001", "updatedAt": "2026-08-25T12:34:56Z", "primaryContact": {"nameFirst": "Alpha", "nameLast": "One"}},
        ],
        patients=[
            {"id": 11, "accountId": "acct-1", "name": "Milo", "updatedAt": "2026-08-25T12:34:56Z", "account": {"primaryContact": {"nameFirst": "Alpha", "nameLast": "One"}}},
        ]
    )
    result = sync.refresh_identity_tables(client, conn)
    assert result["accounts"]["count"] == 1
    assert result["patients"]["count"] == 1
    assert conn.commit_count >= 2
    sql = [stmt for stmt, _ in conn.cursor_obj.sql]
    assert any("CREATE TABLE public.instinct_owner_lookup_refresh" in stmt for stmt in sql)
    assert any("TRUNCATE public.instinct_owner_lookup, public.instinct_patient_lookup" in stmt for stmt in sql)
    assert any("INSERT INTO public.instinct_owner_lookup_refresh" in stmt for stmt in sql)
    assert any("INSERT INTO public.instinct_patient_lookup_refresh" in stmt for stmt in sql)


def test_refresh_failure_leaves_previous_live_dataset_intact(monkeypatch):
    conn = DummyConn()
    client = FakeClient(
        accounts=[{"id": "acct-1", "updatedAt": "2026-08-25T12:34:56Z", "primaryContact": {"nameFirst": "Alpha", "nameLast": "One"}}],
        patients=[{"id": 11, "accountId": "acct-1", "name": "Milo", "updatedAt": "2026-08-25T12:34:56Z"}],
    )
    monkeypatch.setattr(sync, "_replace_live_tables", lambda conn: (_ for _ in ()).throw(RuntimeError("swap failed")))
    with pytest.raises(RuntimeError):
        sync.refresh_identity_tables(client, conn)
    sql = [stmt for stmt, _ in conn.cursor_obj.sql]
    assert not any("TRUNCATE public.instinct_owner_lookup, public.instinct_patient_lookup" in stmt for stmt in sql)
