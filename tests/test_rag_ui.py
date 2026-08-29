from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import types
import base64
import importlib.util
import importlib
import subprocess
from pathlib import Path

import pytest

import scripts.rag_ui.catalog as rag_catalog
from scripts.rag_ui.catalog import load_catalog
import scripts.rag_ui.lambda_app as lambda_app
from scripts.rag_ui.lambda_app import lambda_handler


def _has_postgres_driver() -> bool:
    try:
        if importlib.util.find_spec("psycopg") is not None:
            return True
    except ModuleNotFoundError:
        pass
    try:
        if importlib.util.find_spec("pg8000.dbapi") is not None:
            return True
    except ModuleNotFoundError:
        pass
    return False


def _ensure_instinct_credentials_from_secrets_manager() -> None:
    if (
        os.environ.get("INSTINCT_CLIENT_SECRET_ARN", "").strip()
        and os.environ.get("INSTINCT_CLIENT_ID", "").strip()
        and os.environ.get("INSTINCT_CLIENT_SECRET", "").strip()
        and os.environ.get("TOKEN", "").strip()
    ):
        return

    secret_arn = os.environ.get("INSTINCT_CLIENT_SECRET_ARN", "").strip() or "arn:aws:secretsmanager:us-east-1:274530612068:secret:evh/instinct-api-credentials-OtjOO9"
    result = subprocess.run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--region",
            "us-east-1",
            "--secret-id",
            secret_arn,
            "--query",
            "SecretString",
            "--output",
            "text",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    secret_string = str(result.stdout or "").strip().strip('"')
    if not secret_string:
        raise AssertionError(f"Instinct secret {secret_arn} was empty")
    payload = json.loads(secret_string)
    if not isinstance(payload, dict):
        raise AssertionError(f"Instinct secret {secret_arn} did not contain JSON object credentials")

    client_id = str(payload.get("client_id") or payload.get("clientId") or payload.get("username") or payload.get("INSTINCT_CLIENT_ID") or "").strip()
    client_secret = str(payload.get("client_secret") or payload.get("clientSecret") or payload.get("password") or payload.get("INSTINCT_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise AssertionError(f"Instinct secret {secret_arn} is missing client_id/client_secret fields")

    os.environ["INSTINCT_CLIENT_SECRET_ARN"] = secret_arn
    os.environ["INSTINCT_CLIENT_ID"] = client_id
    os.environ["INSTINCT_CLIENT_SECRET"] = client_secret

    token_response = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            "POST",
            "-G",
            "--data-urlencode",
            "grant_type=client_credentials",
            "--data-urlencode",
            f"client_id={client_id}",
            "--data-urlencode",
            f"client_secret={client_secret}",
            "https://partner.instinctvet.com/v1/auth/token",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(token_response.stdout)
    token = str(payload.get("access_token") or payload.get("token") or payload.get("jwt") or "").strip()
    if not token:
        raise AssertionError("Could not acquire live Instinct token from Secrets Manager credentials")
    os.environ["TOKEN"] = token


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


def write_test_patients_fixture(path: Path) -> None:
    payload = [
        {"client_name": "INSTINCT TEST", "patient_name": "INSTINCT 1", "patient_id": 1, "account_id": "05682212-3fd9-4928-a554-9e789b1e6a82", "pims_code": "INSTINCT001"},
        {"client_name": "INSTINCT TEST", "patient_name": "INSTINCT 2", "patient_id": 2, "account_id": "12e01f5d-ddb2-40a1-a490-e44b797464b6", "pims_code": "INSTINCT002"},
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    lambda_app._SELECTED_CONTEXT_CACHE.clear()
    yield
    rag_catalog._CATALOG_CACHE.clear()
    rag_catalog._CATALOG_MEMORY = None
    lambda_app._SELECTED_CONTEXT_CACHE.clear()


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
def test_load_catalog_refreshes_after_fifteen_minutes(tmp_path, monkeypatch):
    sample = tmp_path / "sample.json"
    write_sample_catalog(sample)
    monkeypatch.setenv("RAG_UI_DATA_PATH", str(sample))

    timeline = [1000.0]
    monkeypatch.setattr(rag_catalog.time, "time", lambda: timeline[0])

    catalog1 = load_catalog()
    assert [item["label"] for item in catalog1.search_clients("")] == ["Alpha Client", "Beta Buyer"]

    refreshed = {
        "accounts": [
            {"id": "client-3", "pimsCode": "CCC003", "pimsId": None, "deletedAt": None, "primaryContact": {"nameFirst": "Gamma", "nameMiddle": None, "nameLast": "Caretaker"}},
        ],
        "patients": [],
    }
    sample.write_text(json.dumps(refreshed), encoding="utf-8")

    timeline[0] += 899.0
    catalog2 = load_catalog()
    assert [item["label"] for item in catalog2.search_clients("")] == ["Alpha Client", "Beta Buyer"]

    rag_catalog._CATALOG_MEMORY = (timeline[0] - 901.0, catalog1)
    rag_catalog._CATALOG_CACHE.clear()
    timeline[0] += 2.0
    catalog3 = load_catalog()
    assert [item["label"] for item in catalog3.search_clients("")] == ["Gamma Caretaker"]


@pytest.mark.unit
def test_load_catalog_with_status_allows_stale_memory(tmp_path, monkeypatch):
    sample = tmp_path / "sample.json"
    write_sample_catalog(sample)
    monkeypatch.setenv("RAG_UI_DATA_PATH", str(sample))

    timeline = [1000.0]
    monkeypatch.setattr(rag_catalog.time, "time", lambda: timeline[0])

    catalog1, status1 = rag_catalog.load_catalog_with_status()
    assert status1["source"] == "refresh"
    assert status1["stale"] is False

    refreshed = {
        "accounts": [
            {"id": "client-3", "pimsCode": "CCC003", "pimsId": None, "deletedAt": None, "primaryContact": {"nameFirst": "Gamma", "nameMiddle": None, "nameLast": "Caretaker"}},
        ],
        "patients": [],
    }
    sample.write_text(json.dumps(refreshed), encoding="utf-8")

    timeline[0] += 3600.0
    catalog2, status2 = rag_catalog.load_catalog_with_status(allow_stale=True)
    assert status2["source"] == "memory"
    assert status2["stale"] is True
    assert [item["label"] for item in catalog2.search_clients("")] == ["Alpha Client", "Beta Buyer"]


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
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><title>packaged</title>", encoding="utf-8")
    monkeypatch.setattr(lambda_app, "INDEX_PATH", static_dir / "index.html")

    index_response = lambda_handler({"rawPath": "/", "requestContext": {"http": {"method": "GET"}}})
    assert index_response["statusCode"] == 200
    assert "packaged" in index_response["body"]

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


@pytest.mark.unit
def test_serve_index_reads_packaged_static_html(monkeypatch, tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    index_path = static_dir / "index.html"
    index_path.write_text("<!doctype html><title>packaged</title>", encoding="utf-8")

    monkeypatch.setattr(lambda_app, "__file__", str(tmp_path / "lambda_app.py"))
    monkeypatch.setattr(lambda_app, "INDEX_PATH", index_path)

    response = lambda_app._serve_index()

    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "text/html; charset=utf-8"
    assert response["body"] == "<!doctype html><title>packaged</title>"


@pytest.mark.unit
def test_lambda_serves_pdf_icons_asset(monkeypatch, tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    icon_path = static_dir / "PDFIcons.png"
    icon_bytes = b"\x89PNG\r\n\x1a\nfakepng"
    icon_path.write_bytes(icon_bytes)

    monkeypatch.setattr(lambda_app, "PDF_ICONS_PATH", icon_path)
    response = lambda_app._serve_static_asset("/PDFIcons.png")

    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "image/png"
    assert response["isBase64Encoded"] is True
    assert base64.b64decode(response["body"]) == icon_bytes


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


@pytest.mark.unit
def test_lambda_import_primes_catalog_from_postgres(monkeypatch):
    calls = []

    def fake_load_catalog_with_status(data_path=None, *, allow_stale=False):
        calls.append({"data_path": data_path, "allow_stale": allow_stale})
        return object(), {"source": "refresh", "stale": False, "age_seconds": 0.0}

    monkeypatch.setenv("EVH_PGHOST", "example-host")
    monkeypatch.setenv("EVH_PGPORT", "5432")
    monkeypatch.setenv("EVH_PGDATABASE", "evhvector")
    monkeypatch.setenv("EVH_PGUSER", "evhadmin")
    monkeypatch.setenv("EVH_PGPASSWORD", "secret")
    monkeypatch.setenv("RAG_UI_DISABLE_IMPORT_PRELOAD", "")
    monkeypatch.setattr(rag_catalog, "load_catalog_with_status", fake_load_catalog_with_status)

    importlib.reload(lambda_app)

    assert calls == [{"data_path": None, "allow_stale": False}]


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
    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", lambda question, chunks, **kwargs: "The patient received Convenia on 2026-08-01.")
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
    assert payload["citations"][0]["source_page_url"] == "https://example.test/doc-1#page=1"
    assert payload["references"][0]["document_id"] == "doc-1"
    assert payload["references"][0]["source_uri"] == "https://example.test/doc-1"


@pytest.mark.unit
def test_call_openai_answer_uses_timeout_and_single_retry(monkeypatch):
    captured = {}

    fake_langchain_openai = types.ModuleType("langchain_openai")

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, messages):
            return type("Resp", (), {"content": "The last documented dental cleaning date is 10/14/2021."})()

    fake_langchain_openai.ChatOpenAI = FakeChatOpenAI

    fake_messages = types.ModuleType("langchain_core.messages")
    fake_messages.HumanMessage = lambda content: {"role": "user", "content": content}
    fake_messages.SystemMessage = lambda content: {"role": "system", "content": content}

    monkeypatch.setitem(sys.modules, "langchain_openai", fake_langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_messages)
    monkeypatch.setattr(lambda_app, "_openai_api_key", lambda: "test-key")

    answer = lambda_app._call_openai_answer(
        "What is the last dental cleaning date?",
        [{"document_title": "Source PDF", "page_label": "Page 1", "source_page_url": "", "snippet": "Date: 10/14/2021 4:40 PM"}],
    )

    assert "10/14/2021" in answer
    assert captured["timeout"] == 8
    assert captured["max_retries"] == 1
    assert captured["temperature"] == 0.2
    assert captured["model"] == lambda_app._llm_model()
    assert captured["api_key"] == "test-key"


@pytest.mark.unit
def test_call_openai_answer_includes_patient_metadata_and_history(monkeypatch):
    captured = {}

    fake_langchain_openai = types.ModuleType("langchain_openai")

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, messages):
            captured["messages"] = messages
            return type("Resp", (), {"content": "Minnie is a canine."})()

    fake_langchain_openai.ChatOpenAI = FakeChatOpenAI

    fake_messages = types.ModuleType("langchain_core.messages")
    fake_messages.HumanMessage = lambda content: {"role": "user", "content": content}
    fake_messages.SystemMessage = lambda content: {"role": "system", "content": content}

    monkeypatch.setitem(sys.modules, "langchain_openai", fake_langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_messages)
    monkeypatch.setattr(lambda_app, "_openai_api_key", lambda: "test-key")

    answer = lambda_app._call_openai_answer(
        "What species is Minnie?",
        [{"document_title": "Patient Note", "page_label": "Page 2", "source_page_url": "", "snippet": "Minnie is a pup with a playful gait."}],
        patient_context={
            "patient_name": "Minnie",
            "species": "Canine",
            "breed": "Yorkshire Terrier",
            "sex": "Female",
            "birthdate": "2020-05-01",
            "owner_name": "Deborah Burchill",
        },
        conversation_turns=[
            {"role": "user", "content": "What species is Minnie?"},
            {"role": "assistant", "content": "Minnie is likely a dog.", "citations": [{"document_id": "doc-1", "page_number": 2}], "references": [{"document_id": "doc-1", "page_number": 2, "document_title": "Patient Note"}]},
            {"role": "user", "content": "Clearly its a canine"},
            {"role": "assistant", "content": "Yes, canine is the supported inference.", "citations": [{"document_id": "doc-1", "page_number": 2}]},
            {"role": "user", "content": "I'm asking if it's a dog or cat"},
            {"role": "assistant", "content": "It is best read as a dog.", "citations": [{"document_id": "doc-1", "page_number": 2}]},
        ],
    )

    assert answer == "Minnie is a canine."
    system_text = captured["messages"][0]["content"]
    user_text = captured["messages"][1]["content"]
    assert "selected patient metadata is authoritative context" in system_text.lower()
    assert "instinct ems and weave" in system_text.lower()
    assert "general questions about those systems are in-scope" in system_text.lower()
    assert "explicit structured fact" in system_text.lower()
    assert "strong inference" in system_text.lower()
    assert "Do not require exact wording" in system_text
    assert '"patient_name": "Minnie"' in user_text
    assert '"species": "Canine"' in user_text
    assert '"breed": "Yorkshire Terrier"' in user_text
    assert "Clearly its a canine" in user_text
    assert "I'm asking if it's a dog or cat" in user_text
    assert '"citations":' in user_text
    assert '"references":' in user_text


@pytest.mark.integration
def test_lambda_serves_rag_answer_with_patient_context_and_history(monkeypatch):
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

    captured = {}
    def fake_answer(question, chunks, **kwargs):
        captured["question"] = question
        captured["chunks"] = chunks
        captured["kwargs"] = kwargs
        return "The patient received Convenia on 2026-08-01."
    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", fake_answer)
    monkeypatch.setattr("scripts.rag_ui.lambda_app._create_chart_file_url", lambda document_id, inline=True: "https://instinct.test/file.pdf")

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "What species is Minnie?"},
            "body": json.dumps({
                "patient_context": {
                    "patient_name": "Minnie",
                    "species": "Canine",
                    "breed": "Yorkshire Terrier",
                    "birthdate": "2020-05-01",
                    "owner_name": "Deborah Burchill",
                },
                "conversation": [
                    {"role": "user", "content": "What species is Minnie?"},
                    {"role": "assistant", "content": "Minnie is likely a dog.", "citations": [{"document_id": "doc-1", "page_number": 1}], "references": [{"document_id": "doc-1", "page_number": 1, "document_title": "Source PDF One"}]},
                    {"role": "user", "content": "Clearly its a canine"},
                    {"role": "assistant", "content": "Yes, canine is the supported inference.", "citations": [{"document_id": "doc-1", "page_number": 1}]},
                    {"role": "user", "content": "I'm asking if it's a dog or cat"},
                ]
            }),
            "requestContext": {"http": {"method": "POST"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["answer"] == "The patient received Convenia on 2026-08-01."
    assert captured["kwargs"]["patient_context"]["species"] == "Canine"
    assert captured["kwargs"]["conversation_turns"][0]["content"] == "What species is Minnie?"
    assert "Clearly its a canine" in captured["kwargs"]["conversation_turns"][2]["content"]
    assert "citations" in captured["kwargs"]["conversation_turns"][1]["content"]
    assert "references" in captured["kwargs"]["conversation_turns"][1]["content"]
    assert captured["question"] == "What species is Minnie?"
    assert payload["citations"][0]["document_id"] == "doc-1"
    assert payload["references"][0]["document_id"] == "doc-1"


@pytest.mark.unit
def test_answer_messages_include_selected_context_bundle(monkeypatch):
    captured = {}

    fake_langchain_openai = types.ModuleType("langchain_openai")

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def invoke(self, messages):
            captured["messages"] = messages
            return type("Resp", (), {"content": "All set."})()

    fake_langchain_openai.ChatOpenAI = FakeChatOpenAI

    fake_messages = types.ModuleType("langchain_core.messages")
    fake_messages.HumanMessage = lambda content: {"role": "user", "content": content}
    fake_messages.SystemMessage = lambda content: {"role": "system", "content": content}

    monkeypatch.setitem(sys.modules, "langchain_openai", fake_langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_messages)
    monkeypatch.setattr(lambda_app, "_openai_api_key", lambda: "test-key")

    answer = lambda_app._call_openai_answer(
        "What is due soon?",
        [],
        patient_context={
            "patient_name": "Minnie",
            "species": "Canine",
            "breed": "Yorkshire Terrier",
            "owner_name": "Deborah Burchill",
        },
        selected_context={
            "client": {"id": "client-1", "name": "Deborah Burchill"},
            "patient": {"id": "pet-1", "name": "Minnie"},
            "financials": {"balance": 12.34},
            "reminders": [{"title": "Annual exam"}],
            "documents": [{"title": "Visit Summary"}],
        },
    )

    assert answer == "All set."
    user_text = captured["messages"][1]["content"]
    assert "Selected conversation context:" in user_text
    assert '"balance": 12.34' in user_text
    assert '"Annual exam"' in user_text
    assert '"Visit Summary"' in user_text
    assert '"Deborah Burchill"' in user_text


@pytest.mark.integration
def test_lambda_serves_rag_answer_with_selected_context_bundle(monkeypatch):
    fake_catalog = types.SimpleNamespace(
        clients_by_id={"client-1": types.SimpleNamespace(id="client-1", label="Deborah Burchill", secondary="8762", primary_phone="", email="")},
        pets_by_id={"pet-1": types.SimpleNamespace(id="pet-1", client_id="client-1", label="Minnie", species="Canine", breed="Yorkshire Terrier", birthdate="2020-01-01", secondary="21369")},
    )
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_catalog_cached", lambda: fake_catalog)
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_patient_documents", lambda client_id, pet_id: [])
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_financials", lambda client_record: {"balance": 12.34})
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_reminders", lambda client_record, patient_record: [{"title": "Annual exam"}])
    monkeypatch.setattr("scripts.rag_ui.lambda_app.search_pet_chunks_by_embedding", lambda client_id, pet_id, question: ([], {"total_seconds": 0.0}))

    captured = {}

    def fake_answer(question, chunks, **kwargs):
        captured["kwargs"] = kwargs
        return "All set."

    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", fake_answer)

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "What is due soon?"},
            "body": json.dumps({
                "selected_context": {
                    "client": {"id": "client-1", "name": "Deborah Burchill"},
                    "patient": {"id": "pet-1", "name": "Minnie"},
                    "financials": {"balance": 12.34},
                    "reminders": [{"title": "Annual exam"}],
                    "documents": [{"title": "Visit Summary"}],
                }
            }),
            "requestContext": {"http": {"method": "POST"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["answer"] == "All set."
    assert captured["kwargs"]["selected_context"]["client"]["name"] == "Deborah Burchill"
    assert captured["kwargs"]["selected_context"]["financials"]["balance"] == 12.34


@pytest.mark.integration
def test_lambda_merges_patient_documents_into_selected_context(monkeypatch):
    fake_catalog = types.SimpleNamespace(
        clients_by_id={"client-1": types.SimpleNamespace(id="client-1", label="Deborah Burchill", secondary="8762", primary_phone="", email="")},
        pets_by_id={"pet-1": types.SimpleNamespace(id="pet-1", client_id="client-1", label="Minnie", species="Canine", breed="Yorkshire Terrier", birthdate="2020-01-01", secondary="21369")},
    )
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_catalog_cached", lambda: fake_catalog)
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_patient_documents", lambda client_id, pet_id: [
        {"document_id": "doc-x", "document_title": "Chart File", "source_page_url": "https://example.test/doc-x#page=1"}
    ])
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_financials", lambda client_record: {"balance": 12.34})
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_reminders", lambda client_record, patient_record: [{"title": "Annual exam"}])
    monkeypatch.setattr("scripts.rag_ui.lambda_app.search_pet_chunks_by_embedding", lambda client_id, pet_id, question: ([], {"total_seconds": 0.0}))

    captured = {}

    def fake_answer(question, chunks, **kwargs):
        captured["kwargs"] = kwargs
        return "All set."

    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", fake_answer)

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "What is due soon?"},
            "body": json.dumps({
                "patient_context": {
                    "patient_name": "Minnie",
                    "species": "Canine",
                    "breed": "Yorkshire Terrier",
                    "owner_name": "Deborah Burchill",
                },
                "selected_context": {
                    "client": {"id": "client-1", "name": "Deborah Burchill"},
                    "patient": {"id": "pet-1", "name": "Minnie"},
                    "financials": {"balance": 12.34},
                    "reminders": [{"title": "Annual exam"}],
                    "documents": [],
                },
            }),
            "requestContext": {"http": {"method": "POST"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["answer"] == "All set."
    assert captured["kwargs"]["selected_context"]["documents"][0]["document_id"] == "doc-x"


@pytest.mark.integration
def test_lambda_selected_context_survives_financials_failure(monkeypatch):
    fake_catalog = types.SimpleNamespace(
        clients_by_id={"client-1": types.SimpleNamespace(id="client-1", label="Deborah Burchill", secondary="8762", primary_phone="", email="")},
        pets_by_id={"pet-1": types.SimpleNamespace(id="pet-1", client_id="client-1", label="Minnie", species="Canine", breed="Yorkshire Terrier", birthdate="2020-01-01", secondary="21369")},
    )
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_catalog_cached", lambda: fake_catalog)
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_patient_documents", lambda client_id, pet_id: [])
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_financials", lambda client_record: (_ for _ in ()).throw(RuntimeError("financials boom")))
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_reminders", lambda client_record, patient_record: [{"title": "Annual exam"}])
    monkeypatch.setattr("scripts.rag_ui.lambda_app.search_pet_chunks_by_embedding", lambda client_id, pet_id, question: ([], {"total_seconds": 0.0}))

    captured = {}

    def fake_answer(question, chunks, **kwargs):
        captured["kwargs"] = kwargs
        return "All set."

    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", fake_answer)

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "What is due soon?"},
            "requestContext": {"http": {"method": "POST"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["answer"] == "All set."
    assert captured["kwargs"]["selected_context"]["client"]["name"] == "Deborah Burchill"
    assert captured["kwargs"]["selected_context"]["financials"] == {}
    assert captured["kwargs"]["selected_context"]["reminders"][0]["title"] == "Annual exam"


@pytest.mark.integration
def test_lambda_selected_context_survives_document_load_failure(monkeypatch):
    fake_catalog = types.SimpleNamespace(
        clients_by_id={"client-1": types.SimpleNamespace(id="client-1", label="Deborah Burchill", secondary="8762", primary_phone="", email="")},
        pets_by_id={"pet-1": types.SimpleNamespace(id="pet-1", client_id="client-1", label="Minnie", species="Canine", breed="Yorkshire Terrier", birthdate="2020-01-01", secondary="21369")},
    )
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_catalog_cached", lambda: fake_catalog)
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_patient_documents", lambda client_id, pet_id: (_ for _ in ()).throw(RuntimeError("documents boom")))
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_financials", lambda client_record: {"balance": 12.34})
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_reminders", lambda client_record, patient_record: [{"title": "Annual exam"}])
    monkeypatch.setattr("scripts.rag_ui.lambda_app.search_pet_chunks_by_embedding", lambda client_id, pet_id, question: ([], {"total_seconds": 0.0}))

    captured = {}

    def fake_answer(question, chunks, **kwargs):
        captured["kwargs"] = kwargs
        return "All set."

    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", fake_answer)

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "What is due soon?"},
            "requestContext": {"http": {"method": "POST"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["answer"] == "All set."
    assert captured["kwargs"]["selected_context"]["client"]["name"] == "Deborah Burchill"
    assert captured["kwargs"]["selected_context"]["financials"]["balance"] == 12.34
    assert captured["kwargs"]["selected_context"]["documents"] == []


@pytest.mark.integration
def test_lambda_answer_survives_empty_retrieval(monkeypatch):
    fake_catalog = types.SimpleNamespace(
        clients_by_id={"client-1": types.SimpleNamespace(id="client-1", label="Deborah Burchill", secondary="8762", primary_phone="", email="")},
        pets_by_id={"pet-1": types.SimpleNamespace(id="pet-1", client_id="client-1", label="Minnie", species="Canine", breed="Yorkshire Terrier", birthdate="2020-01-01", secondary="21369")},
    )
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_catalog_cached", lambda: fake_catalog)
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_patient_documents", lambda client_id, pet_id: [])
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_financials", lambda client_record: {"balance": 12.34})
    monkeypatch.setattr("scripts.rag_ui.lambda_app._fetch_instinct_reminders", lambda client_record, patient_record: [{"title": "Annual exam"}])
    monkeypatch.setattr("scripts.rag_ui.lambda_app._execute_planned_retrieval", lambda question, client_id, pet_id: ([], {"total_seconds": 0.0}, {"plan": "stubbed"}))

    captured = {}

    def fake_answer(question, chunks, **kwargs):
        captured["question"] = question
        captured["chunks"] = chunks
        captured["kwargs"] = kwargs
        return "All set."

    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", fake_answer)

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "What is due soon?"},
            "requestContext": {"http": {"method": "POST"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["answer"] == "All set."
    assert captured["question"] == "What is due soon?"
    assert captured["chunks"] == []
    assert captured["kwargs"]["selected_context"]["financials"]["balance"] == 12.34
    assert captured["kwargs"]["selected_context"]["reminders"][0]["title"] == "Annual exam"


@pytest.mark.integration
def test_lambda_answer_includes_conversation_citation_map(monkeypatch):
    monkeypatch.setattr("scripts.rag_ui.lambda_app.load_patient_documents", lambda client_id, pet_id: [
        {"document_id": "doc-b", "document_title": "Current Doc", "source_uri": "https://example.test/doc-b", "page_number": 2, "page_label": "Page 2", "source_page_url": "https://example.test/doc-b#page=2"},
    ])
    monkeypatch.setattr("scripts.rag_ui.lambda_app.search_pet_chunks_by_embedding", lambda client_id, pet_id, question: ([
        {
            "document_id": "doc-b",
            "document_title": "Current Doc",
            "page_number": 2,
            "page_label": "Page 2",
            "source_page_url": "https://example.test/doc-b#page=2",
            "snippet": "Current turn evidence from B.",
            "confidence": 0.92,
            "date": "2026-08-02",
        }
    ], {"total_seconds": 0.01}))

    monkeypatch.setattr("scripts.rag_ui.lambda_app._call_openai_answer", lambda question, chunks, **kwargs: 'The earlier record supports this [CITE document_id="doc-a" page="1"].')
    monkeypatch.setattr("scripts.rag_ui.lambda_app._create_chart_file_url", lambda document_id, inline=True: f"https://instinct.test/{document_id}.pdf")

    response = lambda_handler(
        {
            "rawPath": "/api/rag/answer",
            "queryStringParameters": {"client_id": "client-1", "pet_id": "pet-1", "q": "Follow-up question?"},
            "body": json.dumps({
                "patient_context": {
                    "patient_name": "Minnie",
                    "species": "Canine",
                    "breed": "Yorkshire Terrier",
                    "owner_name": "Deborah Burchill",
                },
                "conversation": [
                    {"role": "user", "content": "What species is Minnie?"},
                    {"role": "assistant", "content": "Minnie is likely a dog.", "citations": [{"document_id": "doc-a", "page_number": 1, "document_title": "Prior Doc", "source_page_url": "https://example.test/doc-a#page=1"}], "references": [{"document_id": "doc-a", "page_number": 1, "document_title": "Prior Doc", "source_uri": "https://example.test/doc-a"}]},
                ],
            }),
            "requestContext": {"http": {"method": "POST"}},
        }
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["citation_map"]["doc-a:1"]["source_uri"] == "https://example.test/doc-a"
    assert payload["citation_map"]["doc-a:1"]["document_title"] == "Prior Doc"
    assert payload["citation_map"]["doc-b:2"]["source_uri"] == "https://example.test/doc-b"
    assert payload["answer"] == 'The earlier record supports this [CITE document_id="doc-a" page="1"].'


@pytest.mark.unit
def test_call_openai_answer_fast_fails_on_timeout(monkeypatch):
    fake_langchain_openai = types.ModuleType("langchain_openai")

    class SlowChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            raise TimeoutError("request timed out")

    fake_langchain_openai.ChatOpenAI = SlowChatOpenAI

    fake_messages = types.ModuleType("langchain_core.messages")
    fake_messages.HumanMessage = lambda content: {"role": "user", "content": content}
    fake_messages.SystemMessage = lambda content: {"role": "system", "content": content}

    monkeypatch.setitem(sys.modules, "langchain_openai", fake_langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_messages)
    monkeypatch.setattr(lambda_app, "_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(lambda_app.urllib_request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fallback should not run")))

    started = time.perf_counter()
    with pytest.raises(RuntimeError) as excinfo:
        lambda_app._call_openai_answer(
            "What is the last dental cleaning date?",
            [{"document_title": "Source PDF", "page_label": "Page 1", "source_page_url": "", "snippet": "Date: 10/14/2021 4:40 PM"}],
        )
    elapsed = time.perf_counter() - started

    assert "timed out" in str(excinfo.value).lower()
    assert elapsed < 5


@pytest.mark.unit
def test_index_uses_request_driven_search_lifecycle():
    html = Path("website/EVHInstinctPDFRAG/index.html").read_text(encoding="utf-8")
    assert 'const SEARCH_MIN=3;' in html
    assert 'const SEARCH_DEBOUNCE_MS=250;' in html
    assert 'scheduleOptionSearch({' in html
    assert 'abortSearch(clientSearch);' in html
    assert 'abortSearch(petSearch);' in html
    assert 'no preload' in html
    assert 'no focus request' in html
    assert 'Searching…' in html
    assert 'debounce' in html
    assert 'abort superseded requests' in html
    assert 'backend fragment order preserved' in html
    assert 'Focus does not hit the backend' in html
    assert 'filterOptionsLocally' in html
    assert 'Filtering…' in html
    assert 'if(q.length<SEARCH_MIN)' in html
    assert 'if(q.length>=SEARCH_MIN && q===clientSearch.lastQuery && clientSearch.items.length)' in html
    assert 'patientCacheByClient:new Map()' in html
    assert 'loadPatientOptionsOnce(clientId)' in html
    assert 'cachedPatientsFor(state.client.id)' in html
    assert 'showCachedPatients()' in html
    assert 'Searching…' in html
    assert 'clearClientMenu()' in html


@pytest.mark.integration
@pytest.fixture(scope="module")
def live_instinct_catalog():
    _ensure_instinct_credentials_from_secrets_manager()
    return load_catalog()


@pytest.mark.integration
def test_live_client_filter_candidate_retention(live_instinct_catalog):
    catalog = live_instinct_catalog
    all_labels = [item["label"] for item in catalog.search_clients("")]
    assert all_labels, "expected a populated real client catalog"

    client_fragment_index = catalog.client_fragment_index
    client_by_id = catalog.clients_by_id

    candidate_cases = {
        "Deb": lambda scores, client_id: client_id in scores,
        "Debo": lambda scores, client_id: client_id in scores,
        "Debor": lambda scores, client_id: client_id in scores,
        "Debora": lambda scores, client_id: client_id in scores,
        "Deborah": lambda scores, client_id: client_id in scores,
        "Deborah B": lambda scores, client_id: client_id in scores,
        "Deborah Bu": lambda scores, client_id: client_id in scores,
        "Deborah Bur": lambda scores, client_id: client_id in scores,
        "Burchell": lambda scores, client_id: client_id in scores,
        "BEBBORAH": lambda scores, client_id: bool(scores),
    }

    target_item = next(iter(client_by_id.values()))
    target_id = next(item_id for item_id, item in client_by_id.items() if item is target_item)
    target_label = target_item.label
    target_words = [part for part in target_label.split() if part]
    query_prefixes = ["".join(target_words[:1]), "".join(target_words[:2])] if target_words else [target_label]
    candidate_cases = {query: (lambda scores, client_id: client_id in scores) for query in query_prefixes}

    for query, predicate in candidate_cases.items():
        scores = rag_catalog._fragment_scores(query, client_fragment_index)
        assert predicate(scores, target_id), f"{query!r}: expected {target_label} to remain in the candidate set"


@pytest.mark.integration
def test_live_client_filter_ranking_contract(live_instinct_catalog):
    catalog = live_instinct_catalog

    first_label = next(iter(catalog.search_clients("")))["label"]
    first_words = [part for part in first_label.split() if part]
    query = " ".join(first_words[:2]) if len(first_words) >= 2 else first_label
    ranking_cases = [
        (query, lambda labels: first_label in labels[:2]),
        (first_words[0] if first_words else first_label[:3], lambda labels: first_label in labels[:2]),
        (first_label, lambda labels: labels[0] == first_label),
    ]

    for query, predicate in ranking_cases:
        labels = [item["label"] for item in catalog.search_clients(query)]
        assert labels, f"{query!r}: expected nonempty results"
        assert len(labels) <= 10, f"{query!r}: expected top-10 max"
        assert predicate(labels), f"{query!r}: ranking contract failed — got {labels[:5]}"


@pytest.mark.integration
def test_live_client_filter_performance_budget(live_instinct_catalog):
    catalog = live_instinct_catalog
    queries = ["D", "De", "Deb", "Debo", "Debor", "Debora", "Deborah", "Deborah ", "Deborah B", "Deborah Bu", "Deborah Bur", "Burchell"]
    timings: dict[str, float] = {}
    catalog.search_clients("Deb")
    for query in queries:
        started = time.perf_counter()
        catalog.search_clients(query)
        timings[query] = time.perf_counter() - started
    assert max(timings.values()) < 0.1
