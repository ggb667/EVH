from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import traceback
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from pathlib import Path
from urllib import request as urllib_request

import boto3

from scripts.rag_ui.catalog import load_catalog, load_patient_documents, query_options_from_postgres, search_pet_chunks_by_embedding

STATIC_DIR = Path(__file__).resolve().parent / "static"
PDF_ICONS_PATH = STATIC_DIR / "PDFIcons.png"
INDEX_PATH = Path(__file__).resolve().parents[2] / "website" / "EVHInstinctPDFRAG" / "index.html"


@dataclass(frozen=True)
class _InstinctUrlCacheEntry:
    url: str
    expires_at: float


_INSTINCT_URL_CACHE: dict[tuple[str, int], _InstinctUrlCacheEntry] = {}
_SELECTED_CONTEXT_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
DEFAULT_PRACTICE_STACK_CONTEXT = (
    "The practice stack uses Instinct EMS and Weave. "
    "General questions about those systems are in-scope, and the assistant may answer how-to or where-to-look questions about the technology itself. "
    "Do not use that general guidance to override patient-specific truth."
)


def _app_version() -> str:
    env_version = os.environ.get("RAG_UI_VERSION", "").strip()
    if env_version:
        return env_version
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


def _instinct_get_json(path: str, params: dict[str, str] | None = None) -> dict | list | str | None:
    query = urlencode({key: value for key, value in (params or {}).items() if str(value or "").strip()})
    url = f"{_instinct_base_url()}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib_request.Request(
        url,
        headers={"Authorization": f"Bearer {_instinct_token()}", "Accept": "application/json"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _instinct_graphql_json(query: str, variables: dict[str, object] | None = None) -> dict:
    payload = {
        "query": query,
        "variables": variables or {},
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
    if not isinstance(data, dict):
        raise RuntimeError("Instinct GraphQL response was not a JSON object.")
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2, sort_keys=True))
    return data


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _selected_catalog_records(client_id: str, pet_id: str) -> tuple[dict[str, object], dict[str, object]]:
    catalog = load_catalog()
    client = catalog.clients_by_id.get(str(client_id or "").strip())
    pet = catalog.pets_by_id.get(str(pet_id or "").strip())
    client_record = {
        "id": getattr(client, "id", "") or str(client_id or ""),
        "name": getattr(client, "label", "") or "",
        "pims_code": getattr(client, "secondary", "") or "",
        "phone_primary": getattr(client, "primary_phone", "") or "",
        "email": getattr(client, "email", "") or "",
    }
    patient_record = {
        "id": getattr(pet, "id", "") or str(pet_id or ""),
        "account_id": getattr(pet, "client_id", "") or str(client_id or ""),
        "name": getattr(pet, "label", "") or "",
        "species": getattr(pet, "species", "") or "",
        "breed": getattr(pet, "breed", "") or "",
        "birthdate": getattr(pet, "birthdate", "") or "",
        "pims_code": getattr(pet, "secondary", "") or "",
        "owner_name": getattr(client, "label", "") or "",
    }
    return client_record, patient_record


