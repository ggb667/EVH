from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
import sys

import pytest

import scripts.rag_ui.catalog as rag_catalog
from scripts.rag_ui.catalog import load_catalog
from scripts.rag_ui.lambda_app import (
    _answer_prompt,
    _deterministic_retrieval_plan,
    _execute_planned_retrieval,
    _instinct_token,
    _parse_planner_json,
    _plan_retrieval,
    _retrieval_planner_prompt,
    lambda_handler,
)


def write_sample_catalog(path: Path) -> None:
    payload = {
        "accounts": [
            {"id": "client-1", "pimsCode": "AAA001", "pimsId": "ALT-1", "deletedAt": None, "primaryContact": {"nameFirst": "Alpha", "nameMiddle": None, "nameLast": "Client"}},
            {"id": "client-2", "pimsCode": "BBB002", "pimsId": None, "deletedAt": None, "primaryContact": {"nameFirst": "Beta", "nameMiddle": None, "nameLast": "Buyer"}},
        ],
        "patients": [
            {"id": 10, "accountId": "client-1", "name": "Milo", "pimsCode": "PET010", "deletedAt": None, "species": {"label": "Canine"}, "breed": {"label": "Golden Retriever"}, "birthdate": "2020-01-01", "alerts": [{"label": "Anxious"}]},
            {"id": 11, "accountId": "client-1", "name": "Mika", "pimsCode": "PET011", "deletedAt": None, "species": {"label": "Feline"}, "breed": {"label": "Domestic Shorthair"}, "birthdate": "2021-02-02", "alerts": []},
            {"id": 12, "accountId": "client-2", "name": "Poppy", "pimsCode": "PET012", "deletedAt": None, "species": {"label": "Canine"}, "breed": {"label": "Poodle"}, "birthdate": "2019-03-03", "alerts": []},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_sample_sqlite_catalog(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE instinct_accounts (
                id TEXT PRIMARY KEY,
                pims_code TEXT NOT NULL,
                pims_id TEXT,
                owner_first_name TEXT NOT NULL DEFAULT '',
                owner_last_name TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                primary_phone TEXT NOT NULL DEFAULT '',
                email_addresses TEXT NOT NULL,
                communication_details TEXT NOT NULL,
                updated_at TEXT,
                deleted_at TEXT,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                raw_payload TEXT NOT NULL
            );

            CREATE TABLE instinct_patients (
                id INTEGER PRIMARY KEY,
                account_id TEXT NOT NULL,
                pims_code TEXT,
                name TEXT NOT NULL DEFAULT '',
                birthdate TEXT,
                sex_id TEXT,
                species_id TEXT,
                breed TEXT,
                deceased_date TEXT,
                deleted_at TEXT,
                merged_into_patient_id INTEGER,
                alerts TEXT NOT NULL,
                raw_payload TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO instinct_accounts (
                id, pims_code, pims_id, owner_first_name, owner_last_name, display_name,
                primary_phone, email_addresses, communication_details, updated_at, deleted_at,
                is_deleted, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("client-1", "AAA001", "ALT-1", "Alpha", "Client", "Alpha Client", "", "[]", "[]", None, None, 0, "{}"),
                ("client-2", "BBB002", None, "Beta", "Buyer", "Beta Buyer", "", "[]", "[]", None, None, 0, "{}"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO instinct_patients (
                id, account_id, pims_code, name, birthdate, sex_id, species_id, breed,
                deceased_date, deleted_at, merged_into_patient_id, alerts, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (10, "client-1", "PET010", "Milo", "2020-01-01", None, None, "Golden Retriever", None, None, None, json.dumps([{"label": "Anxious"}]), json.dumps({"species": {"label": "Canine"}})),
                (11, "client-1", "PET011", "Mika", "2021-02-02", None, None, "Domestic Shorthair", None, None, None, "[]", json.dumps({"species": {"label": "Feline"}})),
                (12, "client-2", "PET012", "Poppy", "2019-03-03", None, None, "Poodle", None, None, None, "[]", json.dumps({"species": {"label": "Canine"}})),
            ],
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def reset_catalog_cache():
    rag_catalog._CATALOG_CACHE.clear()
    rag_catalog._CATALOG_MEMORY = None
    yield
    rag_catalog._CATALOG_CACHE.clear()
    rag_catalog._CATALOG_MEMORY = None


@pytest.mark.unit
def test_catalog_search_filters_after_three_chars(tmp_path, monkeypatch):
    sample = tmp_path / "sample.json"
    write_sample_catalog(sample)
    monkeypatch.setenv("RAG_UI_DATA_PATH", str(sample))

    catalog = load_catalog(str(sample))
    assert [item["label"] for item in catalog.search_clients("")] == ["Alpha Client", "Beta Buyer"]
    assert [item["label"] for item in catalog.search_clients("alp")] == ["Alpha Client"]
    assert [item["label"] for item in catalog.search_pets("client-1", "")] == ["Milo", "Mika"]
    assert [item["label"] for item in catalog.search_pets("client-1", "mil")] == ["Milo"]


#
# Outer-shell tests: catalog loading and UI/API smoke.
#
@pytest.mark.unit
def test_catalog_search_keeps_both_deborah_matches(tmp_path, monkeypatch):
    payload = {
        "accounts": [
            {"id": "d-1", "pimsCode": "8762", "pimsId": "ALT-8762", "deletedAt": None, "primaryContact": {"nameFirst": "Deborah", "nameMiddle": None, "nameLast": "Bain"}},
            {"id": "d-2", "pimsCode": "8770", "pimsId": "ALT-8770", "deletedAt": None, "primaryContact": {"nameFirst": "Deborah", "nameMiddle": None, "nameLast": "Burchill"}},
        ],
        "patients": [],
    }
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("RAG_UI_DATA_PATH", str(sample))

    catalog = load_catalog()
    labels = [item["label"] for item in catalog.search_clients("Deborah B")]
    assert "Deborah Bain" in labels
    assert "Deborah Burchill" in labels


@pytest.mark.unit
def test_catalog_search_reads_sqlite_database(tmp_path, monkeypatch):
    db_path = tmp_path / "instinct_identity.sqlite"
    write_sample_sqlite_catalog(db_path)
    monkeypatch.setenv("RAG_UI_DB_PATH", str(db_path))

    catalog = load_catalog(str(db_path))
    assert [item["label"] for item in catalog.search_clients("")] == ["Alpha Client", "Beta Buyer"]
    assert [item["label"] for item in catalog.search_clients("alp")] == ["Alpha Client"]
    assert [item["label"] for item in catalog.search_pets("client-1", "")] == ["Milo", "Mika"]
    assert [item["label"] for item in catalog.search_pets("client-1", "mil")] == ["Milo"]


@pytest.mark.unit
def test_search_pet_chunks_by_embedding_uses_pgvector_sql(monkeypatch):
    executed = {}

    class FakeCursor:
        def execute(self, sql, params):
            executed["sql"] = sql
            executed["params"] = params

        def fetchall(self):
            return [
                ("doc-1", "Document One", 3, "Page 3", "https://example.test/doc-1#page=3", "chunk text", {"document_date": "2026-08-23"}, 0.12),
            ]

        def close(self):
            pass

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(rag_catalog, "_pg_connect", lambda: FakeConnection())
    monkeypatch.setattr(rag_catalog, "_embed_text_openai", lambda text: [0.1, 0.2, 0.3])

    hits, timing = rag_catalog.search_pet_chunks_by_embedding("client-1", "pet-1", "last dental")

    assert "embedding <=> %s::vector" in executed["sql"]
    assert "from public.pms_page_chunk" in executed["sql"]
    assert executed["params"][1] == "client-1"
    assert executed["params"][2] == "pet-1"
    assert hits[0]["document_id"] == "doc-1"
    assert hits[0]["page_number"] == 3
    assert timing["total_seconds"] >= 0


@pytest.mark.integration
def test_lambda_serves_index_and_options(tmp_path, monkeypatch):
    sample = tmp_path / "sample.json"
    write_sample_catalog(sample)
    monkeypatch.setenv("RAG_UI_DATA_PATH", str(sample))

    index_response = lambda_handler({"rawPath": "/", "requestContext": {"http": {"method": "GET"}}})
    assert index_response["statusCode"] == 200
    assert "client-input" in index_response["body"]
    assert "pet-input" in index_response["body"]

    options_response = lambda_handler(
        {
            "rawPath": "/api/options",
            "queryStringParameters": {"kind": "pet", "clientId": "client-1", "q": "mil"},
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    payload = json.loads(options_response["body"])
    assert payload["kind"] == "pet"
    assert [item["label"] for item in payload["items"]] == ["Milo"]


@pytest.mark.integration
def test_lambda_serves_options_from_sqlite_catalog(tmp_path, monkeypatch):
    db_path = tmp_path / "instinct_identity.sqlite"
    write_sample_sqlite_catalog(db_path)
    monkeypatch.setenv("RAG_UI_DB_PATH", str(db_path))

    options_response = lambda_handler(
        {
            "rawPath": "/api/options",
            "queryStringParameters": {"kind": "client", "q": "alp"},
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    payload = json.loads(options_response["body"])
    assert payload["kind"] == "client"
    assert [item["label"] for item in payload["items"]] == ["Alpha Client"]


#
# RAG pipeline tests: retrieval, evidence, and answer orchestration.
#
@pytest.mark.unit
def test_rag_search_uses_vector_similarity(monkeypatch):
    executed = {}
    embed_calls = []

    class FakeCursor:
        def execute(self, sql, params):
            executed["sql"] = sql
            executed["params"] = params

        def fetchall(self):
            return [
                ("doc-1", "Document One", 3, "Page 3", "https://example.test/doc-1#page=3", "chunk text", {"document_date": "2026-08-23"}, 0.12),
                ("doc-2", "Document Two", 4, "Page 4", "https://example.test/doc-2#page=4", "other chunk", {"document_date": "2026-08-22"}, 0.30),
            ]

        def close(self):
            pass

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(rag_catalog, "_pg_connect", lambda: FakeConnection())
    monkeypatch.setattr(rag_catalog, "_embed_text_openai", lambda text: embed_calls.append(text) or [0.1, 0.2, 0.3])

    hits, timing = rag_catalog.search_pet_chunks_by_embedding("client-123", "patient-456", "when was the last dental?")

    assert embed_calls == ["when was the last dental?"]
    assert "embedding <=> %s::vector" in executed["sql"]
    assert "client_instinct_uuid = %s" in executed["sql"]
    assert "patient_id = %s" in executed["sql"]
    assert "ilike" not in executed["sql"].lower()
    assert executed["params"][1] == "client-123"
    assert executed["params"][2] == "patient-456"
    assert hits[0]["document_id"] == "doc-1"
    assert hits[0]["page_number"] == 3
    assert hits[0]["confidence"] == pytest.approx(0.88, abs=1e-6)
    assert timing["total_seconds"] >= 0


@pytest.mark.integration
def test_lambda_serves_rag_answer_with_citations(monkeypatch):
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_patient_documents", lambda client_id, pet_id: [
        {"document_id": "doc-1", "document_title": "Source PDF One", "source_uri": "https://example.test/doc-1", "page_number": 1, "page_label": "Page 1", "source_page_url": "https://example.test/doc-1#page=1"},
    ])
    monkeypatch.setattr("scripts.rag_ui.lambda_app.search_pet_chunks_by_embedding", lambda client_id, pet_id, question: ([
        {
            "document_id": "doc-1",
            "document_title": "Source PDF One",
            "page_number": 1,
            "page_label": "Page 1",
            "source_page_url": "https://example.test/doc-1#page=1",
            "snippet": "The patient received Convenia on 2026-08-01.",
            "confidence": 0.93,
            "date": "2026-08-01",
        }
    ], {"total_seconds": 0.012, "pg_connect_seconds": 0.001, "embedding_seconds": 0.002, "execute_seconds": 0.003, "fetch_seconds": 0.004, "materialize_seconds": 0.002}))
    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", lambda question, chunks: "The patient received Convenia on 2026-08-01.")
    monkeypatch.setattr("scripts.rag_ui.lambda_app._create_chart_file_url", lambda document_id, inline=True: "https://instinct.test/file.pdf")

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "When was Convenia given?"},
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["answer"] == "The patient received Convenia on 2026-08-01."
    assert payload["citations"][0]["document_id"] == "doc-1"
    assert payload["citations"][0]["page_number"] == 1
    assert payload["references"][0]["document_id"] == "doc-1"
    assert payload["references"][0]["source_uri"] == "https://example.test/doc-1"


@pytest.mark.integration
def test_document_page_redirects_via_cached_instinct_url(monkeypatch):
    monkeypatch.setattr("scripts.rag_ui.lambda_app._resolve_cached_instinct_url", lambda document_id, page_number, force_refresh=False: "https://instinct.test/file.pdf#page=1")

    response = lambda_handler(
        {
            "rawPath": "/api/rag/documents/doc-1/pages/1",
            "queryStringParameters": {"page": "1"},
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    assert response["statusCode"] == 302
    assert response["headers"]["location"] == "https://instinct.test/file.pdf#page=1"


@pytest.mark.unit
def test_document_page_redirect_uses_instinct_url_without_appending_page(monkeypatch):
    captured = {}

    def fake_resolve(document_id, page_number, force_refresh=False):
        captured["document_id"] = document_id
        captured["page_number"] = page_number
        return "https://instinct.test/file.pdf?signature=abc123"

    monkeypatch.setattr("scripts.rag_ui.lambda_app._resolve_cached_instinct_url", fake_resolve)

    response = lambda_handler(
        {
            "rawPath": "/api/rag/documents/doc-1/pages/34",
            "queryStringParameters": {"page": "34"},
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    assert response["statusCode"] == 302
    assert response["headers"]["location"] == "https://instinct.test/file.pdf?signature=abc123"
    assert captured == {"document_id": "doc-1", "page_number": 34}
    assert "page=34" not in response["headers"]["location"]


@pytest.mark.unit
def test_resolve_cached_instinct_url_appends_page_fragment_not_query(monkeypatch):
    monkeypatch.setenv("RAG_UI_INSTINCT_URL_TTL_SECONDS", "1800")
    monkeypatch.setattr("scripts.rag_ui.lambda_app._create_chart_file_url", lambda chart_id, inline=True: "https://instinct.test/file.pdf?signature=abc123")
    monkeypatch.setattr("scripts.rag_ui.lambda_app._verify_instinct_url", lambda url, timeout=30: True)

    from scripts.rag_ui.lambda_app import _resolve_cached_instinct_url

    url = _resolve_cached_instinct_url("doc-1", 34, force_refresh=True)
    assert url == "https://instinct.test/file.pdf?signature=abc123#page=34"
    assert "?signature=abc123#page=34" in url
    assert "&page=34" not in url


@pytest.mark.unit
def test_verify_instinct_url_accepts_get_after_head_failure(monkeypatch):
    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=30):
        calls.append(request.method)
        if request.method == "HEAD":
            raise OSError("HEAD failed")
        return FakeResponse()

    monkeypatch.setattr("scripts.rag_ui.lambda_app.urllib_request.urlopen", fake_urlopen)

    from scripts.rag_ui.lambda_app import _verify_instinct_url

    assert _verify_instinct_url("https://instinct.test/file.pdf?signature=abc123") is True
    assert calls == ["HEAD", "GET"]


@pytest.mark.unit
def test_retrieval_planner_prompt_includes_all_intents_and_rules():
    prompt = _retrieval_planner_prompt("When was the last dental?")
    text = prompt["content"][0]["text"]
    assert "SEMANTIC" in text
    assert "RECENT" in text
    assert "TIMELINE" in text
    assert "EXHAUSTIVE" in text
    assert "DOCUMENT" in text
    assert "Do not answer the question" in text
    assert "Return only JSON" in text


@pytest.mark.unit
def test_answer_prompt_is_evidence_only_and_mentions_grouping():
    prompt = _answer_prompt("What happened at the last visit?", sources=[{"document_id": "doc-1"}])
    text = prompt["content"][0]["text"]
    assert "careful patient-record assistant" in text
    assert "Use only the provided retrieved evidence" in text
    assert "If the retrieved evidence is grouped by document" in text
    assert "Do not invent facts" in text


@pytest.mark.unit
def test_parse_planner_json_handles_single_and_multi_requests():
    single = _parse_planner_json('{"retrieval":"RECENT","query":"last dental"}')
    multi = _parse_planner_json('{"requests":[{"retrieval":"RECENT","query":"last dental"},{"retrieval":"TIMELINE","query":"dental history"}]}')
    assert single == {"retrieval": "RECENT", "query": "last dental"}
    assert multi == {
        "requests": [
            {"retrieval": "RECENT", "query": "last dental"},
            {"retrieval": "TIMELINE", "query": "dental history"},
        ]
    }


@pytest.mark.unit
def test_plan_retrieval_uses_langchain_planner_json(monkeypatch):
    captured = {}

    class FakeResponse:
        content = '{"retrieval":"DOCUMENT","query":"March lab report"}'

    class FakeChat:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def invoke(self, messages):
            captured["messages"] = messages
            return FakeResponse()

    class FakeHuman:
        def __init__(self, content):
            self.content = content

    class FakeSystem:
        def __init__(self, content):
            self.content = content

    fake_openai = __import__("types").SimpleNamespace(ChatOpenAI=FakeChat)
    fake_messages = __import__("types").SimpleNamespace(HumanMessage=FakeHuman, SystemMessage=FakeSystem)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_messages)
    monkeypatch.setattr("scripts.rag_ui.lambda_app._openai_api_key", lambda: "test-key")

    plan = _plan_retrieval("What does the March lab report say?")

    assert plan == {"retrieval": "DOCUMENT", "query": "March lab report"}
    assert captured["kwargs"]["temperature"] == 0
    assert any("strict retrieval planner" in getattr(msg, "content", "") for msg in captured["messages"])
    assert any("What does the March lab report say?" in getattr(msg, "content", "") for msg in captured["messages"])


@pytest.mark.unit
@pytest.mark.parametrize(
    "question,expected_intent",
    [
        ("When was the last dental?", "RECENT"),
        ("What happened at the last visit?", "RECENT"),
        ("What dates did we see him?", "TIMELINE"),
        ("Has he ever had seizures?", "EXHAUSTIVE"),
        ("What does the March lab report say?", "DOCUMENT"),
        ("Find the most relevant record about allergies.", "SEMANTIC"),
    ],
)
def test_planner_prompt_covers_question_to_intent_examples(question, expected_intent):
    prompt = _retrieval_planner_prompt(question)
    text = prompt["content"][0]["text"]
    assert expected_intent in text


@pytest.mark.unit
def test_execute_planned_retrieval_routes_single_and_multi_requests(monkeypatch):
    planned = {}

    def fake_plan(question, sources=None):
        planned["question"] = question
        return {
            "requests": [
                {"retrieval": "RECENT", "query": "recent dental"},
                {"retrieval": "TIMELINE", "query": "dental history"},
            ]
        }

    def fake_retrieve(intent, query, client_id, pet_id):
        return (
            [{"document_id": f"{intent}:{query}", "page_number": 1, "snippet": query}],
            {f"{intent.lower()}_seconds": 0.01},
        )

    monkeypatch.setattr("scripts.rag_ui.lambda_app._deterministic_retrieval_plan", lambda question: None)
    monkeypatch.setattr("scripts.rag_ui.lambda_app._plan_retrieval", fake_plan)
    monkeypatch.setattr("scripts.rag_ui.lambda_app._retrieve_with_intent", fake_retrieve)

    hits, timing, plan = _execute_planned_retrieval("Compare his last dental with the previous one.", "client-1", "pet-1")
    assert planned["question"] == "Compare his last dental with the previous one."
    assert plan["requests"][0]["retrieval"] == "RECENT"
    assert plan["requests"][1]["retrieval"] == "TIMELINE"
    assert [hit["document_id"] for hit in hits] == ["RECENT:recent dental", "TIMELINE:dental history"]
    assert timing["recent_seconds"] == 0.01
    assert timing["timeline_seconds"] == 0.01


@pytest.mark.unit
@pytest.mark.parametrize(
    "question,expected",
    [
        ("Find the most relevant record about allergies.", {"retrieval": "SEMANTIC", "query": "most relevant record about allergies"}),
        ("When was the last dental cleaning date?", {"retrieval": "RECENT", "query": "dental cleaning"}),
        ("What happened at the most recent visit?", {"retrieval": "RECENT", "query": "happened at visit"}),
        ("What dates did we see him?", {"retrieval": "TIMELINE", "query": "dates did we see him"}),
        ("Has he ever had seizures?", {"retrieval": "EXHAUSTIVE", "query": "has he ever had seizures"}),
        ("What does the March lab report say?", {"retrieval": "DOCUMENT", "query": "march lab report"}),
    ],
)
def test_deterministic_retrieval_plan_routes_common_questions(question, expected):
    assert _deterministic_retrieval_plan(question) == expected


@pytest.mark.unit
def test_execute_planned_retrieval_skips_planner_for_recent_question(monkeypatch):
    called = {"planner": False, "retrieve": False}

    def fail_plan(*args, **kwargs):
        called["planner"] = True
        raise AssertionError("planner should not be called")

    def fake_retrieve(intent, query, client_id, pet_id):
        called["retrieve"] = True
        return ([{"document_id": "doc-1", "page_number": 1, "snippet": query}], {"total_seconds": 0.01})

    monkeypatch.setattr("scripts.rag_ui.lambda_app._plan_retrieval", fail_plan)
    monkeypatch.setattr("scripts.rag_ui.lambda_app._retrieve_with_intent", fake_retrieve)

    hits, timing, plan = _execute_planned_retrieval("What is the last dental cleaning date?", "client-1", "pet-1")

    assert plan == {"retrieval": "RECENT", "query": "dental cleaning"}
    assert called["planner"] is False
    assert called["retrieve"] is True
    assert hits[0]["snippet"] == "dental cleaning"
    assert timing["total_seconds"] == 0.01


@pytest.mark.unit
def test_execute_planned_retrieval_falls_back_to_planner_for_ambiguous_question(monkeypatch):
    called = {"planner": False}

    def fake_plan(question, sources=None):
        called["planner"] = True
        return {"retrieval": "SEMANTIC", "query": "allergy question"}

    def fake_retrieve(intent, query, client_id, pet_id):
        return ([{"document_id": "doc-1", "page_number": 1, "snippet": query}], {"total_seconds": 0.02})

    monkeypatch.setattr("scripts.rag_ui.lambda_app._deterministic_retrieval_plan", lambda question: None)
    monkeypatch.setattr("scripts.rag_ui.lambda_app._plan_retrieval", fake_plan)
    monkeypatch.setattr("scripts.rag_ui.lambda_app._retrieve_with_intent", fake_retrieve)

    hits, timing, plan = _execute_planned_retrieval("What should I know about him?", "client-1", "pet-1")

    assert called["planner"] is True
    assert plan == {"retrieval": "SEMANTIC", "query": "allergy question"}
    assert hits[0]["snippet"] == "allergy question"
    assert timing["total_seconds"] == 0.02


@pytest.mark.unit
def test_instinct_token_loads_from_secrets_manager(monkeypatch):
    captured = {}

    class FakeSecrets:
        def get_secret_value(self, SecretId):
            captured["SecretId"] = SecretId
            return {"SecretString": json.dumps({"client_id": "instinct-id", "client_secret": "instinct-secret"})}

    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.setenv("INSTINCT_CLIENT_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:instinct")
    monkeypatch.setattr("scripts.rag_ui.lambda_app.boto3", __import__("types").SimpleNamespace(client=lambda name: FakeSecrets()))
    monkeypatch.setattr("scripts.rag_ui.lambda_app._instinct_base_url", lambda: "https://partner.instinctvet.test")

    # We only need to prove the secret is read; short-circuit the token POST response.
    def fake_urlopen(request, timeout=30):
        class Resp:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                return json.dumps({"access_token": "token-123"}).encode("utf-8")
        return Resp()

    monkeypatch.setattr("scripts.rag_ui.lambda_app.urllib_request.urlopen", fake_urlopen)

    assert _instinct_token() == "token-123"
    assert captured["SecretId"] == "arn:aws:secretsmanager:us-east-1:123456789012:secret:instinct"


@pytest.mark.unit
def test_call_openai_answer_logs_timing(monkeypatch, capsys):
    class FakeResponse:
        content = "Dental answer"

    class FakeChat:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def invoke(self, messages):
            return FakeResponse()

    class FakeHuman:
        def __init__(self, content):
            self.content = content

    class FakeSystem:
        def __init__(self, content):
            self.content = content

    monkeypatch.setattr("scripts.rag_ui.lambda_app._llm_model", lambda: "gpt-test")
    monkeypatch.setattr("scripts.rag_ui.lambda_app._openai_api_key", lambda: "openai-test")
    monkeypatch.setitem(sys.modules, "langchain_openai", __import__("types").SimpleNamespace(ChatOpenAI=FakeChat))
    monkeypatch.setitem(sys.modules, "langchain_core.messages", __import__("types").SimpleNamespace(HumanMessage=FakeHuman, SystemMessage=FakeSystem))

    from scripts.rag_ui.lambda_app import _call_openai_answer
    assert _call_openai_answer("What is the last dental cleaning date?", [{"document_title": "Doc", "page_label": "Page 1", "source_page_url": "", "snippet": "10/14/2021"}]) == "Dental answer"
    out = capsys.readouterr().out
    assert "answer_model=gpt-test" in out
    assert "answer_request_start" in out


@pytest.mark.unit
@pytest.mark.parametrize(
    "question,expected_rule",
    [
        ("When was the last dental?", "latest / last / most recent"),
        ("What happened at the last visit?", "latest / last / most recent"),
        ("What dates did we see him?", "dates / timeline / history over time"),
        ("Has he ever had seizures?", "ever / all / every / complete history / list all"),
        ("What does the March lab report say?", "specific report / date / document type"),
        ("Find the most relevant record about allergies.", "most relevant record"),
    ],
)
def test_question_intent_matrix_is_represented(question, expected_rule):
    # This is a planner contract smoke test: the examples in the prompt
    # must keep the intent labels visible to the model.
    prompt = _retrieval_planner_prompt(question)["content"][0]["text"]
    assert expected_rule in prompt


@pytest.mark.unit
def test_index_uses_load_once_and_local_filtering():
    html = Path("website/EVHInstinctPDFRAG/index.html").read_text(encoding="utf-8")
    assert "loadClientsOnce" in html
    assert "loadPetsOnce" in html
    assert "filterClientsLocally" in html
    assert "filterPetsLocally" in html
    assert 'kind: "client",\n        q: query' not in html
    assert 'kind: "pet",\n        clientId: state.client.id,\n        q: query' not in html


@pytest.mark.integration
def test_live_client_filter_performance_budget():
    required = ("EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD")
    missing = [name for name in required if not __import__("os").environ.get(name)]
    assert not missing, f"live PostgreSQL credentials are required for this integration test: {', '.join(missing)}"

    catalog = load_catalog()
    all_labels = [item["label"] for item in catalog.search_clients("")]
    assert all_labels, "expected a populated real client catalog"
    assert any(label == "Deborah Burchill" for label in all_labels), "expected Deborah Burchill in the real catalog"

    queries = ["D", "De", "Deb", "Debo", "Debor", "Debora", "Deborah", "Deborah ", "Deborah B", "Deborah Bu", "Deborah Bur"]
    results: dict[str, list[str]] = {}
    timings: dict[str, float] = {}

    # Warm the catalog/search path once so the timing budget reflects interactive filtering
    # rather than one-time cache or module initialization noise.
    catalog.search_clients("Deb")

    for query in queries:
        started = time.perf_counter()
        results[query] = [item["label"] for item in catalog.search_clients(query)]
        timings[query] = time.perf_counter() - started

    assert results["D"] == all_labels
    assert results["De"] == all_labels
    assert "Deborah Burchill" in results["Deb"]
    assert "Deborah Burchill" in results["Debo"]
    assert "Deborah Burchill" in results["Debor"]
    assert "Deborah Burchill" in results["Debora"]
    assert "Deborah Burchill" in results["Deborah"]
    assert "Deborah Burchill" in results["Deborah "]
    assert "Deborah Burchill" in results["Deborah B"]
    assert "Deborah Burchill" in results["Deborah Bu"]
    assert results["Deborah Bur"][0] == "Deborah Burchill"
    assert max(timings.values()) < 0.1
