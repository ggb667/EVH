from __future__ import annotations

import json
import os
import subprocess
import time
import traceback
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode
from pathlib import Path
from urllib import request as urllib_request

import boto3

from scripts.rag_ui.catalog import load_catalog, load_patient_documents, query_options_from_postgres, search_pet_chunks_by_embedding

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_PATH = Path(__file__).resolve().parents[2] / "website" / "EVHInstinctPDFRAG" / "index.html"


@dataclass(frozen=True)
class _InstinctUrlCacheEntry:
    url: str
    expires_at: float


_INSTINCT_URL_CACHE: dict[tuple[str, int], _InstinctUrlCacheEntry] = {}


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


def _openai_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key

    secret_arn = os.environ.get("OPENAI_API_KEY_SECRET_ARN", "").strip()
    if not secret_arn:
        raise RuntimeError("OPENAI_API_KEY_SECRET_ARN is required for LLM answer generation.")

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret = str(response.get("SecretString") or "").strip()
    if not secret:
        raise RuntimeError("Secrets Manager returned an empty OpenAI API key.")
    return secret


def _secret_string_json(secret_arn: str) -> dict:
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret = str(response.get("SecretString") or "").strip()
    if not secret:
        raise RuntimeError(f"Secrets Manager returned an empty secret for {secret_arn!r}.")
    try:
        data = json.loads(secret)
    except json.JSONDecodeError:
        return {"secret_string": secret}
    return data if isinstance(data, dict) else {"secret_string": secret}


def _llm_model() -> str:
    return os.environ.get("RAG_UI_LLM_MODEL", "gpt-5.1").strip() or "gpt-5.1"


def _instinct_base_url() -> str:
    return os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com").strip().rstrip("/")


def _instinct_graphql_url() -> str:
    return os.environ.get("INSTINCT_GRAPHQL_URL", "https://evh.api.instinctvet.com").strip().rstrip("/")


def _instinct_token() -> str:
    token = os.environ.get("TOKEN", "").strip()
    if token:
        return token
    secret_arn = os.environ.get("INSTINCT_CLIENT_SECRET_ARN", "").strip()
    if not secret_arn:
        raise RuntimeError("INSTINCT_CLIENT_SECRET_ARN is required for document URLs.")
    secret_data = _secret_string_json(secret_arn)
    client_id = str(
        secret_data.get("client_id")
        or secret_data.get("clientId")
        or secret_data.get("INSTINCT_CLIENT_ID")
        or secret_data.get("username")
        or ""
    ).strip()
    client_secret = str(
        secret_data.get("client_secret")
        or secret_data.get("clientSecret")
        or secret_data.get("INSTINCT_CLIENT_SECRET")
        or secret_data.get("password")
        or ""
    ).strip()
    if not client_id or not client_secret:
        raise RuntimeError("Instinct secret is missing client_id/client_secret fields.")
    token_url = f"{_instinct_base_url()}/v1/auth/token"
    payload = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")
    request = urllib_request.Request(
        token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    token = str(data.get("access_token") or data.get("token") or data.get("jwt") or "").strip()
    if not token:
        raise RuntimeError(f"Instinct token response missing access token field: {data}")
    return token


def _create_chart_file_url(chart_id: str, inline: bool = True) -> str:
    query = """
query medicalHistoryVisits($patientId: ID!, $chartTypes: [ChartType]) {
  patient(id: $patientId) { id }
}
""".strip()
    mutation = """
mutation createChartFileUrl($id: ID!, $inline: Boolean) {
  createChartFileUrl(id: $id, inline: $inline)
}
""".strip()
    payload = {
        "query": mutation,
        "variables": {"id": chart_id, "inline": inline},
    }
    request = urllib_request.Request(
        _instinct_graphql_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_instinct_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], indent=2, sort_keys=True))
    url = (((data.get("data") or {}).get("createChartFileUrl")) or "").strip()
    if not url:
        raise RuntimeError(f"No download URL returned for chart file id={chart_id!r}")
    return url


def _verify_instinct_url(url: str, timeout: int = 30) -> bool:
    if not url:
        return False
    for method in ("HEAD", "GET"):
        try:
            request = urllib_request.Request(url, method=method)
            with urllib_request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if 200 <= int(status) < 400:
                    return True
        except Exception:
            continue
    return False


