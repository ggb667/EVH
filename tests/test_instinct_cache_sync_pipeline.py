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


def test_sync_documents_records_timeout_and_continues(monkeypatch):
    class DocumentCursor(FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if "select patient_id" in sql.lower():
                self.rows = [{"patient_id": "1"}]
            elif "select document_pdf_id" in sql.lower():
                self.rows = []
            else:
                self.rows = []

    class DocumentConn(FakeConn):
        def __init__(self):
            self.cursor_obj = DocumentCursor()
            self.commits = 0

    class DocumentClient:
        def _auth(self):
            return "token"

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def post(_url, *, json, **_kwargs):
        if str(json.get("query") or "").startswith("mutation"):
            doc_id = str((json.get("variables") or {}).get("id"))
            return Response({"data": {"createChartFileUrl": f"https://example.test/{doc_id}.pdf"}})
        return Response(
            {
                "data": {
                    "patient": {"id": "1", "account": {"id": "client-1"}},
                    "charts": [
                        {"id": "101", "filename": "timeout.pdf", "__typename": "ChartFile"},
                        {"id": "102", "filename": "success.pdf", "__typename": "ChartFile"},
                    ],
                }
            }
        )

    calls = []

    def chunk_patient_pdf_timed(source, *_args, **_kwargs):
        calls.append(source.pdf_id)
        if source.pdf_id == "101":
            raise TimeoutError("OCR PDF size-scaled deadline exceeded")
        return [object()], 1, {}

    monkeypatch.setenv("TOKEN", "token")
    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr("scripts.instinct_pdf_chunker.chunk_patient_pdf_timed", chunk_patient_pdf_timed)
    monkeypatch.setattr("scripts.instinct_pdf_chunker.load_into_postgres", lambda **_kwargs: (0.0, 0.0))
    monkeypatch.setattr(pipeline, "_db_url", lambda: "postgresql://unused")
    lines = []

    summary = pipeline.sync_documents(
        DocumentClient(),
        DocumentConn(),
        log=lines.append,
        run_id="run-timeout-test",
    )

    assert calls == ["101", "102"]
    assert summary.documents_failed == 1
    assert summary.documents_ingested == 1
    events = [json.loads(line) for line in lines]
    failure = next(event for event in events if event.get("event") == "document_ingestion_failed")
    assert failure["document_pdf_id"] == "101"
    assert failure["run_id"] == "run-timeout-test"
    assert failure["stage"] == "ocr"
    assert failure["failure_type"] == "timeout"
    assert failure["terminal"] is True
    assert failure["continuation"] == "next_document"
    assert any(event.get("event") == "new_document_processed" and event.get("document_pdf_id") == "102" for event in events)
