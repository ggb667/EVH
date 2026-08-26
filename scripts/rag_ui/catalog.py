from __future__ import annotations

import json
import heapq
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Any, Iterable


def _normalize(value: Any) -> str:
    text = re.sub(r"[^a-z]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _search_tokens(value: Any) -> list[str]:
    # Keep letters and digits; every other character is a separator.
    return re.findall(r"[A-Z0-9]+", str(value or "").upper())


def _query_tokens(value: Any) -> list[str]:
    return [token for token in _search_tokens(value) if len(token) >= 3]


def _token_fragments(token: str, min_len: int = 3, max_len: int = 7) -> set[str]:
    token = re.sub(r"[^A-Z0-9]+", "", str(token or "").upper())
    fragments: set[str] = set()
    if len(token) < min_len:
        return fragments
    for length in range(min_len, min(7, len(token)) + 1):
        fragments.add(token[:length])
    for length in range(4, min(len(token), max_len) + 1):
        for start in range(0, len(token) - length + 1):
            fragments.add(token[start : start + length])
    return fragments


def _token_fragment_weights(token: str, min_len: int = 3, max_len: int = 7) -> dict[str, int]:
    token = re.sub(r"[^A-Z0-9]+", "", str(token or "").upper())
    fragments: dict[str, int] = {}
    if len(token) < min_len:
        return fragments
    for length in range(min_len, min(7, len(token)) + 1):
        fragment = token[:length]
        fragments[fragment] = max(fragments.get(fragment, 0), length + 1)
    for length in range(4, min(len(token), max_len) + 1):
        for start in range(0, len(token) - length + 1):
            fragment = token[start : start + length]
            fragments[fragment] = max(fragments.get(fragment, 0), length)
    return fragments


def _build_fragment_index(items: Iterable[Any], min_len: int = 3, max_len: int = 7) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for item in items:
        item_id = str(item.id)
        for token in _search_tokens(getattr(item, "search_text", "")):
            for fragment in _token_fragments(token, min_len=min_len, max_len=max_len):
                index.setdefault(fragment, set()).add(item_id)
    return index


def _fragment_scores(query: str, index: dict[str, set[str]], min_len: int = 3, max_len: int = 7) -> dict[str, int]:
    totals: dict[str, int] = {}
    for token in _query_tokens(query):
        per_token: dict[str, int] = {}
        for fragment, fragment_score in _token_fragment_weights(token, min_len=min_len, max_len=max_len).items():
            for item_id in index.get(fragment, ()): 
                score = fragment_score
                if score > per_token.get(item_id, 0):
                    per_token[item_id] = score
        for item_id, score in per_token.items():
            totals[item_id] = totals.get(item_id, 0) + score
    return totals


@lru_cache(maxsize=4096)
def _token_fragment_cache(token: str) -> frozenset[str]:
    return frozenset(_token_fragments(token))


@lru_cache(maxsize=4096)
def _token_prefix_cache(token: str) -> tuple[str, ...]:
    token = re.sub(r"[^A-Z0-9]+", "", str(token or "").upper())
    prefixes: list[str] = []
    if len(token) < 3:
        return tuple(prefixes)
    for length in range(3, min(7, len(token)) + 1):
        prefixes.append(token[:length])
    return tuple(prefixes)


def _item_rank_key(query_tokens: list[str], item: Any, scores: dict[str, int]) -> tuple[Any, ...]:
    search_tokens = _search_tokens(f"{getattr(item, 'label', '')} {getattr(item, 'secondary', '')}")
    token_prefix_evidence = 0
    token_length_score = 0
    for query_token in query_tokens:
        query_fragments = _token_fragment_cache(query_token)
        query_prefixes = _token_prefix_cache(query_token)
        best_prefix = 0
        best_token_length = 0
        for token in search_tokens:
            token_fragments = _token_fragment_cache(token)
            if query_fragments.isdisjoint(token_fragments):
                continue
            best_token_length = max(best_token_length, len(token))
            for prefix in query_prefixes:
                if prefix in token_fragments:
                    best_prefix = max(best_prefix, len(prefix) + 1)
        token_prefix_evidence += best_prefix
        token_length_score += best_token_length
    return (
        scores.get(str(item.id), 0),
        token_prefix_evidence,
        token_length_score,
        len(str(item.label)),
        str(item.label).upper()[::-1],
        str(item.secondary).upper()[::-1],
        str(item.id),
    )


def _rank_items(query: str, items_by_id: dict[str, Any], scores: dict[str, int], limit: int = 10) -> list[Any]:
    query_tokens = _query_tokens(query)
    scored_items = [items_by_id[item_id] for item_id in scores if item_id in items_by_id]
    return heapq.nlargest(limit, scored_items, key=lambda item: _item_rank_key(query_tokens, item, scores))


def _join_non_empty(parts: Iterable[Any]) -> str:
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def _path_exists(path: str) -> bool:
    return bool(path) and Path(path).expanduser().exists()


def resolve_data_path(explicit_path: str | None = None) -> Path:
    default_paths = (
        os.environ.get("RAG_UI_DB_PATH", "").strip(),
        os.environ.get("RAG_UI_DATA_PATH", "").strip(),
        "/home/ggb66/dev/EVH/exports/instinct_identity.sqlite",
        "/home/ggb66/dev/EVH/exports/instinct_identity.db",
        "/home/ggb66/dev/EVH/scripts/instinct_bulk_cache.json",
    )

    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if candidate.exists():
            return candidate

    for raw_path in default_paths:
        if _path_exists(raw_path):
            return Path(raw_path)

    raise FileNotFoundError(
        "Could not find a RAG UI data source. Set RAG_UI_DATA_PATH or place "
        "instinct_bulk_cache.json alongside the repo."
    )


def _refresh_interval_seconds() -> float:
    raw = os.environ.get("RAG_UI_REFRESH_SECONDS", "900").strip()
    try:
        value = float(raw)
    except ValueError:
        return 300.0
    return max(5.0, value)


def _context_ttl_seconds() -> float:
    raw = os.environ.get("RAG_UI_CONTEXT_TTL_SECONDS", "900").strip()
    try:
        value = float(raw)
    except ValueError:
        return 900.0
    return max(30.0, value)


def _pg_env() -> dict[str, str] | None:
    required = ("EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD")
    if not all(os.environ.get(name, "").strip() for name in required):
        return None
    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ["EVH_PGPASSWORD"]
    return env


def _pg_connect():
    env = _pg_env()
    if env is None:
        return None
    try:
        import pg8000.dbapi as pg  # type: ignore

        return pg.connect(
            host=env["EVH_PGHOST"],
            port=int(env["EVH_PGPORT"]),
            database=env["EVH_PGDATABASE"],
            user=env["EVH_PGUSER"],
            password=env["EVH_PGPASSWORD"],
            timeout=10,
        )
    except Exception:
        import psycopg

        return psycopg.connect(
            host=env["EVH_PGHOST"],
            port=int(env["EVH_PGPORT"]),
            dbname=env["EVH_PGDATABASE"],
            user=env["EVH_PGUSER"],
            password=env["EVH_PGPASSWORD"],
            connect_timeout=10,
        )


def _openai_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key
    secret_arn = os.environ.get("OPENAI_API_KEY_SECRET_ARN", "").strip()
    if not secret_arn:
        raise RuntimeError("OPENAI_API_KEY_SECRET_ARN is required for embeddings generation.")
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret = str(response.get("SecretString") or "").strip()
    if not secret:
        raise RuntimeError("Secrets Manager returned an empty OpenAI API key.")
    return secret


def _embed_text_openai(text: str) -> list[float]:
    import urllib.request as urllib_request

    payload = {
        "model": os.environ.get("RAG_UI_EMBEDDING_MODEL", "text-embedding-3-small"),
        "input": text,
    }
    request = urllib_request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    vector = (((data.get("data") or [{}])[0]).get("embedding")) or []
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("OpenAI embeddings response did not include an embedding vector.")
    return [float(v) for v in vector]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


@dataclass(frozen=True)
class ClientOption:
    id: str
    label: str
    secondary: str
    pet_count: int
    search_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "secondary": self.secondary,
            "petCount": self.pet_count,
        }