def _fetch_instinct_financials(client_record: dict[str, object]) -> dict[str, object]:
    name = _normalize_text(client_record.get("name"))
    pims_code = _normalize_text(client_record.get("pims_code"))
    if not name and not pims_code:
        return {}
    query = """
query getAccountsFinancials($params: ListAccountsParams, $overdueInvoicesOnly: Boolean) {
  accounts(params: $params) {
    id
    pimsCode
    label
    isTestAccount
    numberOfPatients
    accountAlerts { id }
    primaryContact {
      communicationDetails {
        type
        label
        value
        displayValue
        isPreferred
      }
    }
    runningLedger(summary: true, overdueInvoicesOnly: $overdueInvoicesOnly) {
      balance
      unappliedPaymentAmount
      invoicesToReview { id balance }
      agedBalances { current over30 over60 over90 over120 }
    }
  }
}
""".strip()
    variables = {
        "params": {"q": name or pims_code, "includeZeroBalances": False, "perPage": 25},
        "overdueInvoicesOnly": False,
    }
    data = _instinct_graphql_json(query, variables)
    accounts = (((data.get("data") or {}).get("accounts")) or [])
    if not isinstance(accounts, list):
        return {}
    target_id = _normalize_text(client_record.get("id"))
    target_pims = _normalize_text(client_record.get("pims_code"))
    target_name = _normalize_text(client_record.get("name")).lower()
    selected = None
    for account in accounts:
        if not isinstance(account, dict):
            continue
        if target_id and _normalize_text(account.get("id")) == target_id:
            selected = account
            break
        if target_pims and _normalize_text(account.get("pimsCode")) == target_pims:
            selected = account
            break
        label = _normalize_text(account.get("label")).lower()
        if target_name and (label == target_name or target_name in label):
            selected = account
            break
    if selected is None and accounts:
        selected = accounts[0]
    if not isinstance(selected, dict):
        return {}
    running = selected.get("runningLedger") or {}
    return {
        "account_id": _normalize_text(selected.get("id")),
        "pims_code": _normalize_text(selected.get("pimsCode")),
        "label": _normalize_text(selected.get("label")) or _normalize_text(client_record.get("name")),
        "number_of_patients": selected.get("numberOfPatients"),
        "balance": running.get("balance"),
        "unapplied_payment_amount": running.get("unappliedPaymentAmount"),
        "aged_balances": running.get("agedBalances") or {},
        "invoices_to_review": running.get("invoicesToReview") or [],
    }


def _fetch_instinct_reminders(client_record: dict[str, object], patient_record: dict[str, object]) -> list[dict[str, object]]:
    query = _normalize_text(patient_record.get("name")) or _normalize_text(client_record.get("name")) or _normalize_text(client_record.get("pims_code"))
    if not query:
        return []
    try:
        data = _instinct_get_json("/v1/reminders", {"limit": "50", "pageDirection": "after"})
    except Exception:
        return []
    rows: list[dict[str, object]] = []
    if isinstance(data, dict):
        for key in ("reminders", "data", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                rows = [row for row in value if isinstance(row, dict)]
                break
    elif isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict)]
    if not rows:
        return []
    lowered = query.lower()
    filtered: list[dict[str, object]] = []
    for row in rows:
        haystack = " ".join(
            _normalize_text(row.get(key))
            for key in ("title", "name", "label", "patientName", "patient_name", "accountName", "account_name", "description")
        ).lower()
        if lowered and lowered in haystack:
            filtered.append(row)
    if filtered:
        rows = filtered
    reminders: list[dict[str, object]] = []
    for row in rows[:10]:
        reminders.append(
            {
                "id": _normalize_text(row.get("id") or row.get("uuid")),
                "title": _normalize_text(row.get("title") or row.get("name") or row.get("label")),
                "type": _normalize_text(row.get("type") or row.get("reminderType") or row.get("category")),
                "due_date": _normalize_text(row.get("dueAt") or row.get("dueDate") or row.get("due")),
                "status": _normalize_text(row.get("status") or row.get("state") or row.get("reminderStatus")),
            }
        )
    return reminders


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
    if not _verify_instinct_url(url):
        raise RuntimeError(f"Instinct URL did not verify for document_id={key[0]!r} page={key[1]}")
    fragment_url = f"{url}#page={key[1]}"
    _INSTINCT_URL_CACHE[key] = _InstinctUrlCacheEntry(url=fragment_url, expires_at=expires_at)
    return fragment_url


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


def _selected_patient_context_from_event(event: dict) -> dict[str, str]:
    body = _event_json_body(event)
    candidate = {}
    if isinstance(body, dict):
        candidate = body.get("patient_context") or body.get("patient") or {}
    if not isinstance(candidate, dict):
        candidate = {}
    params = _query_params(event)
    merged = dict(candidate)
    for key, fallback_key in (
        ("client_id", "client_id"),
        ("clientId", "clientId"),
        ("client_label", "client_label"),
        ("clientLabel", "clientLabel"),
        ("patient_id", "pet_id"),
        ("patientId", "petId"),
        ("pet_id", "pet_id"),
        ("petId", "petId"),
        ("patient_name", "patient_name"),
        ("name", "name"),
        ("species", "species"),
        ("breed", "breed"),
        ("sex", "sex"),
        ("birthdate", "birthdate"),
        ("owner", "owner"),
        ("owner_name", "owner_name"),
        ("pims_code", "pims_code"),
        ("microchip_id", "microchip_id"),
    ):
        if not merged.get(key):
            value = params.get(fallback_key) or params.get(fallback_key.lower()) or ""
            if value:
                merged[key] = value
    normalized: dict[str, str] = {}
    for key, value in merged.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized[key] = text
    return normalized


