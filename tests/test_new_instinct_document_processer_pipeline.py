from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.new_instinct_document_processer_pipeline import build_missing_worklist, MissingWorkItem


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def cursor(self, row_factory=None):
        return self.cursor_obj


def test_build_missing_worklist_orders_and_filters_missing_only():
    conn = FakeConn(
        [
            {"document_pdf_id": "200", "client_id": "c1", "patient_id": "p1", "originalfilename": "a.pdf", "chunk_count": 0},
            {"document_pdf_id": "100", "client_id": "c1", "patient_id": "p1", "originalfilename": "b.pdf", "chunk_count": 0},
        ]
    )

    rows = build_missing_worklist(conn)

    assert rows == [
        MissingWorkItem(document_pdf_id="200", client_id="c1", patient_id="p1", originalfilename="a.pdf", chunk_count=0),
        MissingWorkItem(document_pdf_id="100", client_id="c1", patient_id="p1", originalfilename="b.pdf", chunk_count=0),
    ]
    assert "HAVING COUNT(p.id) = 0" in conn.cursor_obj.sql


def test_build_missing_worklist_applies_filters():
    conn = FakeConn([])

    build_missing_worklist(conn, client_id="c9", patient_id="p2")

    assert conn.cursor_obj.params == ["c9", "p2"]
    assert "i.client_id = %s" in conn.cursor_obj.sql
    assert "i.patient_id = %s" in conn.cursor_obj.sql