@dataclass(frozen=True)
class PetOption:
    id: str
    label: str
    secondary: str
    client_id: str
    client_label: str
    species: str
    breed: str
    birthdate: str
    alert_count: int
    microchip_id: str
    search_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "secondary": self.secondary,
            "clientId": self.client_id,
            "clientLabel": self.client_label,
            "species": self.species,
            "breed": self.breed,
            "birthdate": self.birthdate,
            "alertCount": self.alert_count,
            "microchipId": self.microchip_id or None,
        }


@dataclass(frozen=True)
class RagCatalog:
    clients: list[ClientOption]
    pets_by_client: dict[str, list[PetOption]]
    clients_by_id: dict[str, ClientOption]
    pets_by_id: dict[str, PetOption]

    @cached_property
    def client_fragment_index(self) -> dict[str, set[str]]:
        return _build_fragment_index(self.clients)

    @cached_property
    def pet_fragment_indexes(self) -> dict[str, dict[str, set[str]]]:
        return {client_id: _build_fragment_index(pets) for client_id, pets in self.pets_by_client.items()}

    def search_clients(self, query: str) -> list[dict[str, Any]]:
        tokens = _search_tokens(query)
        if not tokens or max(map(len, tokens)) < 3:
            return [item.as_dict() for item in self.clients]
        scores = _fragment_scores(query, self.client_fragment_index)
        if not scores:
            return [item.as_dict() for item in self.clients]
        ranked = _rank_items(query, self.clients_by_id, scores)
        return [item.as_dict() for item in ranked]

    def search_pets(self, client_id: str | None, query: str) -> list[dict[str, Any]]:
        if not client_id or client_id not in self.pets_by_client:
            return []
        source = self.pets_by_client[client_id]
        tokens = _search_tokens(query)
        if not tokens or max(map(len, tokens)) < 3:
            return [item.as_dict() for item in source]
        scores = _fragment_scores(query, self.pet_fragment_indexes.get(client_id, {}))
        if not scores:
            return [item.as_dict() for item in source]
        ranked = _rank_items(query, self.pets_by_id, scores)
        return [item.as_dict() for item in ranked]


