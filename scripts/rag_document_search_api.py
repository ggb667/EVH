from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency for tests/import-time safety
    psycopg = None  # type: ignore[assignment]


DEFAULT_ROUTE_PATH = "/api/rag/documents/search"
DEFAULT_SOURCE_PAGE_PREFIX = "/api/rag/documents"
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DEFAULT_ICON_SHEET_PATH = "/home/ggb66/dev/EVH/data/PDFIcons.png"

DOCUMENT_FAMILY_ICON_INDEX = {
    "medical_notes": 1,
    "labs": 2,
    "prescriptions": 3,
    "vaccine_history": 4,
    "communications": 5,
    "transaction_history": 6,
    "diagnoses": 7,
    "wellness": 4,
    "other": 7,
}


@dataclass(frozen=True)
class SearchRequest:
    client_id: str | None
    pet_id: str | None
    q: str
    page: int
    page_size: int
    cursor: int
    sort: str


class RouteConfigError(RuntimeError):
    pass


def _headers(content_type: str) -> dict[str, str]:
    return {
        "content-type": content_type,
        "cache-control": "no-store",
        "access-control-allow-origin": "*",
    }


def _json_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _headers("application/json; charset=utf-8"),
        "body": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
    }


def _path(event: dict[str, Any]) -> str:
    return str(event.get("rawPath") or event.get("path") or "/")


def _method(event: dict[str, Any]) -> str:
    request_context = event.get("requestContext") or {}
    http = request_context.get("http") or {}
    return str(http.get("method") or event.get("httpMethod") or "GET").upper()