def _selected_context_from_event(event: dict) -> dict[str, object]:
    body = _event_json_body(event)
    candidate = {}
    if isinstance(body, dict):
        candidate = body.get("selected_context") or {}
    return candidate if isinstance(candidate, dict) else {}


def _merge_selected_context(
    selected_context: dict[str, object] | None,
    patient_context: dict[str, str] | None,
    patient_documents: list[dict[str, object]] | None,
) -> dict[str, object]:
    selected_context = selected_context or {}
    patient_context = patient_context or {}
    patient_documents = patient_documents or []
    merged = dict(selected_context)
    merged_patient = dict(merged.get("patient") or {})
    for key in ("client_id", "clientId", "patient_id", "patientId", "pet_id", "petId", "patient_name", "name", "species", "breed", "sex", "birthdate", "owner", "owner_name", "pims_code", "microchip_id"):
        value = patient_context.get(key)
        if value and not merged_patient.get(key):
            merged_patient[key] = value
    merged["patient"] = merged_patient or patient_context
    merged.setdefault("client", selected_context.get("client") or {})
    merged.setdefault("financials", selected_context.get("financials") or {})
    merged.setdefault("reminders", selected_context.get("reminders") or [])
    merged_documents = list(merged.get("documents") or [])
    if patient_documents:
        existing_ids = {str(item.get("document_id") or "").strip() for item in merged_documents if isinstance(item, dict)}
        for doc in patient_documents:
            if not isinstance(doc, dict):
                continue
            doc_id = str(doc.get("document_id") or "").strip()
            if doc_id and doc_id in existing_ids:
                continue
            merged_documents.append(
                {
                    "document_id": doc_id,
                    "title": str(doc.get("document_title") or doc.get("title") or "Source PDF"),
                    "type": str(doc.get("type") or doc.get("family") or ""),
                    "source_page_url": str(doc.get("source_page_url") or ""),
                }
            )
    merged["documents"] = merged_documents
    return merged


def _selected_context_cache_key(client_id: str, pet_id: str) -> str:
    return f"{str(client_id or '').strip()}::{str(pet_id or '').strip()}"


def _prune_selected_context_cache(now: float | None = None) -> None:
    now = time.time() if now is None else now
    stale_keys = [key for key, (cached_at, _) in _SELECTED_CONTEXT_CACHE.items() if (now - cached_at) >= 900]
    for key in stale_keys:
        _SELECTED_CONTEXT_CACHE.pop(key, None)
    while len(_SELECTED_CONTEXT_CACHE) > 50:
        oldest_key = min(_SELECTED_CONTEXT_CACHE.items(), key=lambda item: item[1][0])[0]
        _SELECTED_CONTEXT_CACHE.pop(oldest_key, None)


def _selected_context_cache_get(client_id: str, pet_id: str) -> dict[str, object] | None:
    key = _selected_context_cache_key(client_id, pet_id)
    cached = _SELECTED_CONTEXT_CACHE.get(key)
    if not cached:
        return None
    cached_at, payload = cached
    if (time.time() - cached_at) >= 900:
        _SELECTED_CONTEXT_CACHE.pop(key, None)
        return None
    return payload


def _selected_context_cache_set(client_id: str, pet_id: str, payload: dict[str, object]) -> None:
    _SELECTED_CONTEXT_CACHE[_selected_context_cache_key(client_id, pet_id)] = (time.time(), payload)
    _prune_selected_context_cache()