def _resolve_cached_instinct_url(document_id: str, page_number: int, *, force_refresh: bool = False) -> str:
    key = (str(document_id or "").strip(), int(page_number or 1))
    if not key[0]:
        raise ValueError("document_id is required")
    now = time.time()
    cached = _INSTINCT_URL_CACHE.get(key)
    if cached and not force_refresh and cached.expires_at > now and _verify_instinct_url(cached.url):
        return cached.url

    url = _create_chart_file_url(key[0], inline=True)
    expires_at = now + float(os.environ.get("RAG_UI_INSTINCT_URL_TTL_SECONDS", "1800").strip() or 1800)
    separator = "&" if "?" in url else "?"
    url = f"{url}{separator}page={key[1]}"
    if not _verify_instinct_url(url):
        raise RuntimeError(f"Instinct URL did not verify for document_id={key[0]!r} page={key[1]}")
    _INSTINCT_URL_CACHE[key] = _InstinctUrlCacheEntry(url=url, expires_at=expires_at)
    return url


def _summarize_context_chunks(chunks: list[dict]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(chunks[:8], start=1):
        lines.append(
            "\n".join(
                [
                    f"[{idx}] {item.get('document_title', 'Source PDF')} — {item.get('page_label', 'Page')}",
                    f"Source: {item.get('source_page_url', '')}",
                    f"Text: {item.get('snippet', '')}",
                ]
            )
        )
    return "\n\n".join(lines)


def _extract_citations(chunks: list[dict]) -> list[dict]:
    return [
        {
            "document_id": hit["document_id"],
            "page_number": hit["page_number"],
            "source_page_url": hit["source_page_url"],
            "snippet": hit["snippet"],
            "confidence": hit.get("confidence", 0.0),
        }
        for hit in chunks
    ]


def _build_reference_map(documents: list[dict], chunks: list[dict]) -> list[dict]:
    by_id = {str(doc.get("document_id") or ""): doc for doc in documents}
    seen: set[tuple[str, int]] = set()
    references: list[dict] = []
    for hit in chunks:
        document_id = str(hit.get("document_id") or "").strip()
        page_number = int(hit.get("page_number") or 0)
        key = (document_id, page_number)
        if not document_id or key in seen:
            continue
        seen.add(key)
        doc = by_id.get(document_id, {})
        references.append(
            {
                "document_id": document_id,
                "page_number": page_number,
                "document_title": doc.get("document_title") or hit.get("document_title"),
                "source_uri": doc.get("source_uri") or hit.get("source_page_url"),
            }
        )
    return references


def _extract_output_text(payload: dict) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = payload.get("output") or []
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                value = content.get("text") or content.get("value")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return "\n".join(parts).strip()


def _retrieval_planner_prompt(question: str) -> dict:
    return {
        "role": "system",
        "content": [
            {
                "type": "input_text",
                "text": (
                    "You are a strict retrieval planner for a patient-record RAG system.\n"
                    "Choose the smallest sufficient retrieval intent from this menu:\n"
                    "- SEMANTIC — retrieve the most relevant chunks by meaning\n"
                    "- RECENT — retrieve the newest relevant chunks first\n"
                    "- TIMELINE — retrieve date-bearing records in chronological order\n"
                    "- EXHAUSTIVE — retrieve broadly and completely when completeness matters\n"
                    "- DOCUMENT — retrieve a specific document, date, or document type\n\n"
                    "Rules:\n"
                    "- Do not invent SQL, table names, indexes, limits, or implementation details.\n"
                    "- Do not answer the question.\n"
                    "- Choose the retrieval intent based on the user's information need.\n"
                    "- If the user asks for ever / all / every / complete history / list all, use EXHAUSTIVE.\n"
                    "- If the user asks for the latest / last / most recent, use RECENT.\n"
                    "- If the user asks for dates / timeline / history over time, use TIMELINE.\n"
                    "- If the user points to a specific report / date / document type, use DOCUMENT.\n"
                    "- If the user asks for the most relevant record without requiring completeness or chronology, use SEMANTIC.\n"
                    "- If one intent is not enough, return multiple requests.\n\n"
                    "Return only JSON. The output shape must be either:\n"
                    '{"retrieval":"SEMANTIC","query":"..."}\n'
                    "or:\n"
                    '{"requests":[{"retrieval":"RECENT","query":"..."},{"retrieval":"TIMELINE","query":"..."}]}\n'
                ),
            }
        ],
    }


def _answer_prompt(question: str, sources: list[dict]) -> dict:
    return {
        "role": "system",
        "content": [
            {
                "type": "input_text",
                "text": (
                    "You are a careful patient-record assistant.\n"
                    "Use only the provided retrieved evidence to answer the user's question.\n"
                    "Do not invent facts. Do not use outside knowledge if the evidence does not support it.\n"
                    "If the evidence does not contain the answer, say so plainly.\n"
                    "Prefer the retrieved evidence over memory or guessin'.\n"
                    "When useful, mention the source document(s) and page number(s).\n"
                    "Keep the answer concise and clinically useful.\n"
                    "If the retrieved evidence is grouped by document, respect that grouping.\n"
                    "If multiple documents support the answer, synthesize them clearly.\n\n"
                    "Return JSON with answer text only, not markdown."
                ),
            }
        ],
    }


def _parse_planner_json(payload_text: str) -> dict:
    data = json.loads(payload_text)
    if isinstance(data, dict) and "requests" in data:
        requests = []
        for req in data.get("requests") or []:
            if not isinstance(req, dict):
                continue
            retrieval = str(req.get("retrieval") or "").strip().upper()
            query = str(req.get("query") or "").strip()
            if retrieval and query:
                requests.append({"retrieval": retrieval, "query": query})
        return {"requests": requests}
    retrieval = str(data.get("retrieval") or "").strip().upper()
    query = str(data.get("query") or "").strip()
    if not retrieval or not query:
        raise ValueError("planner output missing retrieval or query")
    return {"retrieval": retrieval, "query": query}


def _normalize_question_for_routing(question: str) -> str:
    return re.sub(r"\s+", " ", str(question or "").strip().lower())


def _strip_question_prefix(question: str) -> str:
    text = _normalize_question_for_routing(question)
    for _ in range(4):
        updated = re.sub(r"^(what|when|which|who|how|is|are|was|were|does|do|did|can|could|would|should)\s+", "", text)
        updated = re.sub(r"^(is there|are there|was there|were there|do we have|did we have)\s+", "", updated)
        updated = re.sub(r"^(please\s+|tell me\s+|show me\s+|find\s+|what about\s+)", "", updated)
        updated = re.sub(r"^(the|a|an|this|that)\s+", "", updated)
        updated = re.sub(r"\s+(please|thanks?|thank you|say)$", "", updated)
        updated = updated.strip(" ?.,")
        if updated == text:
            break
        text = updated
    return text.strip(" ?.,")


def _deterministic_retrieval_plan(question: str) -> dict | None:
    text = _normalize_question_for_routing(question)
    if not text:
        return None

    document_patterns = [
        r"\b(march|april|may|june|july|august|september|october|november|december|january|february)\b.*\b(report|lab|labs|note|notes|record|records|chart|invoice|estimate|consent|vaccine|vaccination|dental|medical)\b",
        r"\b(report|lab report|lab results|medical notes|medical note|dental chart|dental record|vaccine record|vaccination record|invoice|estimate|consent form|document)\b",
        r"\bthis\s+(report|lab|note|record|chart|invoice|estimate|document)\b",
    ]
    if any(re.search(pattern, text) for pattern in document_patterns):
        return {"retrieval": "DOCUMENT", "query": _strip_question_prefix(question)}

    if re.search(r"\b(what\s+dates|date[s]? did we|when did we|timeline|history over time|visit history|major events)\b", text):
        return {"retrieval": "TIMELINE", "query": _strip_question_prefix(question)}

    if re.search(r"\b(ever|all|every|complete history|list all|how many times|has he ever|has she ever|have they ever)\b", text):
        return {"retrieval": "EXHAUSTIVE", "query": _strip_question_prefix(question)}

    if re.search(r"\b(last|latest|most recent|most recently)\b", text):
        subject = _strip_question_prefix(question)
        subject = re.sub(r"\b(last|latest|most recent|most recently)\b", "", subject).strip(" ?.,")
        subject = re.sub(r"\b(date|date of)\b", "", subject).strip(" ?.,")
        subject = re.sub(r"\b(the|a|an)\b", "", subject).strip(" ?.,")
        subject = re.sub(r"\s+", " ", subject).strip()
        return {"retrieval": "RECENT", "query": subject or _strip_question_prefix(question)}

    if re.search(r"\b(most relevant|relevant record|find|search for|tell me about|what about|show me|does he have|did he have|has he had)\b", text):
        return {"retrieval": "SEMANTIC", "query": _strip_question_prefix(question)}

    return None


def _plan_retrieval(question: str, sources: list[dict] | None = None) -> dict:
    prompt = _retrieval_planner_prompt(question)
    prompt["content"][0]["text"] += f"\n\nUser question: {question}\n"
    if sources:
        prompt["content"][0]["text"] += f"Retrieved source count hint: {len(sources)}\n"
    payload = {
        "model": _llm_model(),
        "input": [prompt],
        "temperature": 0,
        "max_output_tokens": 300,
        "text": {"format": {"type": "json_object"}},
    }
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=_llm_model(),
            temperature=0,
            api_key=_openai_api_key(),
        )
        response = model.invoke([
            SystemMessage(content=prompt["content"][0]["text"]),
            HumanMessage(content=question),
        ])
        text = getattr(response, "content", "")
        if isinstance(text, str) and text.strip():
            return _parse_planner_json(text.strip())
    except Exception:
        pass

    request = urllib_request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = _extract_output_text(data)
    if not text:
        raise RuntimeError(f"OpenAI planner response missing text: {json.dumps(data)[:500]}")
    return _parse_planner_json(text)


