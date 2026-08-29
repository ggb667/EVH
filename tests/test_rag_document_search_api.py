from __future__ import annotations

import json

from scripts.rag_document_search_api import (
    DEFAULT_ROUTE_PATH,
    _build_search_sql,
    _normalize_row,
    _offset_to_cursor,
    _request_from_event,
    _response_payload,
    lambda_handler,
)


def test_request_parsing_and_cursor_round_trip():
    request = _request_from_event(
        {
            "rawPath": DEFAULT_ROUTE_PATH,
            "rawQueryString": "client_id=client-1&petId=pet-9&q=milk&page=2&pageSize=10&cursor=&sort=recent",
            "requestContext": {"http": {"method": "GET"}},
        }
    )

    assert request.client_id == "client-1"
    assert request.pet_id == "pet-9"
    assert request.q == "milk"
    assert request.page == 2
    assert request.page_size == 10
    assert request.sort == "recent"
    assert _offset_to_cursor(15)


def test_search_sql_mentions_ocr_page_table_and_limits():
    request = _request_from_event(
        {
            "rawPath": DEFAULT_ROUTE_PATH,
            "rawQueryString": "client_id=client-1&q=milk&page=1&pageSize=10",
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    sql, args = _build_search_sql(request)
    assert "rag_pdf_ocr_page" in sql
    assert "source_reference_id" in sql
    assert args[-2:] == [10, 0]


def test_normalize_row_emits_stable_source_page_url():
    normalized = _normalize_row(
        {
            "document_id": "doc-1",
            "pdf_id": "chart-42",
            "client_id": "client-1",
            "pet_id": "pet-1",
            "filename": "file.pdf",
            "page_id": "page-9",
            "page_number": 3,
            "page_label": "3",
            "extracted_text": "hello there",
            "source_uri": "s3://bucket/file.pdf",
            "score": 0.98,
            "hit_type": "page",
        }
    )
    assert normalized["source_page_url"] == "/api/rag/documents/chart-42/pages/3"
    assert normalized["match_text"] == "hello there"


def test_handler_returns_route_not_configured_without_db_url(monkeypatch):
    monkeypatch.delenv("EVH_PGDATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = lambda_handler(
        {
            "rawPath": DEFAULT_ROUTE_PATH,
            "requestContext": {"http": {"method": "GET"}},
        }
    )
    assert response["statusCode"] == 503
    payload = json.loads(response["body"])
    assert payload["error"] == "route_not_configured"


def test_response_payload_includes_source_truth_policy():
    payload = _response_payload(
        _request_from_event(
            {
                "rawPath": DEFAULT_ROUTE_PATH,
                "rawQueryString": "page=1&pageSize=5",
                "requestContext": {"http": {"method": "GET"}},
            }
        ),
        [
            {
                "document_id": "doc-1",
                "pdf_id": "chart-42",
                "page_number": 1,
                "source_uri": "s3://bucket/file.pdf",
            }
        ],
    )
    assert payload["items"][0]["source_page_url"] == "/api/rag/documents/chart-42/pages/1"
    assert "rag_pdf_ocr_page" in payload["source_truth"]["text_layer_policy"]