def _conversation_turns_from_event(event: dict) -> list[dict[str, str]]:
    body = _event_json_body(event)
    turns = []
    if isinstance(body, dict):
        turns = body.get("conversation") or body.get("turns") or body.get("history") or []
    if not isinstance(turns, list):
        return []
    normalized: list[dict[str, str]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or turn.get("speaker") or "user").strip().lower()
        if role not in {"user", "assistant", "system"}:
            role = "user"
        content = str(turn.get("content") or turn.get("text") or turn.get("message") or "").strip()
        if not content:
            continue
        evidence_parts = []
        for key in ("answer", "citations", "references"):
            value = turn.get(key)
            if value in (None, "", [], {}):
                continue
            evidence_parts.append(f"{key}: {json.dumps(value, sort_keys=True)}")
        if evidence_parts:
            content = f"{content}\n" + "\n".join(evidence_parts)
        normalized.append({"role": role, "content": content})
    return normalized


def _conversation_citation_refs_from_event(event: dict) -> list[dict[str, str]]:
    body = _event_json_body(event)
    turns = []
    if isinstance(body, dict):
        turns = body.get("conversation") or body.get("turns") or body.get("history") or []
    if not isinstance(turns, list):
        return []
    refs: list[dict[str, str]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        for key in ("citations", "references"):
            values = turn.get(key) or []
            if not isinstance(values, list):
                continue
            for ref in values:
                if not isinstance(ref, dict):
                    continue
                document_id = str(ref.get("document_id") or ref.get("documentId") or "").strip()
                if not document_id:
                    continue
                page_number = int(ref.get("page_number") or ref.get("pageNumber") or ref.get("page") or 1)
                title = str(ref.get("document_title") or ref.get("documentTitle") or ref.get("page_label") or "Source PDF").strip()
                source_uri = str(ref.get("source_uri") or ref.get("sourcePageUrl") or ref.get("source_page_url") or "").strip()
                if not source_uri and isinstance(ref.get("source_page_url"), str):
                    source_uri = str(ref.get("source_page_url") or "").strip()
                refs.append({
                    "document_id": document_id,
                    "page_number": str(page_number),
                    "document_title": title,
                    "source_uri": source_uri,
                })
    return refs


def _event_json_body(event: dict) -> dict | list | None:
    body = event.get("body")
    if body in (None, ""):
        return None
    if isinstance(body, (dict, list)):
        return body
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, (dict, list)) else None
    return None


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


def _build_document_url_map(documents: list[dict], conversation_refs: list[dict] | None = None) -> dict[str, dict]:
    def _canonical_url(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parts = urlsplit(raw)
        if not parts.scheme and not parts.netloc:
            return raw.split("#", 1)[0]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))

    entries: dict[tuple[str, int], dict[str, str]] = {}
    for item in list(documents or []) + list(conversation_refs or []):
        if not isinstance(item, dict):
            continue
        document_id = str(item.get("document_id") or item.get("documentId") or "").strip()
        if not document_id:
            continue
        try:
            page_number = int(item.get("page_number") or item.get("pageNumber") or item.get("page") or 1)
        except (TypeError, ValueError):
            page_number = 1
        key = (document_id, page_number)
        if key in entries:
            continue
        entries[key] = {
            "document_id": document_id,
            "page_number": page_number,
            "document_title": str(item.get("document_title") or item.get("documentTitle") or item.get("page_label") or "Source PDF").strip() or "Source PDF",
            "source_uri": _canonical_url(item.get("source_uri") or item.get("sourcePageUrl") or item.get("source_page_url") or ""),
        }
    return {f"{document_id}:{page_number}": value for (document_id, page_number), value in entries.items()}


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