def _retrieve_with_intent(intent: str, query: str, client_id: str, pet_id: str | None) -> tuple[list[dict], dict[str, float]]:
    intent = str(intent or "").strip().upper()
    handlers = {
        "SEMANTIC": _retrieve_semantic,
        "RECENT": _retrieve_recent,
        "TIMELINE": _retrieve_timeline,
        "EXHAUSTIVE": _retrieve_exhaustive,
        "DOCUMENT": _retrieve_document,
    }
    handler = handlers.get(intent, _retrieve_semantic)
    return handler(query, client_id, pet_id)


def _retrieve_semantic(query: str, client_id: str, pet_id: str | None) -> tuple[list[dict], dict[str, float]]:
    return search_pet_chunks_by_embedding(client_id, pet_id, query)


def _retrieve_recent(query: str, client_id: str, pet_id: str | None) -> tuple[list[dict], dict[str, float]]:
    return search_pet_chunks_by_embedding(client_id, pet_id, query)


def _retrieve_timeline(query: str, client_id: str, pet_id: str | None) -> tuple[list[dict], dict[str, float]]:
    return search_pet_chunks_by_embedding(client_id, pet_id, query)


def _retrieve_exhaustive(query: str, client_id: str, pet_id: str | None) -> tuple[list[dict], dict[str, float]]:
    return search_pet_chunks_by_embedding(client_id, pet_id, query)