@dataclass(frozen=True)
class RagHit:
    document_id: str
    document_title: str
    page_number: int
    page_label: str
    source_page_url: str
    snippet: str
    confidence: float
    date: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "page_number": self.page_number,
            "page_label": self.page_label,
            "source_page_url": self.source_page_url,
            "snippet": self.snippet,
            "confidence": self.confidence,
            "date": self.date,
        }


@dataclass(frozen=True)
class RagContextChunk:
    document_id: str
    document_title: str
    page_number: int
    page_label: str
    source_page_url: str
    chunk_text: str
    source_name: str
    confidence: float
    date: str

    def as_hit(self) -> dict[str, Any]:
        return RagHit(
            document_id=self.document_id,
            document_title=self.document_title,
            page_number=self.page_number,
            page_label=self.page_label,
            source_page_url=self.source_page_url,
            snippet=self.chunk_text[:280],
            confidence=self.confidence,
            date=self.date,
        ).as_dict()


def _build_catalog(clients: list[dict[str, Any]], patients: list[dict[str, Any]]) -> RagCatalog:
    client_options = [
        ClientOption(
            id=str(item["id"]),
            label=str(item["label"]),
            secondary=str(item["secondary"]),
            pet_count=sum(1 for patient in patients if patient["client_id"] == str(item["id"])),
            search_text=str(item["search_text"]),
        )
        for item in clients
    ]
    patient_options = [
        PetOption(
            id=str(item["id"]),
            label=str(item["label"]),
            secondary=str(item["secondary"]),
            client_id=str(item["client_id"]),
            client_label=next((client["label"] for client in clients if client["id"] == item["client_id"]), ""),
            species=str(item["species"]),
            breed=str(item["breed"]),
            birthdate=str(item["birthdate"]),
            alert_count=int(item["alert_count"]),
            microchip_id=str(item["microchip_id"]),
            search_text=str(item["search_text"]),
        )
        for item in patients
    ]
    return RagCatalog(
        clients=client_options,
        pets_by_client={
            client_id: [pet for pet in patient_options if pet.client_id == client_id]
            for client_id in {pet.client_id for pet in patient_options}
        },
        clients_by_id={item.id: item for item in client_options},
        pets_by_id={item.id: item for item in patient_options},
    )


def load_patient_documents(client_id: str, pet_id: str | None = None) -> list[dict[str, Any]]:
    started = time.perf_counter()
    client_id = str(client_id or "").strip()
    pet_id = str(pet_id or "").strip() or None
    if not client_id or not pet_id:
        print("[RAG_TIMING] patient_documents_seconds=0.000 status=400 docs=0", flush=True)
        return []

    connection_started = time.perf_counter()
    connection = _pg_connect()
    connect_seconds = time.perf_counter() - connection_started
    if connection is None:
        print(
            f"[RAG_TIMING] patient_documents_connect_seconds={connect_seconds:.3f} "
            f"patient_documents_execute_seconds=0.000 patient_documents_fetch_seconds=0.000 "
            f"patient_documents_materialize_seconds=0.000 total_seconds={time.perf_counter() - started:.3f} docs=0",
            flush=True,
        )
        return []

    cursor = connection.cursor()
    query_sql = """
        select
          coalesce(document_pdf_id::text, metadata->>'source_reference_id', metadata->>'pdf_id', source_name) as document_id,
          coalesce(nullif(metadata->>'original_filename', ''), nullif(metadata->>'originalfilename', ''), source_name) as document_title,
          min(coalesce(page_number, 1)) as page_number,
          'Page ' || min(coalesce(page_number, 1))::text as page_label,
          count(*) as chunk_count
        from public.pms_page_chunk
        where client_instinct_uuid = %s
          and patient_id = %s
          and chunk_text is not null
        group by 1, 2
        order by min(coalesce(created_at, now())) asc, min(coalesce(page_number, 1)) asc, 1 asc
    """
    try:
        execute_started = time.perf_counter()
        cursor.execute(query_sql, (client_id, pet_id))
        execute_seconds = time.perf_counter() - execute_started
        fetch_started = time.perf_counter()
        rows = cursor.fetchall()
        fetch_seconds = time.perf_counter() - fetch_started
    finally:
        cursor.close()
        connection.close()

    materialize_started = time.perf_counter()
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        document_id, document_title, page_number, page_label, _chunk_count = row
        document_id = str(document_id or "").strip()
        if not document_id or document_id in seen:
            continue
        seen.add(document_id)
        documents.append(
            {
                "document_id": document_id,
                "document_title": str(document_title or "Source PDF"),
                "source_uri": "",
                "page_number": int(page_number or 1),
                "page_label": str(page_label or f"Page {page_number or 1}"),
                "source_page_url": "",
            }
        )
    materialize_seconds = time.perf_counter() - materialize_started
    total_seconds = time.perf_counter() - started
    print(
        "[RAG_TIMING] patient_documents_connect_seconds="
        f"{connect_seconds:.3f} patient_documents_execute_seconds={execute_seconds:.3f} "
        f"patient_documents_fetch_seconds={fetch_seconds:.3f} "
        f"patient_documents_materialize_seconds={materialize_seconds:.3f} "
        f"total_seconds={total_seconds:.3f} docs={len(documents)}",
        flush=True,
    )
    return documents