def _query_params(event: dict[str, Any]) -> dict[str, str]:
    params = event.get("queryStringParameters")
    if isinstance(params, dict) and params:
        return {str(k): str(v) for k, v in params.items() if v is not None}
    raw_query = str(event.get("rawQueryString") or "")
    if not raw_query:
        return {}
    parsed = parse_qs(raw_query, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _parse_positive_int(value: str | None, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        parsed = int((value or "").strip())
    except ValueError:
        return default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _cursor_to_offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
        return max(0, int(payload.get("offset", 0)))
    except Exception:
        return 0


def _offset_to_cursor(offset: int) -> str:
    payload = json.dumps({"offset": max(0, offset)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8").rstrip("=")


def _request_from_event(event: dict[str, Any]) -> SearchRequest:
    params = _query_params(event)
    return SearchRequest(
        client_id=(params.get("client_id") or params.get("clientId") or "").strip() or None,
        pet_id=(params.get("pet_id") or params.get("petId") or "").strip() or None,
        q=(params.get("q") or "").strip(),
        page=_parse_positive_int(params.get("page"), 1),
        page_size=_parse_positive_int(params.get("page_size") or params.get("pageSize"), DEFAULT_PAGE_SIZE, maximum=MAX_PAGE_SIZE),
        cursor=_cursor_to_offset(params.get("cursor")),
        sort=(params.get("sort") or "relevance").strip().lower(),
    )


def _source_page_url(pdf_id: str, page_number: int) -> str:
    return f"{DEFAULT_SOURCE_PAGE_PREFIX}/{pdf_id}/pages/{page_number}"


def _normalize_document_family(value: Any) -> str:
    family = str(value or "").strip().lower()
    return family or "other"


def _document_icon_index(document_family: Any, filename: Any = "") -> int:
    family = _normalize_document_family(document_family)
    filename_text = str(filename or "").strip().lower()
    if "lab" in family or "lab" in filename_text:
        return 2
    if any(token in family or token in filename_text for token in ("notes", "note-line", "note")) or "in" in family or "in" in filename_text:
        return 1
    return DOCUMENT_FAMILY_ICON_INDEX.get(family, 7)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    pdf_id = str(row.get("pdf_id") or row.get("source_reference_id") or row.get("document_id") or "")
    page_number = int(row.get("page_number") or 1)
    hit_type = str(row.get("hit_type") or ("ocr_page" if row.get("ocr_page_id") else "page"))
    document_family = _normalize_document_family(
        row.get("document_family")
        or (row.get("metadata") or {}).get("document_family") if isinstance(row.get("metadata"), dict) else None
    )
    filename = row.get("filename") or row.get("original_filename")
    return {
        "document_id": str(row.get("document_id") or ""),
        "pdf_id": pdf_id,
        "client_id": row.get("client_id"),
        "pet_id": row.get("pet_id"),
        "filename": filename,
        "document_family": document_family,
        "document_icon_index": _document_icon_index(document_family, filename),
        "document_icon_sheet": DEFAULT_ICON_SHEET_PATH,
        "page_id": row.get("page_id"),
        "page_number": page_number,
        "page_label": row.get("page_label"),
        "match_text": row.get("match_text") or row.get("extracted_text") or row.get("page_text") or "",
        "match_source": row.get("match_source") or ("rag_pdf_ocr_page" if hit_type == "ocr_page" else "pms_document_page"),
        "hit_type": hit_type,
        "source_page_url": _source_page_url(pdf_id, page_number) if pdf_id else "",
        "source_uri": row.get("source_uri"),
        "score": float(row.get("score") or 0.0),
        "page_kind": row.get("page_kind"),
        "ocr_method": row.get("ocr_method"),
        "ocr_status": row.get("ocr_status"),
        "source_reference_id": row.get("source_reference_id") or pdf_id,
    }


def _build_search_sql(request: SearchRequest) -> tuple[str, list[Any]]:
    predicates = ["TRUE"]
    args: list[Any] = []
    if request.client_id:
        predicates.append("sd.client_id = %s")
        args.append(request.client_id)
    if request.pet_id:
        predicates.append("sd.pet_id = %s")
        args.append(request.pet_id)

    query_terms = request.q.lower()
    if query_terms:
        predicates.append(
            "(LOWER(dp.extracted_text) LIKE %s OR LOWER(COALESCE(op.page_text, '')) LIKE %s OR LOWER(sd.filename) LIKE %s)"
        )
        pattern = f"%{query_terms}%"
        args.extend([pattern, pattern, pattern])

    if request.sort == "recent":
        order_by = "sd.created_at DESC, dp.page_number ASC"
    else:
        order_by = "CASE WHEN LOWER(COALESCE(dp.extracted_text, '')) LIKE %s THEN 0 ELSE 1 END, sd.created_at DESC, dp.page_number ASC"
        if query_terms:
            args.append(f"%{query_terms}%")
        else:
            args.append("%%")

    limit = request.page_size
    offset = request.cursor if request.cursor else (request.page - 1) * request.page_size
    args.extend([limit, offset])

    sql = f"""
        WITH search_hits AS (
            SELECT
                sd.id::text AS document_id,
                sd.source_reference_id AS pdf_id,
                sd.client_id,
                sd.pet_id,
                sd.filename,
                sd.filename AS original_filename,
                sd.source_uri,
                dp.id::text AS page_id,
                dp.page_number,
                dp.page_label,
                dp.extracted_text,
                dp.source_page_link,
                'page' AS hit_type,
                NULL::text AS page_kind,
                NULL::text AS ocr_method,
                NULL::text AS ocr_status,
                NULL::text AS document_family,
                NULL::jsonb AS metadata,
                1.0::double precision AS score,
                sd.created_at
            FROM pms_source_document sd
            JOIN pms_document_page dp ON dp.document_id = sd.id
            LEFT JOIN rag_pdf_ocr_page op
              ON op.pdf_id = sd.source_reference_id
             AND op.page_number = dp.page_number
            WHERE {' AND '.join(predicates)}
        )
        SELECT * FROM search_hits
        ORDER BY {order_by}
        LIMIT %s OFFSET %s
    """.strip()
    return sql, args


def _load_db_url() -> str:
    url = os.environ.get("EVH_PGDATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not url:
        raise RouteConfigError("Missing EVH_PGDATABASE_URL or DATABASE_URL for document search route")
    return url


def _query_database(request: SearchRequest) -> list[dict[str, Any]]:
    if psycopg is None:
        raise RouteConfigError("psycopg is not available in this environment")
    sql, args = _build_search_sql(request)
    with psycopg.connect(_load_db_url(), row_factory=psycopg.rows.dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def _response_payload(request: SearchRequest, rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rows = [row if row.get("source_page_url") else _normalize_row(row) for row in rows]
    next_cursor = _offset_to_cursor(request.cursor + len(normalized_rows)) if normalized_rows else None
    return {
        "route": DEFAULT_ROUTE_PATH,
        "query": {
            "client_id": request.client_id,
            "pet_id": request.pet_id,
            "q": request.q,
            "page": request.page,
            "page_size": request.page_size,
            "cursor": request.cursor or None,
            "sort": request.sort,
        },
        "count": len(normalized_rows),
        "items": normalized_rows,
        "pagination": {
            "next_cursor": next_cursor,
            "next_page": request.page + 1 if rows else None,
        },
        "source_truth": {
            "page_url_policy": "source_page_url is stable backend-generated proxy for exact document/page identity",
            "text_layer_policy": "text-layer hits can jump precisely; OCR hits remain page-level via rag_pdf_ocr_page",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def lambda_handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    method = _method(event)
    path = _path(event)

    if method == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": {
                "access-control-allow-origin": "*",
                "access-control-allow-methods": "GET,OPTIONS",
                "access-control-allow-headers": "content-type",
            },
            "body": "",
        }

    if path == "/health":
        return _json_response(200, {"ok": True})

    if path != DEFAULT_ROUTE_PATH:
        return _json_response(404, {"error": "not_found", "path": path})

    if method != "GET":
        return _json_response(405, {"error": "method_not_allowed", "method": method})

    request = _request_from_event(event)
    try:
        rows = _query_database(request)
    except RouteConfigError as exc:
        return _json_response(503, {"error": "route_not_configured", "message": str(exc)})

    return _json_response(200, _response_payload(request, rows))


if __name__ == "__main__":
    import argparse
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse

    parser = argparse.ArgumentParser(description="Serve the EVH document search route locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            event = {
                "rawPath": parsed.path,
                "rawQueryString": parsed.query,
                "requestContext": {"http": {"method": "GET"}},
            }
            response = lambda_handler(event, None)
            body = response.get("body", "")
            body_bytes = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
            self.send_response(int(response.get("statusCode", 200)))
            for key, value in response.get("headers", {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body_bytes)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.do_GET()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