def _retrieve_document(query: str, client_id: str, pet_id: str | None) -> tuple[list[dict], dict[str, float]]:
    return search_pet_chunks_by_embedding(client_id, pet_id, query)


def _execute_planned_retrieval(question: str, client_id: str, pet_id: str) -> tuple[list[dict], dict[str, float], dict]:
    plan = _deterministic_retrieval_plan(question) or _plan_retrieval(question, sources=[])
    if "requests" in plan:
        merged_hits: list[dict] = []
        merged_timing: dict[str, float] = {}
        for request in plan.get("requests") or []:
            hits, timing = _retrieve_with_intent(request["retrieval"], request["query"], client_id, pet_id or None)
            merged_hits.extend(hits)
            for key, value in timing.items():
                merged_timing[key] = max(merged_timing.get(key, 0.0), float(value))
        return merged_hits, merged_timing, plan
    hits, timing = _retrieve_with_intent(plan["retrieval"], plan["query"], client_id, pet_id or None)
    return hits, timing, plan


def _call_openai_answer(question: str, context_chunks: list[dict]) -> str:
    context_text = _summarize_context_chunks(context_chunks)
    prompt = (
        "You answer questions using only the provided context. "
        "If the context does not contain the answer, say you cannot find it in the retrieved documents. "
        "Return a concise answer and mention source page numbers in parentheses.\n\n"
        f"Question: {question}\n\nRetrieved context:\n{context_text}"
    )
    model_name = _llm_model()
    started = time.perf_counter()
    print(f"[RAG_TIMING] answer_model={model_name} answer_request_start", flush=True)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=model_name,
            temperature=0.2,
            api_key=_openai_api_key(),
        )
        response = model.invoke([
            SystemMessage(content="You are a precise RAG assistant."),
            HumanMessage(content=prompt),
        ])
        text = getattr(response, "content", "")
        if isinstance(text, str) and text.strip():
            elapsed = time.perf_counter() - started
            print(
                "[RAG_TIMING] answer_api_elapsed_seconds="
                f"{elapsed:.3f} status=ok incomplete_reason=none output_tokens=unknown total_answer_elapsed_seconds={elapsed:.3f}",
                flush=True,
            )
            return text.strip()
    except Exception:
        pass

    payload = {
        "model": model_name,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You answer questions using only the provided context. "
                            "If the context does not contain the answer, say you cannot find it in the retrieved documents. "
                            "Be concise and cite the most relevant source page numbers in parentheses."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Question: {question}\n\nRetrieved context:\n{context_text}",
                    }
                ],
            },
        ],
        "temperature": 0.2,
        "max_output_tokens": 400,
    }
    request = urllib_request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=90) as response:
        api_started = time.perf_counter()
        data = json.loads(response.read().decode("utf-8"))
        api_elapsed = time.perf_counter() - api_started
    text = _extract_output_text(data)
    status = str(data.get("status") or "ok")
    incomplete_reason = str((data.get("incomplete_details") or {}).get("reason") or data.get("incomplete_reason") or "none")
    output_tokens = (
        ((data.get("usage") or {}).get("output_tokens"))
        or ((data.get("usage") or {}).get("output_tokens_details") or {}).get("reasoning_tokens")
        or "unknown"
    )
    total_elapsed = time.perf_counter() - started
    print(
        "[RAG_TIMING] answer_api_elapsed_seconds="
        f"{api_elapsed:.3f} status={status} incomplete_reason={incomplete_reason} output_tokens={output_tokens} total_answer_elapsed_seconds={total_elapsed:.3f}",
        flush=True,
    )
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise RuntimeError(f"OpenAI response did not include output text: {json.dumps(data)[:500]}")


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

    started = time.perf_counter()
    items: list[dict]
    if os.environ.get("RAG_UI_DATA_PATH", "").strip() or os.environ.get("RAG_UI_DB_PATH", "").strip():
        catalog_started = time.perf_counter()
        catalog = load_catalog()
        catalog_elapsed = time.perf_counter() - catalog_started
        print(f"[RAG_TIMING] options_catalog_seconds={catalog_elapsed:.3f}", flush=True)

        search_started = time.perf_counter()
        if kind == "pet":
            items = catalog.search_pets(client_id or None, query)
        else:
            items = catalog.search_clients(query)
        search_elapsed = time.perf_counter() - search_started
        print(f"[RAG_TIMING] options_search_seconds={search_elapsed:.3f} count={len(items)}", flush=True)
    elif os.environ.get("EVH_PGHOST", "").strip():
        search_started = time.perf_counter()
        items = query_options_from_postgres(kind, query, client_id or None)
        search_elapsed = time.perf_counter() - search_started
        print(f"[RAG_TIMING] options_search_seconds={search_elapsed:.3f} count={len(items)}", flush=True)
    else:
        catalog_started = time.perf_counter()
        catalog = load_catalog()
        catalog_elapsed = time.perf_counter() - catalog_started
        print(f"[RAG_TIMING] options_catalog_seconds={catalog_elapsed:.3f}", flush=True)

        search_started = time.perf_counter()
        if kind == "pet":
            items = catalog.search_pets(client_id or None, query)
        else:
            items = catalog.search_clients(query)
        search_elapsed = time.perf_counter() - search_started
        print(f"[RAG_TIMING] options_search_seconds={search_elapsed:.3f} count={len(items)}", flush=True)

    response_started = time.perf_counter()
    payload = {
        "kind": kind,
        "query": query,
        "clientId": client_id or None,
        "threshold": 3,
        "count": len(items),
        "items": items,
    }
    response_elapsed = time.perf_counter() - response_started
    total_elapsed = time.perf_counter() - started
    print(f"[RAG_TIMING] options_response_seconds={response_elapsed:.3f} total_seconds={total_elapsed:.3f}", flush=True)

    return _json_response(200, payload)