def search_pet_chunks_by_embedding(client_id: str, pet_id: str | None, question: str) -> tuple[list[dict[str, Any]], dict[str, float]]:
    started = time.perf_counter()
    client_id = str(client_id or "").strip()
    pet_id = str(pet_id or "").strip() or None
    if not client_id:
        return [], {"total_seconds": 0.0}

    connection = _pg_connect()
    if connection is None:
        return [], {"total_seconds": round(time.perf_counter() - started, 3)}

    cursor = connection.cursor()
    try:
        question_text = str(question or "").strip()
        embedding = _embed_text_openai(question_text) if question_text else []
        if not embedding:
            return [], {"total_seconds": round(time.perf_counter() - started, 3)}
        vector = _vector_literal(embedding)
        query_sql = """
            select
              coalesce(document_pdf_id::text, metadata->>'source_reference_id', metadata->>'pdf_id', source_name) as document_id,
              coalesce(nullif(metadata->>'original_filename', ''), nullif(metadata->>'originalfilename', ''), source_name) as document_title,
              coalesce(page_number, 1) as page_number,
              'Page ' || coalesce(page_number, 1)::text as page_label,
              coalesce(source_uri, '') as source_page_url,
              left(coalesce(chunk_text, ''), 1200) as chunk_text,
              coalesce(created_at::text, '') as date,
              (embedding <=> %s::vector) as distance
            from public.pms_page_chunk
            where client_instinct_uuid = %s
              and patient_id = %s
              and chunk_text is not null
              and embedding is not null
            order by embedding <=> %s::vector, page_number asc, chunk_index asc
            limit 25
        """
        cursor.execute(query_sql, (vector, client_id, pet_id or "", vector))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    chunks: list[dict[str, Any]] = []
    for row in rows:
        document_id, document_title, page_number, page_label, source_page_url, chunk_text, date, distance = row
        similarity = max(0.0, 1.0 - float(distance or 0.0))
        chunks.append(
            {
                "document_id": str(document_id or ""),
                "document_title": str(document_title or "Source PDF"),
                "page_number": int(page_number or 1),
                "page_label": str(page_label or f"Page {page_number or 1}"),
                "source_page_url": str(source_page_url or ""),
                "snippet": str(chunk_text or ""),
                "confidence": similarity,
                "date": str(date or ""),
            }
        )

    elapsed = round(time.perf_counter() - started, 3)
    return chunks, {"total_seconds": elapsed}


@lru_cache(maxsize=64)
def _postgres_client_options() -> tuple[ClientOption, ...]:
    started = time.perf_counter()
    connection = _pg_connect()
    connect_seconds = time.perf_counter() - started
    print(f"[RAG_TIMING] pg_connect_seconds={connect_seconds:.3f} kind=client", flush=True)
    if connection is None:
        return ()
    cursor = connection.cursor()
    try:
        execute_started = time.perf_counter()
        cursor.execute(
            """
            select
              account_id as id,
              coalesce(nullif(owner_name, ''), nullif(pims_code, ''), account_id) as label,
              coalesce(nullif(pims_code, ''), account_id) as secondary
            from public.instinct_owner_lookup_norm
            """
        )
        execute_seconds = time.perf_counter() - execute_started
        print(f"[RAG_TIMING] query_execute_seconds={execute_seconds:.3f} kind=client", flush=True)
        fetch_started = time.perf_counter()
        rows = cursor.fetchall()
        fetch_seconds = time.perf_counter() - fetch_started
        print(f"[RAG_TIMING] fetch_seconds={fetch_seconds:.3f} kind=client count={len(rows)}", flush=True)
        return tuple(
            ClientOption(
                id=str(row[0] or "").strip(),
                label=str(row[1] or "").strip(),
                secondary=str(row[2] or "").strip(),
                pet_count=0,
                search_text=_normalize(" ".join([str(row[1] or "").strip(), str(row[2] or "").strip(), str(row[0] or "").strip()])),
            )
            for row in rows
            if str(row[0] or "").strip()
        )
    finally:
        cursor.close()
        connection.close()


@lru_cache(maxsize=1)
def _postgres_client_fragment_index() -> dict[str, set[str]]:
    started = time.perf_counter()
    index = _build_fragment_index(_postgres_client_options())
    build_seconds = time.perf_counter() - started
    print(f"[RAG_TIMING] fragment_index_build_seconds={build_seconds:.3f} kind=client fragment_count={len(index)}", flush=True)
    return index