def _answer_messages(
    question: str,
    context_chunks: list[dict],
    *,
    practice_stack_context: str | None = None,
    patient_context: dict[str, str] | None = None,
    selected_context: dict[str, object] | None = None,
    conversation_turns: list[dict[str, str]] | None = None,
    conversation_refs: list[dict[str, str]] | None = None,
) -> list[dict]:
    patient_context = patient_context or {}
    selected_context = selected_context or {}
    conversation_turns = conversation_turns or []
    conversation_refs = conversation_refs or []
    structured_patient = {
        "patient_name": patient_context.get("patient_name") or patient_context.get("name") or "",
        "species": patient_context.get("species") or "",
        "breed": patient_context.get("breed") or "",
        "sex": patient_context.get("sex") or "",
        "birthdate": patient_context.get("birthdate") or "",
        "owner": patient_context.get("owner_name") or patient_context.get("owner") or patient_context.get("client_label") or "",
        "client_id": patient_context.get("client_id") or patient_context.get("clientId") or "",
        "patient_id": patient_context.get("patient_id") or patient_context.get("patientId") or patient_context.get("pet_id") or patient_context.get("petId") or "",
        "pims_code": patient_context.get("pims_code") or "",
        "microchip_id": patient_context.get("microchip_id") or "",
    }
    patient_text = json.dumps(structured_patient, indent=2, sort_keys=True)
    structured_selected_context = {
        "client": selected_context.get("client") or {},
        "patient": selected_context.get("patient") or structured_patient,
        "financials": selected_context.get("financials") or {},
        "reminders": selected_context.get("reminders") or [],
        "documents": selected_context.get("documents") or [],
    }
    selected_context_text = json.dumps(structured_selected_context, indent=2, sort_keys=True)
    history_text = json.dumps(conversation_turns, indent=2, sort_keys=True)
    evidence_refs = [
        {
            "document_id": str(item.get("document_id") or "").strip(),
            "page_number": int(item.get("page_number") or 1),
            "document_title": str(item.get("document_title") or "Source PDF").strip() or "Source PDF",
            "source_uri": str(item.get("source_page_url") or "").strip(),
        }
        for item in context_chunks
        if str(item.get("document_id") or "").strip()
    ]
    for ref in conversation_refs:
        document_id = str(ref.get("document_id") or "").strip()
        if not document_id:
            continue
        evidence_refs.append(
            {
                "document_id": document_id,
                "page_number": int(ref.get("page_number") or 1),
                "document_title": str(ref.get("document_title") or "Source PDF").strip() or "Source PDF",
                "source_uri": str(ref.get("source_uri") or "").strip(),
            }
        )
    context_text = _summarize_context_chunks(context_chunks)
    practice_stack_context = (practice_stack_context or DEFAULT_PRACTICE_STACK_CONTEXT).strip()
    system_text = (
        "You are a careful patient-record assistant.\n"
        f"{practice_stack_context}\n"
        "Patient facts like species, breed, sex, birthdate, owner, and microchip stay authoritative only from the selected patient record and retrieved chart evidence.\n"
        "Selected patient metadata is authoritative context and may be used even when no retrieved document says the same thing verbatim.\n"
        "Conversation history and its cited evidence are part of the same patient conversation, not independent prompts.\n"
        "Distinguish these evidence levels explicitly when relevant:\n"
        "- explicit structured fact\n"
        "- explicit document fact\n"
        "- strong inference\n"
        "- genuinely unknown\n"
        "You may make reasonable evidence-based inferences from the selected patient metadata and retrieved context.\n"
        "Do not require an exact sentence in a retrieved document before answering.\n"
        "Use the prior conversation turns to resolve follow-up questions in context.\n"
        "Treat follow-up phrases like 'clearly it's a canine' or 'I'm asking if it's a dog or cat' as contextual continuation, not new document-search tasks.\n"
        "Do not invent facts.\n"
        "If the evidence is insufficient, say what is unknown and what would be needed.\n"
        "When useful, mention the source document(s) and page number(s).\n"
        "Keep the answer concise and clinically useful.\n"
        "If multiple documents support the answer, synthesize them clearly.\n"
        "Do not require exact wording from a retrieved document when a reasonable evidence-based inference is supported.\n"
        "When citing a source, emit machine-readable markers like [CITE document_id=\"61173\" page=\"1\"] and do not invent URLs."
    )
    user_text = (
        f"Selected conversation context:\n{selected_context_text}\n\n"
        f"Selected patient metadata:\n{patient_text}\n\n"
        f"Prior conversation turns:\n{history_text}\n\n"
        f"Evidence reference map:\n{json.dumps(evidence_refs, indent=2, sort_keys=True)}\n\n"
        f"Current question:\n{question}\n\n"
        f"Retrieved context:\n{context_text}"
    )
    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]