def _serve_rag_search(event: dict) -> dict:
    params = _query_params(event)
    client_id = params.get("client_id") or params.get("clientId") or ""
    pet_id = params.get("pet_id") or params.get("petId") or ""
    question = params.get("q") or params.get("question") or ""
    hits, retrieval_timing = search_pet_chunks_by_embedding(client_id, pet_id or None, question)
    patient_documents = load_patient_documents(client_id, pet_id or None)
    return _json_response(
        200,
        {
            "client_id": client_id or None,
            "pet_id": pet_id or None,
            "question": question,
            "answer": hits[0]["snippet"] if hits else "I couldn't find a matching PDF hit in the available documents.",
            "items": hits,
            "patient_documents": patient_documents,
            "document_urls": _build_document_url_map(patient_documents or hits),
            "citations": [
                {
                    "document_id": hit["document_id"],
                    "page_number": hit["page_number"],
                    "source_page_url": hit["source_page_url"],
                    "snippet": hit["snippet"],
                    "confidence": hit.get("confidence", 0.0),
                }
                for hit in hits
            ],
            "retrieval": {
                "matched_documents": len({hit["document_id"] for hit in hits}),
                "matched_pages": len(hits),
                "timing": {name: round(value, 3) for name, value in retrieval_timing.items()},
            },
        },
    )