@lru_cache(maxsize=256)
def _postgres_pet_options(client_id: str) -> tuple[PetOption, ...]:
    client_id = str(client_id or "").strip()
    if not client_id:
        return ()
    started = time.perf_counter()
    connection = _pg_connect()
    connect_seconds = time.perf_counter() - started
    print(f"[RAG_TIMING] pg_connect_seconds={connect_seconds:.3f} kind=pet client_id={client_id}", flush=True)
    if connection is None:
        return ()
    cursor = connection.cursor()
    try:
        execute_started = time.perf_counter()
        cursor.execute(
            """
            select
              patient_id::text as id,
              coalesce(nullif(patient_name, ''), nullif(patient_pims_code, ''), patient_id::text) as label,
              coalesce(nullif(patient_pims_code, ''), patient_id::text) as secondary,
              coalesce(nullif(species, ''), '') as species,
              coalesce(nullif(breed, ''), '') as breed,
              coalesce(owner_name, '') as owner_name
            from public.instinct_patient_lookup
            where account_id = %s
            """,
            [client_id],
        )
        execute_seconds = time.perf_counter() - execute_started
        print(f"[RAG_TIMING] query_execute_seconds={execute_seconds:.3f} kind=pet client_id={client_id}", flush=True)
        fetch_started = time.perf_counter()
        rows = cursor.fetchall()
        fetch_seconds = time.perf_counter() - fetch_started
        print(f"[RAG_TIMING] fetch_seconds={fetch_seconds:.3f} kind=pet client_id={client_id} count={len(rows)}", flush=True)
        return tuple(
            PetOption(
                id=str(row[0] or "").strip(),
                label=str(row[1] or "").strip(),
                secondary=str(row[2] or "").strip(),
                client_id=client_id,
                client_label=str(row[5] or "").strip(),
                species=str(row[3] or "").strip(),
                breed=str(row[4] or "").strip(),
                birthdate="",
                alert_count=0,
                microchip_id="",
                search_text=" ".join([
                    str(row[1] or "").strip(),
                    str(row[2] or "").strip(),
                    str(row[3] or "").strip(),
                    str(row[4] or "").strip(),
                    str(row[5] or "").strip(),
                    str(row[0] or "").strip(),
                ]),
            )
            for row in rows
            if str(row[0] or "").strip()
        )
    finally:
        cursor.close()
        connection.close()


@lru_cache(maxsize=256)
def _postgres_pet_fragment_index(client_id: str) -> dict[str, set[str]]:
    started = time.perf_counter()
    index = _build_fragment_index(_postgres_pet_options(client_id))
    build_seconds = time.perf_counter() - started
    print(f"[RAG_TIMING] fragment_index_build_seconds={build_seconds:.3f} kind=pet client_id={client_id} fragment_count={len(index)}", flush=True)
    return index


def _initialize_client_search() -> tuple[tuple[ClientOption, ...], dict[str, ClientOption], dict[str, set[str]]]:
    started = time.perf_counter()
    clients = _postgres_client_options()
    client_by_id = {item.id: item for item in clients}
    fragment_index = _build_fragment_index(clients)
    build_seconds = time.perf_counter() - started
    print(
        f"[RAG_TIMING] client_search_init_seconds={build_seconds:.3f} "
        f"client_count={len(clients)} fragment_count={len(fragment_index)}",
        flush=True,
    )
    return clients, client_by_id, fragment_index


if all(os.environ.get(name, "").strip() for name in ("EVH_PGHOST", "EVH_PGPORT", "EVH_PGDATABASE", "EVH_PGUSER", "EVH_PGPASSWORD")):
    CLIENTS, CLIENT_BY_ID, CLIENT_FRAGMENT_INDEX = _initialize_client_search()
else:
    CLIENTS = ()
    CLIENT_BY_ID = {}
    CLIENT_FRAGMENT_INDEX = {}


