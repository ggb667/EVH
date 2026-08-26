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

    def iter_accounts(self, updated_since):
        return list(self._accounts)

    def iter_patients(self, updated_since):
        return list(self._patients)


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
    assert [row["id"] for row in client.iter_accounts("2026-08-01T00:00:00Z")] == ["acct-1", "acct-2"]
    assert [row["id"] for row in client.iter_patients("2026-08-01T00:00:00Z")] == [1, 2]
    assert calls[0][1]["updatedSince"] == "2026-08-01T00:00:00Z"
    assert "pageCursor" in calls[1][1]
    assert calls[2][1]["updatedSince"] == "2026-08-01T00:00:00Z"
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


def test_sync_accounts_commits_before_advancing_watermark(monkeypatch, tmp_path):
    conn = DummyConn()
    client = FakeClient(
        accounts=[
            {"id": "acct-1", "pimsCode": "P001", "updatedAt": "2026-08-25T12:34:56Z", "primaryContact": {"nameFirst": "Alpha", "nameLast": "One"}},
        ]
    )
    watermark = sync.sync_accounts(client, conn, None)
    assert conn.commit_count == 1
    assert watermark == "2026-08-25T12:34:56Z"
    assert "INSERT INTO public.instinct_owner_lookup" in conn.cursor_obj.sql[0][0]


def test_sync_patients_commits_before_advancing_watermark():
    conn = DummyConn()
    client = FakeClient(
        patients=[
            {"id": 11, "accountId": "acct-1", "name": "Milo", "updatedAt": "2026-08-25T12:34:56Z", "account": {"primaryContact": {"nameFirst": "Alpha", "nameLast": "One"}}},
        ]
    )
    watermark = sync.sync_patients(client, conn, None)
    assert conn.commit_count == 1
    assert watermark == "2026-08-25T12:34:56Z"
    assert "INSERT INTO public.instinct_patient_lookup" in conn.cursor_obj.sql[0][0]


def test_main_does_not_advance_watermark_on_failure(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"accounts_watermark": "old", "patients_watermark": "old"}))

    monkeypatch.setenv("INSTINCT_CLIENT_ID", "cid")
    monkeypatch.setenv("INSTINCT_CLIENT_SECRET", "secret")

    class DummySyncClient:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(sync, "InstinctApiSyncClient", DummySyncClient)
    monkeypatch.setattr(sync, "_connect", lambda: DummyConn())

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(sync, "sync_accounts", boom)
    with pytest.raises(RuntimeError):
        sync.main(["--state-file", str(state), "--accounts-only", "--base-url", "https://partner.instinctvet.com"])
    saved = json.loads(state.read_text())
    assert saved["accounts_watermark"] == "old"


def test_sync_main_writes_watermarks_after_success(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    monkeypatch.setenv("INSTINCT_CLIENT_ID", "cid")
    monkeypatch.setenv("INSTINCT_CLIENT_SECRET", "secret")

    class DummySyncClient:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(sync, "InstinctApiSyncClient", DummySyncClient)
    monkeypatch.setattr(sync, "_connect", lambda: DummyConn())
    monkeypatch.setattr(sync, "sync_accounts", lambda client, conn, watermark: "acct-watermark")
    monkeypatch.setattr(sync, "sync_patients", lambda client, conn, watermark: "pat-watermark")
    code = sync.main(["--state-file", str(state), "--base-url", "https://partner.instinctvet.com"])
    assert code == 0
    saved = json.loads(state.read_text())
    assert saved["accounts_watermark"] == "acct-watermark"
    assert saved["patients_watermark"] == "pat-watermark"
