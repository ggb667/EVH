from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import instinct_cache_sync_pipeline as pipeline


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.sqls = []
        self.params = None

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self.params = params

    def executemany(self, sql, rows):
        self.sqls.append(sql)
        self.params = list(rows)

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


class FakeClient:
    def __init__(self):
        self.calls = []

    def iter_accounts(self):
        self.calls.append("accounts")
        return ([{"id": "a1", "pimsCode": "11", "primaryContact": {"nameFirst": "Ann", "nameLast": "M"} }], 0.1)

    def _get(self, path, params):
        self.calls.append((path, params))
        return {
            "data": [{"id": 101, "name": "Pet One", "accountId": "a1", "species": {"label": "Canine"}}],
            "metadata": {},
        }


def test_sync_clients_logs_and_upserts():
    conn = FakeConn()
    client = FakeClient()
    lines = []
    summary = pipeline.sync_clients(client, conn, log=lines.append)
    assert summary.fetched == 1
    assert conn.commits == 1
    assert any("clients_fetch_done" in line for line in lines)


def test_sync_patients_logs_and_upserts():
    conn = FakeConn()
    client = FakeClient()
    lines = []
    summary = pipeline.sync_patients(client, conn, log=lines.append)
    assert summary.fetched == 1
    assert conn.commits == 1
    assert any("patients_fetch_done" in line for line in lines)


def test_emit_makes_json():
    lines = []
    pipeline.emit(lines.append, "hello", x=1)
    payload = json.loads(lines[0])
    assert payload["event"] == "hello"
    assert payload["x"] == 1