def _serve_rag_answer(event: dict) -> dict:
    params = _query_params(event)
    client_id = params.get("client_id") or params.get("clientId") or ""
    pet_id = params.get("pet_id") or params.get("petId") or ""
    question = params.get("q") or params.get("question") or ""
    if not client_id or not pet_id:
        return _json_response(400, {"error": "client_id and pet_id are required"})
    if not question.strip():
        return _json_response(400, {"error": "question is required"})
    started = time.perf_counter()
    print(f"[RAG_TIMING] answer_start client_id={client_id} pet_id={pet_id} qlen={len(question)}")
    try:
        patient_documents = load_patient_documents(client_id, pet_id or None)
        retrieval_started = time.perf_counter()
        context_chunks, retrieval_timing, retrieval_plan = _execute_planned_retrieval(question, client_id, pet_id)
        retrieval_elapsed = time.perf_counter() - retrieval_started
        print(f"[RAG_TIMING] retrieval_seconds={retrieval_elapsed:.3f} chunks={len(context_chunks)}")
        llm_started = time.perf_counter()
        answer = _call_openai_answer(question, context_chunks)
        llm_elapsed = time.perf_counter() - llm_started
        total_elapsed = time.perf_counter() - started
        print(f"[RAG_TIMING] llm_seconds={llm_elapsed:.3f} total_seconds={total_elapsed:.3f}")
        payload = {
            "answer": answer,
            "context": context_chunks,
            "patient_documents": patient_documents,
            "references": _build_reference_map(patient_documents, context_chunks),
            "citations": _extract_citations(context_chunks),
            "retrieval": {
                "matched_documents": len({hit["document_id"] for hit in context_chunks}),
                "matched_pages": len(context_chunks),
                "plan": retrieval_plan,
            },
            "timing": {
                "retrieval_seconds": round(retrieval_elapsed, 3),
                "llm_seconds": round(llm_elapsed, 3),
                "total_seconds": round(total_elapsed, 3),
                "retrieval_detail": {name: round(value, 3) for name, value in retrieval_timing.items()},
            },
        }
        payload.update({
            "client_id": client_id or None,
            "pet_id": pet_id or None,
            "question": question,
        })
        return _json_response(200, payload)
    except Exception as exc:
        print(
            "[RAG_TIMING] answer_error "
            f"type={type(exc).__name__} message={exc} traceback={traceback.format_exc()}",
            flush=True,
        )
        return _json_response(
            500,
            {
                "error": "rag_answer_failed",
                "error_type": type(exc).__name__,
                "message": str(exc),
                "client_id": client_id or None,
                "pet_id": pet_id or None,
                "question": question,
            },
        )