def query_options_from_postgres(kind: str, query: str, client_id: str | None = None) -> list[dict[str, Any]]:
    kind = str(kind or "client").strip().lower()
    query_text = str(query or "").strip()
    total_started = time.perf_counter()

    if kind == "pet":
        client_id = str(client_id or "").strip()
        if not client_id:
            return []
        pets = _postgres_pet_options(client_id)
        if not query_text:
            print(f"[RAG_TIMING] ranking_seconds=0.000 kind=pet client_id={client_id} query={query_text!r}", flush=True)
            print(f"[RAG_TIMING] total_options_seconds={time.perf_counter() - total_started:.3f} kind=pet client_id={client_id} count={len(pets[:10])}", flush=True)
            return [item.as_dict() for item in pets[:10]]
        ranking_started = time.perf_counter()
        index = _postgres_pet_fragment_index(client_id)
        print(f"[RAG_TIMING] fragment_count={len(index)} kind=pet client_id={client_id}", flush=True)
        scores = _fragment_scores(query_text, index)
        print(f"[RAG_TIMING] candidate_count={len(scores)} kind=pet client_id={client_id}", flush=True)
        if not scores:
            ranking_seconds = time.perf_counter() - ranking_started
            print(f"[RAG_TIMING] fragment_scores_seconds={ranking_seconds:.3f} kind=pet client_id={client_id}", flush=True)
            print(f"[RAG_TIMING] candidate_lookup_seconds=0.000 kind=pet client_id={client_id}", flush=True)
            print(f"[RAG_TIMING] top10_seconds=0.000 kind=pet client_id={client_id}", flush=True)
            print(f"[RAG_TIMING] ranking_seconds={ranking_seconds:.3f} kind=pet client_id={client_id} query={query_text!r}", flush=True)
            print(f"[RAG_TIMING] total_options_seconds={time.perf_counter() - total_started:.3f} kind=pet client_id={client_id} count={len(pets[:10])}", flush=True)
            return [item.as_dict() for item in pets[:10]]
        pet_map = {item.id: item for item in pets}
        lookup_started = time.perf_counter()
        ranked = _rank_items(query_text, pet_map, scores)
        candidate_lookup_seconds = time.perf_counter() - lookup_started
        top10_started = time.perf_counter()
        results = [item.as_dict() for item in ranked]
        top10_seconds = time.perf_counter() - top10_started
        ranking_seconds = time.perf_counter() - ranking_started
        fragment_scores_seconds = ranking_seconds - candidate_lookup_seconds - top10_seconds
        print(f"[RAG_TIMING] fragment_scores_seconds={fragment_scores_seconds:.3f} kind=pet client_id={client_id}", flush=True)
        print(f"[RAG_TIMING] candidate_lookup_seconds={candidate_lookup_seconds:.3f} kind=pet client_id={client_id}", flush=True)
        print(f"[RAG_TIMING] top10_seconds={top10_seconds:.3f} kind=pet client_id={client_id}", flush=True)
        print(f"[RAG_TIMING] ranking_seconds={ranking_seconds:.3f} kind=pet client_id={client_id} query={query_text!r}", flush=True)
        print(f"[RAG_TIMING] total_options_seconds={time.perf_counter() - total_started:.3f} kind=pet client_id={client_id} count={len(results or pets[:10])}", flush=True)
        return results or [item.as_dict() for item in pets[:10]]

    clients = _postgres_client_options()
    if not query_text:
        print(f"[RAG_TIMING] ranking_seconds=0.000 kind=client query={query_text!r}", flush=True)
        print(f"[RAG_TIMING] total_options_seconds={time.perf_counter() - total_started:.3f} kind=client count={len(clients[:10])}", flush=True)
        return [item.as_dict() for item in clients[:10]]
    ranking_started = time.perf_counter()
    index = CLIENT_FRAGMENT_INDEX or _postgres_client_fragment_index()
    print(f"[RAG_TIMING] fragment_count={len(index)} kind=client", flush=True)
    scores = _fragment_scores(query_text, index)
    print(f"[RAG_TIMING] candidate_count={len(scores)} kind=client", flush=True)
    if not scores:
        ranking_seconds = time.perf_counter() - ranking_started
        print(f"[RAG_TIMING] fragment_scores_seconds={ranking_seconds:.3f} kind=client", flush=True)
        print(f"[RAG_TIMING] candidate_lookup_seconds=0.000 kind=client", flush=True)
        print(f"[RAG_TIMING] top10_seconds=0.000 kind=client", flush=True)
        print(f"[RAG_TIMING] ranking_seconds={ranking_seconds:.3f} kind=client query={query_text!r}", flush=True)
        print(f"[RAG_TIMING] total_options_seconds={time.perf_counter() - total_started:.3f} kind=client count={len(clients[:10])}", flush=True)
        return [item.as_dict() for item in clients[:10]]
    lookup_started = time.perf_counter()
    ranked = _rank_items(query_text, CLIENT_BY_ID or {item.id: item for item in clients}, scores)
    candidate_lookup_seconds = time.perf_counter() - lookup_started
    top10_started = time.perf_counter()
    results = [item.as_dict() for item in ranked]
    top10_seconds = time.perf_counter() - top10_started
    ranking_seconds = time.perf_counter() - ranking_started
    fragment_scores_seconds = ranking_seconds - candidate_lookup_seconds - top10_seconds
    print(f"[RAG_TIMING] fragment_scores_seconds={fragment_scores_seconds:.3f} kind=client", flush=True)
    print(f"[RAG_TIMING] candidate_lookup_seconds={candidate_lookup_seconds:.3f} kind=client", flush=True)
    print(f"[RAG_TIMING] top10_seconds={top10_seconds:.3f} kind=client", flush=True)
    print(f"[RAG_TIMING] ranking_seconds={ranking_seconds:.3f} kind=client query={query_text!r}", flush=True)
    print(f"[RAG_TIMING] total_options_seconds={time.perf_counter() - total_started:.3f} kind=client count={len(results or clients[:10])}", flush=True)
    return results or [item.as_dict() for item in clients[:10]]

def _client_display_name(account: dict[str, Any]) -> str:
    contact = account.get("primaryContact") or {}
    first = contact.get("nameFirst") or ""
    middle = contact.get("nameMiddle") or ""
    last = contact.get("nameLast") or ""
    full_name = _join_non_empty([first, middle, last]).strip()
    label = account.get("label") or ""
    return full_name or label or account.get("pimsCode") or account.get("id") or "Unnamed client"


