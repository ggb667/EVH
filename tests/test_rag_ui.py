from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import psycopg

from scripts.rag_ui.catalog import load_catalog
from scripts.rag_ui.lambda_app import lambda_handler


def write_sample_catalog(path: Path) -> None:
    payload = {
        "accounts": [
            {
                "id": "client-1",
                "pimsCode": "AAA001",
                "pimsId": "ALT-1",
                "deletedAt": None,
                "primaryContact": {
                    "nameFirst": "Alpha",
                    "nameMiddle": None,
                    "nameLast": "Client",
                },
            },
            {
                "id": "client-2",
                "pimsCode": "BBB002",
                "pimsId": None,
                "deletedAt": None,
                "primaryContact": {
                    "nameFirst": "Beta",
                    "nameMiddle": None,
                    "nameLast": "Buyer",
                },
            },
        ],
        "patients": [
            {
                "id": 10,
                "accountId": "client-1",
                "name": "Milo",
                "pimsCode": "PET010",
                "deletedAt": None,
                "species": {"label": "Canine"},
                "breed": {"label": "Golden Retriever"},
                "birthdate": "2020-01-01",
                "alerts": [{"label": "Anxious"}],
            },
            {
                "id": 11,
                "accountId": "client-1",
                "name": "Mika",
                "pimsCode": "PET011",
                "deletedAt": None,
                "species": {"label": "Feline"},
                "breed": {"label": "Domestic Shorthair"},
                "birthdate": "2021-02-02",
                "alerts": [],
            },
            {
                "id": 12,
                "accountId": "client-2",
                "name": "Poppy",
                "pimsCode": "PET012",
                "deletedAt": None,
                "species": {"label": "Canine"},
                "breed": {"label": "Poodle"},
                "birthdate": "2019-03-03",
                "alerts": [],
            },
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
        connection.execute(
            """
            INSERT INTO instinct_accounts (
                id, pims_code, pims_id, owner_first_name, owner_last_name, display_name,
                primary_phone, email_addresses, communication_details, updated_at, deleted_at,
                is_deleted, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "client-1",
                "AAA001",
                "ALT-1",
                "Alpha",
                "Client",
                "Alpha Client",
                "",
                "[]",
                "[]",
                None,
                None,
                0,
                "{}",
            ),
        )
        connection.execute(
            """
            INSERT INTO instinct_accounts (
                id, pims_code, pims_id, owner_first_name, owner_last_name, display_name,
                primary_phone, email_addresses, communication_details, updated_at, deleted_at,
                is_deleted, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "client-2",
                "BBB002",
                None,
                "Beta",
                "Buyer",
                "Beta Buyer",
                "",
                "[]",
                "[]",
                None,
                None,
                0,
                "{}",
            ),
        )
        connection.executemany(
            """
            INSERT INTO instinct_patients (
                id, account_id, pims_code, name, birthdate, sex_id, species_id, breed,
                deceased_date, deleted_at, merged_into_patient_id, alerts, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    10,
                    "client-1",
                    "PET010",
                    "Milo",
                    "2020-01-01",
                    None,
                    None,
                    "Golden Retriever",
                    None,
                    None,
                    None,
                    json.dumps([{"label": "Anxious"}]),
                    json.dumps({"species": {"label": "Canine"}}),
                ),
                (
                    11,
                    "client-1",
                    "PET011",
                    "Mika",
                    "2021-02-02",
                    None,
                    None,
                    "Domestic Shorthair",
                    None,
                    None,
                    None,
                    "[]",
                    json.dumps({"species": {"label": "Feline"}}),
                ),
                (
                    12,
                    "client-2",
                    "PET012",
                    "Poppy",
                    "2019-03-03",
                    None,
                    None,
                    "Poodle",
                    None,
                    None,
                    None,
                    "[]",
                    json.dumps({"species": {"label": "Canine"}}),
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _live_chunk_pair() -> tuple[str, str]:
    with psycopg.connect(
        host=os.environ["EVH_PGHOST"],
        port=int(os.environ["EVH_PGPORT"]),
        dbname=os.environ["EVH_PGDATABASE"],
        user=os.environ["EVH_PGUSER"],
        password=os.environ["EVH_PGPASSWORD"],
        connect_timeout=10,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select client_instinct_uuid, patient_id
                from public.pms_page_chunk
                where chunk_text is not null
                limit 1
                """
            )
            row = cursor.fetchone()
    assert row is not None, "expected at least one live chunk row"
    return str(row[0]), str(row[1])


def test_catalog_search_filters_after_three_chars(tmp_path, monkeypatch):
    sample = tmp_path / "sample.json"
    write_sample_catalog(sample)
    monkeypatch.setenv("RAG_UI_DATA_PATH", str(sample))

    catalog = load_catalog(str(sample))

    default_clients = catalog.search_clients("", limit=10)
    assert [item["label"] for item in default_clients] == ["Alpha Client", "Beta Buyer"]

    filtered_clients = catalog.search_clients("alp", limit=10)
    assert [item["label"] for item in filtered_clients] == ["Alpha Client"]

    default_pets = catalog.search_pets("client-1", "", limit=10)
    assert [item["label"] for item in default_pets] == ["Mika", "Milo"]

    filtered_pets = catalog.search_pets("client-1", "mil", limit=10)
    assert [item["label"] for item in filtered_pets] == ["Milo"]


def test_catalog_search_keeps_both_deborah_matches(tmp_path, monkeypatch):
    payload = {
        "accounts": [
            {
                "id": "d-1",
                "pimsCode": "8762",
                "pimsId": "ALT-8762",
                "deletedAt": None,
                "primaryContact": {
                    "nameFirst": "Deborah",
                    "nameMiddle": None,
                    "nameLast": "Bain",
                },
            },
            {
                "id": "d-2",
                "pimsCode": "8770",
                "pimsId": "ALT-8770",
                "deletedAt": None,
                "primaryContact": {
                    "nameFirst": "Deborah",
                    "nameMiddle": None,
                    "nameLast": "Burchill",
                },
            },
        ],
        "patients": [],
    }
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("RAG_UI_DATA_PATH", str(sample))

    catalog = load_catalog()
    results = catalog.search_clients("Deborah B", limit=10)
    labels = [item["label"] for item in results]

    assert "Deborah Bain" in labels
    assert "Deborah Burchill" in labels


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
            "rawQueryString": "kind=pet&clientId=client-1&q=mil&limit=10",
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    payload = json.loads(options_response["body"])
    assert payload["kind"] == "pet"
    assert [item["label"] for item in payload["items"]] == ["Milo"]


def test_catalog_search_reads_sqlite_database(tmp_path, monkeypatch):
    db_path = tmp_path / "instinct_identity.sqlite"
    write_sample_sqlite_catalog(db_path)
    monkeypatch.setenv("RAG_UI_DB_PATH", str(db_path))

    catalog = load_catalog(str(db_path))

    assert [item["label"] for item in catalog.search_clients("", limit=10)] == ["Alpha Client", "Beta Buyer"]
    assert [item["label"] for item in catalog.search_clients("alp", limit=10)] == ["Alpha Client"]
    assert [item["label"] for item in catalog.search_pets("client-1", "", limit=10)] == ["Mika", "Milo"]
    assert [item["label"] for item in catalog.search_pets("client-1", "mil", limit=10)] == ["Milo"]


def test_live_rag_document_search_uses_postgres_data():
    required = ("EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD")
    if not all(os.environ.get(name, "").strip() for name in required):
        return

    client_id, pet_id = _live_chunk_pair()

    response = lambda_handler(
        {
            "rawPath": "/api/rag/documents/search",
            "rawQueryString": f"client_id={client_id}&pet_id={pet_id}&q=&page=1&page_size=5",
            "requestContext": {"http": {"method": "GET"}},
        }
    )

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["client_id"] == client_id
    assert payload["pet_id"] == pet_id
    assert isinstance(payload["items"], list)
    assert payload["items"], "expected at least one live PDF hit"
    assert payload["items"][0]["snippet"]


def test_live_rag_context_endpoint_uses_postgres_data():
    required = ("EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD")
    if not all(os.environ.get(name, "").strip() for name in required):
        return

    client_id, pet_id = _live_chunk_pair()

    response = lambda_handler(
        {
            "rawPath": "/api/rag/context",
            "rawQueryString": f"client_id={client_id}&pet_id={pet_id}",
            "requestContext": {"http": {"method": "GET"}},
        }
    )

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["client_id"] == client_id
    assert payload["pet_id"] == pet_id
    assert payload["count"] == len(payload["items"])
    assert payload["items"], "expected live context chunks"
