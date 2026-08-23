from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs

from scripts.rag_ui.catalog import load_catalog, load_pet_context_chunks, search_document_hits

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_PATH = STATIC_DIR / "index.html"


def _app_version() -> str:
    env_version = os.environ.get("RAG_UI_VERSION", "").strip()
    if env_version:
      return env_version
    try:
        root = Path(__file__).resolve().parents[3]
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _headers(content_type: str) -> dict[str, str]:
    return {
        "content-type": content_type,
        "cache-control": "no-store",
    }


def _json_response(status_code: int, payload: dict) -> dict:
    payload = dict(payload)
    metadata = dict(payload.get("metadata") or {})
    metadata["version"] = _app_version()
    payload["metadata"] = metadata
    return {
        "statusCode": status_code,
        "headers": _headers("application/json; charset=utf-8"),
        "body": json.dumps(payload, indent=2, sort_keys=True),
    }


def _html_response(status_code: int, body: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": _headers("text/html; charset=utf-8"),
        "body": body,
    }


def _path(event: dict) -> str:
    return str(event.get("rawPath") or event.get("path") or "/")


def _method(event: dict) -> str:
    request_context = event.get("requestContext") or {}
    http = request_context.get("http") or {}
    return str(http.get("method") or event.get("httpMethod") or "GET").upper()


def _query_params(event: dict) -> dict[str, str]:
    params = event.get("queryStringParameters")
    if isinstance(params, dict) and params:
        return {str(key): str(value) for key, value in params.items() if value is not None}

    raw_query = str(event.get("rawQueryString") or "")
    if not raw_query:
        return {}

    parsed = parse_qs(raw_query, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _serve_index() -> dict:
    return _html_response(200, INDEX_PATH.read_text(encoding="utf-8"))


def _serve_version() -> dict:
    return _json_response(200, {"version": _app_version()})


def _serve_options(event: dict) -> dict:
    params = _query_params(event)
    kind = (params.get("kind") or "client").strip().lower()
    query = params.get("q") or ""
    client_id = params.get("clientId") or params.get("client_id") or ""
    limit_text = params.get("limit") or "10"
    try:
        limit = max(1, min(200, int(limit_text)))
    except ValueError:
        limit = 10

    catalog = load_catalog()
    if kind == "pet":
        items = catalog.search_pets(client_id or None, query, limit=limit)
    else:
        items = catalog.search_clients(query, limit=limit)

    return _json_response(
        200,
        {
            "kind": kind,
            "query": query,
            "clientId": client_id or None,
            "threshold": 3,
            "count": len(items),
            "items": items,
        },
    )


def _serve_rag_search(event: dict) -> dict:
    params = _query_params(event)
    client_id = params.get("client_id") or params.get("clientId") or ""
    pet_id = params.get("pet_id") or params.get("petId") or ""
    question = params.get("q") or params.get("question") or ""
    page = int(params.get("page") or "1")
    page_size = int(params.get("page_size") or params.get("pageSize") or "8")
    hits = search_document_hits(client_id, pet_id or None, question, limit=max(1, min(20, page_size)))
    return _json_response(
        200,
        {
            "client_id": client_id or None,
            "pet_id": pet_id or None,
            "question": question,
            "answer": hits[0]["snippet"] if hits else "I couldn't find a matching PDF hit in the available documents.",
            "items": hits,
            "citations": [
                {
                    "document_id": hit["document_id"],
                    "page_number": hit["page_number"],
                    "source_page_url": hit["source_page_url"],
                    "snippet": hit["snippet"],
                }
                for hit in hits
            ],
            "retrieval": {
                "matched_documents": len({hit["document_id"] for hit in hits}),
                "matched_pages": len(hits),
            },
        },
    )


def _serve_context(event: dict) -> dict:
    params = _query_params(event)
    client_id = params.get("client_id") or params.get("clientId") or ""
    pet_id = params.get("pet_id") or params.get("petId") or ""
    if not client_id or not pet_id:
        return _json_response(400, {"error": "client_id and pet_id are required"})
    chunks = load_pet_context_chunks(client_id, pet_id, limit=None)
    return _json_response(
        200,
        {
            "client_id": client_id,
            "pet_id": pet_id,
            "count": len(chunks),
            "items": chunks,
        },
    )


def lambda_handler(event: dict, context: object | None = None) -> dict:
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

    if path in {"/", "/index.html"}:
        return _serve_index()

    if path == "/api/options":
        return _serve_options(event)

    if path == "/api/version":
        return _serve_version()

    if path == "/api/rag/documents/search":
        return _serve_rag_search(event)

    if path == "/api/rag/context":
        return _serve_context(event)

    if path == "/health":
        return _json_response(200, {"ok": True})

    return _json_response(404, {"error": "not_found", "path": path})


if __name__ == "__main__":
    import argparse
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse

    parser = argparse.ArgumentParser(description="Serve the Pinkie RAG UI locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
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
            if isinstance(body, str):
                body_bytes = body.encode("utf-8")
            else:
                body_bytes = json.dumps(body).encode("utf-8")

            self.send_response(int(response.get("statusCode", 200)))
            for key, value in response.get("headers", {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body_bytes)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
