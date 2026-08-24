import json
import os
import time

import pytest
import lambda_app as app


def event(path, method="GET", params=None, body=None):
    return {"rawPath": path, "queryStringParameters": params or {}, "body": json.dumps(body) if body is not None else None,
            "requestContext": {"http": {"method": method}}}


def test_index_is_single_static_page_and_loads_clients_once():
    html = open(app.INDEX_PATH, encoding="utf-8").read()
    assert 'api("/api/options?kind=client")' in html
    assert 'function localFilter(' in html
    # Input handlers must filter state already in the browser, not refetch clients.
    client_handler = html.split('$("client-input").addEventListener("input"', 1)[1].split('});', 1)[0]
    assert "/api/clients" not in client_handler
    assert "/api/pets" not in client_handler


def test_embedding_search_is_patient_scoped_and_vector_based(monkeypatch):
    executed = {}
    class Cursor:
        def execute(self, sql, params): executed.update(sql=sql, params=params)
        def fetchall(self): return [("doc1", "record.pdf", 3, "src", "https://example.test/r.pdf", "dental text", {}, 0.1)]
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass
    monkeypatch.setattr(app, "_pg_connect", lambda: Connection())
    monkeypatch.setattr(app, "_embed", lambda q: [0.1, 0.2])
    hits = app.search_patient_chunks("client-1", "patient-2", "dental")
    sql = executed["sql"].lower()
    assert "embedding <=> %s::vector" in sql
    assert "client_instinct_uuid = %s" in sql
    assert "patient_id = %s" in sql
    assert "ilike" not in sql
    assert executed["params"] == ("[0.10000000,0.20000000]", "client-1", "patient-2", "[0.10000000,0.20000000]")
    assert hits[0]["document_id"] == "doc1" and hits[0]["page_number"] == 3


def test_embedding_search_is_not_capped_at_20(monkeypatch):
    executed = {}
    rows = [
        (f"doc{i}", f"record-{i}.pdf", i, "src", "https://example.test/r.pdf", f"text {i}", {}, 0.01 * i)
        for i in range(1, 22)
    ]

    class Cursor:
        def execute(self, sql, params): executed.update(sql=sql, params=params)
        def fetchall(self): return rows
        def close(self): pass

    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass

    monkeypatch.setattr(app, "_pg_connect", lambda: Connection())
    monkeypatch.setattr(app, "_embed", lambda q: [0.1, 0.2])
    hits = app.search_patient_chunks("client-1", "patient-2", "dental")
    assert len(hits) == 21
    assert hits[-1]["document_id"] == "doc21"
    assert "limit" not in executed["sql"].lower()


def test_llm_cannot_invent_reference(monkeypatch):
    monkeypatch.setattr(app, "load_patient_documents", lambda c, p: [{"document_id": "doc1", "title": "record.pdf", "source_uri": "https://example.test/r.pdf"}])
    monkeypatch.setattr(app, "search_patient_chunks", lambda c, p, q: [{"document_id":"doc1","document_title":"record.pdf","page_number":3,"page_label":"Page 3","source_page_url":"https://example.test/r.pdf#page=3","snippet":"evidence"}])
    monkeypatch.setattr(app, "_openai_json", lambda path, payload: {"output_text": json.dumps({"answer":"Answer","references":[{"document_id":"doc1","page_number":3},{"document_id":"fake","page_number":99}]})})
    result = app.answer_question("c", "p", "q")
    assert result["answer"] == "Answer"
    assert result["references"] == [{"document_id":"doc1","document_title":"record.pdf","page_number":3,"page_label":"Page 3","source_page_url":"https://example.test/r.pdf#page=3"}]
    assert result["retrieval"]["retrieved_chunks"] == 1
    assert result["retrieval"]["evidence_chunks"] == 1


