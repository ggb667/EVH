from __future__ import annotations

import json
import os
import sys
import time
import re
import urllib.request as urllib_request
from pathlib import Path
from typing import Any

INDEX_PATH = Path(__file__).resolve().parents[2] / "website" / "EVHInstinctPDFRAG" / "index.html"
CLIENT_CACHE: list[dict[str, Any]] | None = None
PETS_CACHE: dict[str, list[dict[str, Any]]] = {}


def _normalize_fragment_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _search_tokens(value: Any) -> list[str]:
    return re.findall(r"[A-Z0-9]+", str(value or "").upper())


def _build_fragment_index(items: list[dict[str, Any]], *, min_len: int = 3, max_len: int = 7) -> dict[str, set[str]]:
    """
    Build the typo-tolerant search index.

    Each searchable token is indexed by every contiguous substring from
    3 through 7 characters. This work is intentionally done on the index
    side so query matching can remain small and deterministic.

    Example for BURCHILL, the index contains fragments including:
        BURCHIL, BURCHI, BURCH, BURC, BUR
        URCHILL, URCHIL, URCHI, URCH, URC
        ...

    The fragment index allows query lookup to back off from longer
    fragments to shorter shared fragments without edit-distance or
    fuzzy-string calculations.
    """
    index: dict[str, set[str]] = {}
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        for token in _search_tokens(item.get("search_text") or ""):
            token_len = len(token)
            for start in range(token_len):
                stop = min(token_len, start + max_len)
                for end in range(start + min_len, stop + 1):
                    index.setdefault(token[start:end], set()).add(item_id)
    return index


def _fragment_scores(query: str, index: dict[str, set[str]], *, min_len: int = 3, max_len: int = 7) -> dict[str, int]:
    """
    Score typo-tolerant fragment matches while preferring the longest
    useful match.

    For each query token, advance through the token one character at a
    time. At each starting position, try fragment lengths from 7 down
    through 3. Stop backing off at that position once a match is found.

    Example: query BURCHELL against indexed BURCHILL

        position 0:
            BURCHEL -> miss
            BURCHE  -> miss
            BURCH   -> hit

        position 1:
            URCHELL -> miss
            URCHEL  -> miss
            URCHE   -> miss
            URCH    -> hit

    Because the index already contains every 3-7 character substring,
    the query side does not need to generate or retain a complete
    substring set.

    A candidate receives only its best fragment score for each query
    token. Scores from separate query tokens are then added together.

    This makes small spelling differences tolerant while favoring long
    shared fragments and preserving inexpensive hash lookups.
    """
    totals: dict[str, int] = {}
    for token in _search_tokens(query):
        per_token: dict[str, int] = {}
        token_len = len(token)
        for start in range(max(0, token_len - min_len + 1)):
            suffix = token[start:]
            for size in range(min(max_len, len(suffix)), min_len - 1, -1):
                key = suffix[:size]
                matches = index.get(key, ())
                if not matches:
                    continue
                for item_id in matches:
                    score = size
                    if score > per_token.get(item_id, 0):
                        per_token[item_id] = score
                break
        for item_id, score in per_token.items():
            totals[item_id] = totals.get(item_id, 0) + score
    return totals