def _call_openai_answer(
    question: str,
    context_chunks: list[dict],
    *,
    practice_stack_context: str | None = None,
    patient_context: dict[str, str] | None = None,
    selected_context: dict[str, object] | None = None,
    conversation_turns: list[dict[str, str]] | None = None,
    conversation_refs: list[dict[str, str]] | None = None,
) -> str:
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
            timeout=8,
            max_retries=1,
        )
        messages = _answer_messages(
            question,
            context_chunks,
            practice_stack_context=practice_stack_context,
            patient_context=patient_context,
            selected_context=selected_context,
            conversation_turns=conversation_turns,
            conversation_refs=conversation_refs,
        )
        response = model.invoke([
            SystemMessage(content=messages[0]["content"]),
            HumanMessage(content=messages[1]["content"]),
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
    except TimeoutError as exc:
        raise RuntimeError(f"OpenAI request timed out: {exc}") from exc
    except Exception:
        pass

    messages = _answer_messages(
        question,
        context_chunks,
        practice_stack_context=practice_stack_context,
        patient_context=patient_context,
        selected_context=selected_context,
        conversation_turns=conversation_turns,
        conversation_refs=conversation_refs,
    )
    payload = {
        "model": model_name,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": messages[0]["content"]}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": messages[1]["content"]}],
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

def _serve_static_asset(path: str) -> dict:
    if path == "/PDFIcons.png":
        return {
            "statusCode": 200,
            "headers": _headers("image/png"),
            "isBase64Encoded": True,
            "body": base64.b64encode(PDF_ICONS_PATH.read_bytes()).decode("ascii"),
        }
    return _json_response(404, {"error": "not_found", "path": path})


def _serve_version() -> dict:
    return _json_response(
        200,
        {
            "version": _app_version(),
            "lambda_version": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "").strip() or "$LATEST",
        },
    )


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


def _build_selected_context_bundle(client_id: str, pet_id: str, *, patient_context: dict[str, str] | None = None) -> dict[str, object]:
    patient_context = patient_context or {}
    client_record, patient_record = _selected_catalog_records(client_id, pet_id)
    selected_context = {
        "client": client_record,
        "patient": patient_record,
        "financials": _fetch_instinct_financials(client_record),
        "reminders": _fetch_instinct_reminders(client_record, patient_record),
        "documents": load_patient_documents(client_id, pet_id or None),
    }
    return _merge_selected_context(selected_context, patient_context, selected_context.get("documents") or [])


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
        patient_context = _selected_patient_context_from_event(event)
        conversation_turns = _conversation_turns_from_event(event)
        conversation_refs = _conversation_citation_refs_from_event(event)
        selected_context = _selected_context_from_event(event)
        cached_selected_context = _selected_context_cache_get(client_id, pet_id)
        if cached_selected_context is None:
            cached_selected_context = _build_selected_context_bundle(client_id, pet_id, patient_context=patient_context)
            _selected_context_cache_set(client_id, pet_id, cached_selected_context)
        selected_context = _merge_selected_context(cached_selected_context, patient_context, cached_selected_context.get("documents") or [])
        selected_documents = selected_context.get("documents") or []
        retrieval_started = time.perf_counter()
        context_chunks, retrieval_timing, retrieval_plan = _execute_planned_retrieval(question, client_id, pet_id)
        retrieval_elapsed = time.perf_counter() - retrieval_started
        print(f"[RAG_TIMING] retrieval_seconds={retrieval_elapsed:.3f} chunks={len(context_chunks)}")
        llm_started = time.perf_counter()
        answer = _call_openai_answer(
            question,
            context_chunks,
            patient_context=patient_context,
            selected_context=selected_context,
            conversation_turns=conversation_turns,
            conversation_refs=conversation_refs,
        )
        llm_elapsed = time.perf_counter() - llm_started
        total_elapsed = time.perf_counter() - started
        print(f"[RAG_TIMING] llm_seconds={llm_elapsed:.3f} total_seconds={total_elapsed:.3f}")
        citation_map = _build_document_url_map(
            list(selected_documents or []) + list(context_chunks or []),
            conversation_refs,
        )
        payload = {
            "answer": answer,
            "context": context_chunks,
            "patient_documents": selected_documents,
            "references": _build_reference_map(selected_documents, context_chunks),
            "citations": _extract_citations(context_chunks),
            "citation_map": citation_map,
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

    if path == "/PDFIcons.png":
        response = _serve_static_asset(path)
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