def test_answer_question_sends_only_first_50_unique_chunks_and_preserves_urls(monkeypatch):
    captured = {}
    monkeypatch.setattr(app, "load_patient_documents", lambda c, p: [{"document_id": "doc0", "title": "record.pdf", "source_uri": "https://example.test/r.pdf"}])

    hits = []
    for i in range(1, 61):
        hits.append({
            "document_id": f"doc{i}",
            "document_title": f"record-{i}.pdf",
            "page_number": i,
            "page_label": f"Page {i}",
            "source_name": f"src{i}",
            "source_page_url": f"https://example.test/r{i}.pdf#page={i}",
            "snippet": f"chunk {i}",
            "confidence": 1.0 - (i * 0.001),
            "metadata": {},
        })
    # Duplicate entries should not consume extra evidence slots.
    hits.insert(1, dict(hits[0]))
    hits.insert(10, dict(hits[3]))
    monkeypatch.setattr(app, "search_patient_chunks", lambda c, p, q: hits)

    def fake_openai(path, payload):
        captured["payload"] = payload
        evidence = json.loads(payload["input"][0]["content"][0]["text"])["retrieved_evidence"]
        assert len(evidence) == 50
        assert evidence[0]["document_id"] == "doc1"
        assert evidence[1]["document_id"] == "doc2"
        assert evidence[2]["document_id"] == "doc3"
        assert evidence[3]["document_id"] == "doc4"
        assert evidence[4]["document_id"] == "doc5"
        assert evidence[49]["document_id"] == "doc50"
        assert evidence[0]["source_page_url"] == "https://example.test/r1.pdf#page=1"
        assert evidence[-1]["source_page_url"] == "https://example.test/r50.pdf#page=50"
        return {"output_text": json.dumps({"answer": "Answer", "references": [{"document_id": "doc1", "page_number": 1}, {"document_id": "doc50", "page_number": 50}, {"document_id": "fake", "page_number": 99}]})}

    monkeypatch.setattr(app, "_openai_json", fake_openai)
    result = app.answer_question("c", "p", "q")
    assert result["answer"] == "Answer"
    assert result["references"] == [
        {"document_id": "doc1", "document_title": "record-1.pdf", "page_number": 1, "page_label": "Page 1", "source_page_url": "https://example.test/r1.pdf#page=1"},
        {"document_id": "doc50", "document_title": "record-50.pdf", "page_number": 50, "page_label": "Page 50", "source_page_url": "https://example.test/r50.pdf#page=50"},
    ]
    assert result["retrieval"]["retrieved_chunks"] == 62
    assert result["retrieval"]["evidence_chunks"] == 50
    evidence = json.loads(captured["payload"]["input"][0]["content"][0]["text"])["retrieved_evidence"]
    assert len(evidence) == 50
    assert "doc51" not in {e["document_id"] for e in evidence}


def test_api_ask_requires_selection_and_question():
    response = app.lambda_handler(event("/api/ask", "POST", body={"question": "hello"}))
    assert response["statusCode"] == 400


def test_fragment_search_matches_burchell_to_burchill():
    # Regression: a mismatch after a shared prefix must back off at the
    # same query position. BURCHEL misses, but BURCH must match BURCHILL.
    items = [
        {"id": "unrelated-id", "label": "Zelda Pumpkin", "secondary": "8762", "search_text": "zelda pumpkin 8762"},
        {"id": "burchill-id", "label": "Deborah Burchill", "secondary": "8770", "search_text": "deborah burchill 8770"},
    ]
    scores = app._fragment_scores("Burchell", app._build_fragment_index(items))
    assert scores["burchill-id"] > 0
    results = app._search_loaded_options(items, "Burchell")
    assert any(item["id"] == "burchill-id" for item in results)
    assert not any(item["id"] == "unrelated-id" for item in results)


def test_api_options_uses_fragment_search_for_clients(monkeypatch):
    clients = [
        {"id": "d-1", "label": "Deborah Bain", "secondary": "8762"},
        {"id": "d-2", "label": "Deborah Burchill", "secondary": "8770"},
    ]
    monkeypatch.setattr(app, "load_clients", lambda force=False: clients)

    response = app.lambda_handler(event("/api/options", params={"kind": "client", "q": "Burchell"}))
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    labels = [item["label"] for item in body["items"]]
    assert "Deborah Burchill" in labels


def test_search_patient_chunks_remains_uncapped_and_returns_ranked_hits(monkeypatch):
    executed = {}
    rows = [
        ("doc1", "record-1.pdf", 1, "src", "https://example.test/r1.pdf", "chunk 1", {}, 0.1),
        ("doc2", "record-2.pdf", 2, "src", "https://example.test/r2.pdf", "chunk 2", {}, 0.2),
        ("doc3", "record-3.pdf", 3, "src", "https://example.test/r3.pdf", "chunk 3", {}, 0.3),
    ]

    class Cursor:
        def execute(self, sql, params): executed.update(sql=sql, params=params)
        def fetchall(self): return rows
        def close(self): pass

    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass

    monkeypatch.setattr(app, "_pg_connect", lambda: Connection())
    monkeypatch.setattr(app, "_embed", lambda q: [0.1, 0.2])
    hits = app.search_patient_chunks("client-1", "patient-2", "dental")
    assert len(hits) == 3
    assert [h["document_id"] for h in hits] == ["doc1", "doc2", "doc3"]
    assert "limit" not in executed["sql"].lower()


@pytest.mark.integration
def test_live_deborah_burchill_catalog_and_narrowing_speed():
    required = ["EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD"]
    if not all(os.environ.get(k) for k in required):
        pytest.skip("live PostgreSQL environment is not configured")
    clients = app.load_clients(force=True)
    assert any(c["label"] == "Deborah Burchill" for c in clients), "Deborah Burchill missing from live client catalog"

    def filter_clients(q):
        q = q.lower().strip()
        if len(q) < 3: return clients
        return [c for c in clients if q in " ".join(str(c.get(k, "")) for k in ("label", "secondary", "id")).lower()]

    for query in ("Deb", "Debo", "Debor", "Debora", "Deborah", "Deborah B"):
        started = time.perf_counter()
        matches = filter_clients(query)
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert any(c["label"] == "Deborah Burchill" for c in matches)
        assert elapsed_ms < 100, f"{query!r} narrowing took {elapsed_ms:.1f}ms"
    labels = [c["label"] for c in filter_clients("Deborah B")]
    assert "Deborah Burchill" in labels