def _pg_connect():
    required = ("EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(f"Missing PostgreSQL settings: {', '.join(missing)}")
    try:
        import psycopg
        return psycopg.connect(
            host=os.environ["EVH_PGHOST"], port=int(os.environ["EVH_PGPORT"]),
            dbname=os.environ["EVH_PGDATABASE"], user=os.environ["EVH_PGUSER"],
            password=os.environ["EVH_PGPASSWORD"], connect_timeout=10,
        )
    except ImportError:
        import pg8000.dbapi as pg  # type: ignore
        return pg.connect(
            host=os.environ["EVH_PGHOST"], port=int(os.environ["EVH_PGPORT"]),
            database=os.environ["EVH_PGDATABASE"], user=os.environ["EVH_PGUSER"],
            password=os.environ["EVH_PGPASSWORD"], timeout=10,
        )


def _openai_api_key() -> str:
    started = time.perf_counter()
    print("openai.embeddings.key.start", flush=True)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        print(f"openai.embeddings.key.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
        return key
    arn = os.environ.get("OPENAI_API_KEY_SECRET_ARN", "").strip()
    if not arn:
        raise RuntimeError("OPENAI_API_KEY or OPENAI_API_KEY_SECRET_ARN is required")
    import boto3
    secret = boto3.client("secretsmanager").get_secret_value(SecretId=arn).get("SecretString", "")
    if not secret:
        raise RuntimeError("OpenAI secret is empty")
    print(f"openai.embeddings.key.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
    return str(secret).strip()


def _openai_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    print(f"openai.{path}.start", flush=True)
    request = urllib_request.Request(
        f"https://api.openai.com/v1/{path}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {_openai_api_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    print(f"openai.{path}.urlopen.start", flush=True)
    try:
        with urllib_request.urlopen(request, timeout=90) as response:
            print(f"openai.{path}.urlopen.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
            data = json.loads(response.read().decode())
    except Exception as exc:
        print(f"openai.{path}.urlopen.error type={type(exc).__name__} message={exc} elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
        raise
    print(f"openai.{path}.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
    return data


def _openai_responses_with_retry(payload: dict[str, Any], *, initial_max_output_tokens: int, retry_max_output_tokens: int) -> dict[str, Any]:
    payload1 = dict(payload)
    payload1["max_output_tokens"] = initial_max_output_tokens
    data = _openai_json("responses", payload1)
    if data.get("status") == "incomplete":
        details = data.get("incomplete_details") or {}
        if str(details.get("reason") or "") == "max_output_tokens":
            payload2 = dict(payload)
            payload2["max_output_tokens"] = retry_max_output_tokens
            data = _openai_json("responses", payload2)
            if data.get("status") == "incomplete":
                details2 = data.get("incomplete_details") or {}
                if str(details2.get("reason") or "") == "max_output_tokens":
                    raise RuntimeError(
                        "OpenAI Responses API returned incomplete output twice due to max_output_tokens"
                    )
    return data


def _embed(question: str) -> list[float]:
    started = time.perf_counter()
    data = _openai_json("embeddings", {
        "model": os.environ.get("RAG_UI_EMBEDDING_MODEL", "text-embedding-3-small"),
        "input": question,
    })
    vector = ((data.get("data") or [{}])[0]).get("embedding") or []
    if not vector:
        raise RuntimeError("Embedding response contained no vector")
    print(f"embedding.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
    return [float(value) for value in vector]


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def load_clients(*, force: bool = False) -> list[dict[str, Any]]:
    global CLIENT_CACHE
    if CLIENT_CACHE is not None and not force:
        return CLIENT_CACHE
    connection = _pg_connect()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            select account_id,
                   coalesce(nullif(owner_name, ''), nullif(pims_code, ''), account_id) as label,
                   coalesce(nullif(pims_code, ''), account_id) as secondary
            from public.instinct_owner_lookup_norm
            where account_id is not null and account_id <> ''
            order by lower(coalesce(owner_name_last_first, owner_name, pims_code, account_id)),
                     lower(coalesce(pims_code, account_id))
        """)
        CLIENT_CACHE = [
            {"id": str(row[0]), "label": str(row[1]), "secondary": str(row[2] or "")}
            for row in cursor.fetchall()
        ]
        return CLIENT_CACHE
    finally:
        cursor.close(); connection.close()


def load_pets(client_id: str, *, force: bool = False) -> list[dict[str, Any]]:
    client_id = str(client_id or "").strip()
    if not client_id:
        return []
    if client_id in PETS_CACHE and not force:
        return PETS_CACHE[client_id]
    connection = _pg_connect()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            select patient_id::text,
                   coalesce(nullif(patient_name, ''), nullif(patient_pims_code, ''), patient_id::text),
                   coalesce(nullif(patient_pims_code, ''), patient_id::text),
                   coalesce(species, ''), coalesce(breed, '')
            from public.instinct_patient_lookup
            where account_id = %s
            order by lower(coalesce(patient_name, patient_pims_code, patient_id::text))
        """, (client_id,))
        pets = [
            {"id": str(r[0]), "label": str(r[1]), "secondary": str(r[2] or ""),
             "clientId": client_id, "species": str(r[3] or ""), "breed": str(r[4] or "")}
            for r in cursor.fetchall()
        ]
        PETS_CACHE[client_id] = pets
        return pets
    finally:
        cursor.close(); connection.close()


def _search_loaded_options(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    normalized = _normalize_fragment_text(query)
    tokens = _search_tokens(query)
    ordered = sorted(items, key=lambda item: (str(item.get("label") or "").lower(), str(item.get("secondary") or "").lower()))
    if len(normalized) < 3 or not tokens:
        return ordered
    search_index = _build_fragment_index(
        [
            {
                "id": str(item.get("id") or ""),
                "search_text": _normalize_fragment_text(
                    " ".join(str(item.get(field, "")) for field in ("label", "secondary", "id"))
                ),
            }
            for item in ordered
        ]
    )
    scores = _fragment_scores(query, search_index)
    if not scores:
        return ordered
    by_id = {str(item.get("id") or ""): item for item in ordered}
    return [by_id[item_id] for item_id in sorted(scores, key=scores.get, reverse=True) if item_id in by_id]


def load_patient_documents(client_id: str, patient_id: str) -> list[dict[str, Any]]:
    started = time.perf_counter()
    connection = _pg_connect(); cursor = connection.cursor()
    try:
        cursor.execute("""
            select document_pdf_id::text,
                   coalesce(nullif(original_filename, ''), nullif(source_name, ''), document_pdf_id::text),
                   coalesce(source_uri, '')
            from public.pms_page_chunk
            where client_instinct_uuid = %s and patient_id = %s and document_pdf_id is not null
            group by document_pdf_id, original_filename, source_name, source_uri
            order by lower(coalesce(nullif(original_filename, ''), nullif(source_name, ''), document_pdf_id::text))
        """, (client_id, patient_id))
        return [{"document_id": str(r[0]), "title": str(r[1]), "source_uri": str(r[2] or "")} for r in cursor.fetchall()]
    finally:
        cursor.close(); connection.close()
        print(f"documents.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)


def search_patient_chunks(client_id: str, patient_id: str, question: str) -> list[dict[str, Any]]:
    embedding = _embed(question)
    vector = _vector_literal(embedding)
    started = time.perf_counter()
    print("db.connect.start", flush=True)
    connection = _pg_connect(); cursor = connection.cursor()
    try:
        print("vector_query.start", flush=True)
        cursor.execute("""
            select document_pdf_id::text,
                   coalesce(nullif(original_filename, ''), nullif(source_name, ''), document_pdf_id::text),
                   page_number, source_name, source_uri, chunk_text, metadata,
                   embedding <=> %s::vector as distance
            from public.pms_page_chunk
            where client_instinct_uuid = %s
              and patient_id = %s
              and chunk_text is not null
              and embedding is not null
            order by embedding <=> %s::vector, page_number asc, chunk_index asc
        """, (vector, client_id, patient_id, vector))
        rows = cursor.fetchall()
    finally:
        cursor.close(); connection.close()
        print(f"db.connect.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
        print(f"vector_query.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f} result_count={len(rows) if 'rows' in locals() else 0}", flush=True)
    hits = []
    for doc_id, title, page, source_name, source_uri, text, metadata, distance in rows:
        page = int(page or 1)
        source_uri = str(source_uri or "")
        hits.append({
            "document_id": str(doc_id), "document_title": str(title), "page_number": page,
            "page_label": f"Page {page}", "source_name": str(source_name or ""),
            "source_page_url": f"{source_uri}#page={page}" if source_uri.startswith(("http://", "https://")) else "",
            "snippet": str(text or ""), "confidence": max(0.0, 1.0 - float(distance or 0.0)),
            "metadata": metadata if isinstance(metadata, dict) else {},
        })
    return hits


def _extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if isinstance(content.get("text"), str):
                return content["text"]
    return ""


def answer_question(client_id: str, patient_id: str, question: str) -> dict[str, Any]:
    started = time.perf_counter()
    print("rag.start", flush=True)
    documents = load_patient_documents(client_id, patient_id)
    hits = search_patient_chunks(client_id, patient_id, question)
    unique_hits: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for hit in hits:
        key = (hit.get("document_id"), hit.get("page_number"), hit.get("snippet"))
        if key in seen:
            continue
        seen.add(key)
        unique_hits.append(hit)
    evidence = [
        {
            "document_id": h["document_id"],
            "page_number": h["page_number"],
            "title": h["document_title"],
            "text": h["snippet"],
            "source_page_url": h.get("source_page_url", ""),
        }
        for h in unique_hits[:50]
    ]
    prompt = {
        "question": question,
        "documents": documents,
        "retrieved_evidence": evidence,
        "instructions": (
            "Answer only from retrieved_evidence. Return JSON with keys answer and references. "
            "references must be an array of objects containing document_id and page_number, and may only cite evidence actually used. "
            "Do not invent URLs or document IDs. If evidence is insufficient, say so in answer."
        ),
    }
    data = _openai_responses_with_retry({
        "model": os.environ.get("RAG_UI_LLM_MODEL", "gpt-5-mini"),
        "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(prompt)}]}],
        "text": {"format": {"type": "json_object"}},
    }, initial_max_output_tokens=1200, retry_max_output_tokens=2400)
    if data.get("status") == "incomplete":
        details = data.get("incomplete_details") or {}
        raise RuntimeError(
            f"OpenAI Responses API returned incomplete output: reason={details.get('reason')!r}"
        )
    raw = _extract_output_text(data)
    try:
        llm = json.loads(raw)
    except Exception:
        llm = {"answer": raw.strip() or "I could not produce an answer.", "references": []}

    hit_by_key = {(h["document_id"], h["page_number"]): h for h in hits}
    refs = []
    seen = set()
    for ref in llm.get("references") or []:
        try:
            key = (str(ref.get("document_id")), int(ref.get("page_number")))
        except Exception:
            continue
        hit = hit_by_key.get(key)
        if hit and key not in seen:
            seen.add(key)
            refs.append({k: hit[k] for k in ("document_id", "document_title", "page_number", "page_label", "source_page_url")})
    result = {
        "answer": str(llm.get("answer") or ""), "references": refs,
        "retrieval": {
            "retrieved_chunks": len(hits),
            "evidence_chunks": len(evidence),
            "documents": len({h['document_id'] for h in hits}),
        },
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    print(f"rag.done elapsed_ms={(time.perf_counter() - started) * 1000:.1f}", flush=True)
    return result


def _params(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("queryStringParameters") or {}


def _body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if isinstance(body, dict): return body
    if not body: return {}
    try: return json.loads(body)
    except Exception: return {}


def _response(status: int, payload: Any, content_type: str = "application/json; charset=utf-8") -> dict[str, Any]:
    return {"statusCode": status, "headers": {"content-type": content_type, "access-control-allow-origin": "*"},
            "body": payload if isinstance(payload, str) else json.dumps(payload)}


def lambda_handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    path = str(event.get("rawPath") or event.get("path") or "/")
    method = str(((event.get("requestContext") or {}).get("http") or {}).get("method") or event.get("httpMethod") or "GET").upper()
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": {"access-control-allow-origin": "*", "access-control-allow-methods": "GET,POST,OPTIONS", "access-control-allow-headers": "content-type"}, "body": ""}
    try:
        if path == "/__diag__":
            import importlib.util
            return _response(200, {
                "cwd": os.getcwd(),
                "task_root": os.environ.get("LAMBDA_TASK_ROOT"),
                "sys_path": sys.path,
                "pg8000_spec": str(importlib.util.find_spec("pg8000")),
                "psycopg_spec": str(importlib.util.find_spec("psycopg")),
                "psycopg_binary_spec": str(importlib.util.find_spec("psycopg_binary")),
            })
        if path in ("/", "/index.html"):
            return _response(200, INDEX_PATH.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if path == "/health": return _response(200, {"ok": True})
        if path == "/api/clients": return _response(200, {"items": load_clients()})
        if path == "/api/pets": return _response(200, {"items": load_pets(str(_params(event).get("client_id") or ""))})
        if path == "/api/options":  # compatibility with older UI/tests
            p = _params(event); kind = str(p.get("kind") or "client")
            query = str(p.get("q") or "").strip()
            items = load_pets(str(p.get("clientId") or p.get("client_id") or "")) if kind == "pet" else load_clients()
            items = _search_loaded_options(items, query) if query else items
            return _response(200, {"kind": kind, "threshold": 3, "count": len(items), "items": items})
        if path in ("/api/ask", "/api/rag/answer"):
            p = {**_params(event), **_body(event)}
            client_id = str(p.get("client_id") or p.get("clientId") or "").strip()
            patient_id = str(p.get("patient_id") or p.get("pet_id") or p.get("petId") or "").strip()
            question = str(p.get("question") or p.get("q") or "").strip()
            if not client_id or not patient_id or not question:
                return _response(400, {"error": "client_id, patient_id and question are required"})
            return _response(200, answer_question(client_id, patient_id, question))
        return _response(404, {"error": "not_found", "path": path})
    except Exception as exc:
        print(f"RAG error: {type(exc).__name__}: {exc}", flush=True)
        return _response(500, {"error": "server_error", "detail": str(exc)})