def _serve_context(event: dict) -> dict:
    started = time.perf_counter()
    params = _query_params(event)
    client_id = params.get("client_id") or params.get("clientId") or ""
    pet_id = params.get("pet_id") or params.get("petId") or ""
    if not client_id or not pet_id:
        elapsed = time.perf_counter() - started
        print(f"[RAG_TIMING] context_seconds={elapsed:.3f} status=400", flush=True)
        return _json_response(400, {"error": "client_id and pet_id are required"})
    documents = load_patient_documents(client_id, pet_id)
    elapsed = time.perf_counter() - started
    print(f"[RAG_TIMING] context_seconds={elapsed:.3f} count={len(documents)}", flush=True)
    return _json_response(
        200,
        {
            "client_id": client_id,
            "pet_id": pet_id,
            "count": len(documents),
            "items": documents,
        },
    )


def _serve_document_page(event: dict) -> dict:
    started = time.perf_counter()
    params = _query_params(event)
    path = _path(event)
    parts = [part for part in path.split("/") if part]
    if len(parts) < 5:
        elapsed = time.perf_counter() - started
        print(f"[RAG_TIMING] document_page_seconds={elapsed:.3f} status=404 path={path}", flush=True)
        return _json_response(404, {"error": "not_found", "path": path})
    document_id = parts[3]
    page_text = parts[5] if len(parts) > 5 else ""
    try:
        page_number = int(params.get("page") or page_text or parts[-1])
    except ValueError:
        page_number = 1
    try:
        target = _resolve_cached_instinct_url(document_id, page_number)
    except Exception as exc:
        elapsed = time.perf_counter() - started
        print(
            "[RAG_TIMING] document_page_seconds="
            f"{elapsed:.3f} status=500 document_id={document_id} page_number={page_number}",
            flush=True,
        )
        return _json_response(500, {"error": "document_url_unavailable", "document_id": document_id, "page_number": page_number, "detail": str(exc)})
    elapsed = time.perf_counter() - started
    print(
        f"[RAG_TIMING] document_page_seconds={elapsed:.3f} status=302 document_id={document_id} page_number={page_number}",
        flush=True,
    )
    return {
        "statusCode": 302,
        "headers": {
            "location": target,
            "cache-control": "no-store",
        },
        "body": "",
    }


def lambda_handler(event: dict, context: object | None = None) -> dict:
    started = time.perf_counter()
    method = _method(event)
    path = _path(event)
    print(f"[RAG_TIMING] request_start method={method} path={path}", flush=True)

    if method == "OPTIONS":
        response = {
            "statusCode": 204,
            "headers": {
                "access-control-allow-origin": "*",
                "access-control-allow-methods": "GET,OPTIONS",
                "access-control-allow-headers": "content-type",
            },
            "body": "",
        }
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status=204 path={path}", flush=True)
        return response

    if path in {"/", "/index.html"}:
        response = _serve_index()
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status={response['statusCode']} path={path}", flush=True)
        return response

    if path == "/api/options":
        response = _serve_options(event)
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status={response['statusCode']} path={path}", flush=True)
        return response

    if path == "/api/version":
        response = _serve_version()
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status={response['statusCode']} path={path}", flush=True)
        return response

    if path == "/api/rag/documents/search":
        response = _serve_rag_search(event)
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status={response['statusCode']} path={path}", flush=True)
        return response

    if path == "/api/rag/answer":
        response = _serve_rag_answer(event)
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status={response['statusCode']} path={path}", flush=True)
        return response

    if path == "/api/rag/context":
        response = _serve_context(event)
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status={response['statusCode']} path={path}", flush=True)
        return response

    if path.startswith("/api/rag/documents/") and "/pages/" in path:
        response = _serve_document_page(event)
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status={response['statusCode']} path={path}", flush=True)
        return response

    if path == "/health":
        response = _json_response(200, {"ok": True})
        print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status=200 path={path}", flush=True)
        return response

    response = _json_response(404, {"error": "not_found", "path": path})
    print(f"[RAG_TIMING] request_seconds={time.perf_counter() - started:.3f} status=404 path={path}", flush=True)
    return response


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