def _client_secondary(account: dict[str, Any]) -> str:
    parts = [
        account.get("pimsCode"),
        account.get("pimsId"),
        account.get("id"),
    ]
    return _join_non_empty(parts)


def _pet_display_name(patient: dict[str, Any]) -> str:
    return (
        patient.get("name")
        or patient.get("pimsCode")
        or f"Patient {patient.get('id')}"
        or "Unnamed pet"
    )


def _pet_secondary(patient: dict[str, Any]) -> str:
    species = (patient.get("species") or {}).get("label") or ""
    breed = (patient.get("breed") or {}).get("label") or ""
    pims_code = patient.get("pimsCode") or ""
    parts = [species, breed, pims_code]
    return " | ".join(part for part in parts if part)


def _load_catalog_from_sqlite(db_path: Path) -> RagCatalog:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        account_rows = connection.execute(
            """
            SELECT
                id,
                pims_code,
                pims_id,
                owner_first_name,
                owner_last_name,
                display_name
            FROM instinct_accounts
            WHERE is_deleted = 0
            """
        ).fetchall()
        patient_rows = connection.execute(
            """
            SELECT
                id,
                account_id,
                pims_code,
                name,
                birthdate,
                breed,
                deleted_at,
                alerts,
                raw_payload
            FROM instinct_patients
            WHERE deleted_at IS NULL OR deleted_at = ''
            """
        ).fetchall()
    finally:
        connection.close()

    clients: list[dict[str, Any]] = []
    for row in account_rows:
        client_id = str(row["id"] or "").strip()
        if not client_id:
            continue
        label = str(row["display_name"] or "").strip() or str(row["owner_first_name"] or "").strip() or str(row["pims_code"] or "").strip() or client_id
        secondary = " ".join(part for part in (str(row["pims_code"] or "").strip(), str(row["pims_id"] or "").strip(), client_id) if part)
        search_text = _normalize(" ".join([label, secondary, str(row["owner_first_name"] or ""), str(row["owner_last_name"] or "")]))
        clients.append({"id": client_id, "label": label, "secondary": secondary, "search_text": search_text})

    patients: list[dict[str, Any]] = []
    for row in patient_rows:
        client_id = str(row["account_id"] or "").strip()
        if not client_id:
            continue
        pet_id = str(row["id"] or "").strip()
        if not pet_id:
            continue
        name = str(row["name"] or "").strip() or str(row["pims_code"] or "").strip() or pet_id
        breed = str(row["breed"] or "").strip()
        birthdate = str(row["birthdate"] or "").strip()
        alerts_value = row["alerts"] or "[]"
        try:
            alerts = json.loads(alerts_value) if isinstance(alerts_value, str) else list(alerts_value)
        except json.JSONDecodeError:
            alerts = []
        species = ""
        raw_payload = row["raw_payload"] or "{}"
        try:
            raw = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload)
            species = (raw.get("species") or {}).get("label") or ""
        except Exception:
            pass
        secondary = _pet_secondary({"species": {"label": species} if species else {}, "breed": {"label": breed} if breed else {}, "pimsCode": row["pims_code"] or ""})
        search_text = _normalize(" ".join([name, secondary, client_id, str(row["pims_code"] or ""), pet_id]))
        patients.append({"id": pet_id, "label": name, "secondary": secondary, "client_id": client_id, "species": species, "breed": breed, "birthdate": birthdate, "alert_count": len(alerts), "microchip_id": str(row["microchipId"] or "").strip() if "microchipId" in row.keys() else "", "search_text": search_text})

    return _build_catalog(clients, patients)


def load_catalog_from_file(data_path: str) -> RagCatalog:
    path = Path(data_path)
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return _load_catalog_from_sqlite(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    clients: list[dict[str, Any]] = []
    for account in payload.get("accounts", []):
        if not isinstance(account, dict) or account.get("deletedAt") is not None:
            continue
        client_id = str(account.get("id") or "").strip()
        if not client_id:
            continue
        label = _client_display_name(account)
        secondary = _client_secondary(account)
        search_text = _normalize(" ".join([label, secondary, account.get("note") or ""]))
        clients.append({"id": client_id, "label": label, "secondary": secondary, "search_text": search_text})

    patients: list[dict[str, Any]] = []
    for patient in payload.get("patients", []):
        if not isinstance(patient, dict) or patient.get("deletedAt") is not None:
            continue
        client_id = str(patient.get("accountId") or "").strip()
        if not client_id:
            continue
        pet_id = str(patient.get("id") or "").strip()
        if not pet_id:
            continue
        species = (patient.get("species") or {}).get("label") or ""
        breed = (patient.get("breed") or {}).get("label") or ""
        birthdate = str(patient.get("birthdate") or "").strip()
        alert_count = len(patient.get("alerts") or [])
        microchip_id = str(patient.get("microchipId") or "").strip()
        label = _pet_display_name(patient)
        secondary = _pet_secondary(patient)
        search_text = _normalize(" ".join([label, secondary, client_id, patient.get("pimsCode") or "", str(patient.get("id") or "")]))
        patients.append({"id": pet_id, "label": label, "secondary": secondary, "client_id": client_id, "species": species, "breed": breed, "birthdate": birthdate, "alert_count": alert_count, "microchip_id": microchip_id, "search_text": search_text})

    return _build_catalog(clients, patients)


def _load_catalog_from_postgres() -> RagCatalog:
    connection = _pg_connect()
    if connection is None:
        raise FileNotFoundError("Postgres env vars are missing")
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            select
              account_id,
              coalesce(nullif(owner_name, ''), nullif(pims_code, ''), account_id) as label,
              coalesce(nullif(pims_code, ''), account_id) as secondary,
              coalesce(owner_name, '') as owner_name
            from public.instinct_owner_lookup_norm
            """
        )
        owner_rows = cursor.fetchall()
        cursor.execute(
            """
            select
              patient_id::text,
              account_id,
              coalesce(nullif(patient_name, ''), nullif(patient_pims_code, ''), patient_id::text) as label,
              coalesce(nullif(species, ''), '') as species,
              coalesce(nullif(breed, ''), '') as breed,
              coalesce(nullif(patient_pims_code, ''), patient_id::text) as pims_code,
              coalesce(owner_name, '') as owner_name
            from public.instinct_patient_lookup
            where account_id is not null and account_id <> ''
            """
        )
        patient_rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    clients: list[dict[str, Any]] = []
    for account_id, label, secondary, owner_name in owner_rows:
        client_id = str(account_id or "").strip()
        if not client_id:
            continue
        label = str(label or "").strip() or client_id
        secondary = str(secondary or "").strip()
        search_text = _normalize(" ".join([label, secondary, owner_name]))
        clients.append({"id": client_id, "label": label, "secondary": secondary, "search_text": search_text})

    patients: list[dict[str, Any]] = []
    for patient_id, account_id, label, species, breed, pims_code, owner_name in patient_rows:
        client_id = str(account_id or "").strip()
        if not client_id:
            continue
        pet_id = str(patient_id or "").strip()
        if not pet_id:
            continue
        label = str(label or "").strip() or pet_id
        species = str(species or "").strip()
        breed = str(breed or "").strip()
        pims_code = str(pims_code or "").strip()
        secondary = _pet_secondary({"species": {"label": species} if species else {}, "breed": {"label": breed} if breed else {}, "pimsCode": pims_code})
        search_text = _normalize(" ".join([label, secondary, client_id, pims_code, pet_id, owner_name]))
        patients.append({"id": pet_id, "label": label, "secondary": secondary, "client_id": client_id, "species": species, "breed": breed, "birthdate": "", "alert_count": 0, "microchip_id": "", "search_text": search_text})

    return _build_catalog(clients, patients)


_CATALOG_CACHE: dict[str, tuple[float, float, RagCatalog]] = {}
_CATALOG_MEMORY: tuple[float, RagCatalog] | None = None


def _load_cached_file_catalog(path: Path, force: bool = False) -> RagCatalog:
    key = str(path)
    now = time.time()
    mtime = path.stat().st_mtime if path.exists() else 0.0
    cached = _CATALOG_CACHE.get(key)

    if not force and cached and cached[0] == mtime and now - cached[1] < _refresh_interval_seconds():
        return cached[2]

    catalog = load_catalog_from_file(key)
    _CATALOG_CACHE[key] = (mtime, now, catalog)
    return catalog


def refresh_catalog(data_path: str | None = None, *, force: bool = False) -> RagCatalog:
    explicit_path = data_path or os.environ.get("RAG_UI_DATA_PATH", "").strip() or os.environ.get("RAG_UI_DB_PATH", "").strip()
    if explicit_path:
        return _load_cached_file_catalog(resolve_data_path(explicit_path), force=force)

    pg_env = _pg_env()
    if pg_env is not None:
        cache_key = "postgres://instinct_lookup"
        now = time.time()
        cached = _CATALOG_CACHE.get(cache_key)
        if not force and cached and (now - cached[1]) < _refresh_interval_seconds():
            return cached[2]
        catalog = _load_catalog_from_postgres()
        _CATALOG_CACHE[cache_key] = (0.0, now, catalog)
        return catalog

    return _load_cached_file_catalog(resolve_data_path(data_path), force=force)


def load_catalog(data_path: str | None = None) -> RagCatalog:
    global _CATALOG_MEMORY
    if data_path is None and _CATALOG_MEMORY is not None:
        cached_at, catalog = _CATALOG_MEMORY
        if (time.time() - cached_at) < _refresh_interval_seconds():
            return catalog
    catalog = refresh_catalog(data_path)
    if data_path is None:
        _CATALOG_MEMORY = (time.time(), catalog)
    return catalog


def _prime_catalog_memory() -> None:
    global _CATALOG_MEMORY
    if _CATALOG_MEMORY is not None:
        return
    try:
        _CATALOG_MEMORY = (time.time(), refresh_catalog())
    except Exception:
        _CATALOG_MEMORY = None


_prime_catalog_memory()
