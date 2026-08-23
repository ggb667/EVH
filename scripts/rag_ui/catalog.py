from __future__ import annotations

import json
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


def _build_fragment_index(items: Iterable[Any], min_len: int = 3, max_len: int = 7) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for item in items:
        item_id = str(item.id)
        for token in _search_tokens(getattr(item, "search_text", "")):
            token_len = len(token)
            for start in range(token_len):
                stop = min(token_len, start + max_len)
                for end in range(start + min_len, stop + 1):
                    index.setdefault(token[start:end], set()).add(item_id)
    return index


def _fragment_scores(query: str, index: dict[str, set[str]], min_len: int = 3, max_len: int = 7) -> dict[str, int]:
    # Each query token contributes only its single longest match for a candidate.
    # We remove characters from the front only.
    totals: dict[str, int] = {}
    for token in _search_tokens(query):
        per_token: dict[str, int] = {}
        for start in range(max(0, len(token) - min_len + 1)):
            suffix = token[start:]
            key = suffix[:max_len]
            if len(key) < min_len:
                continue
            for item_id in index.get(key, ()):
                score = min(len(suffix), max_len)
                if score > per_token.get(item_id, 0):
                    per_token[item_id] = score
        for item_id, score in per_token.items():
            totals[item_id] = totals.get(item_id, 0) + score
    return totals


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
        "/home/ggb66/dev/EVH/scripts/patients.json",
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
    raw = os.environ.get("RAG_UI_REFRESH_SECONDS", "300").strip()
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
        return [self.clients_by_id[item_id].as_dict() for item_id in sorted(scores, key=scores.get, reverse=True)]

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
        return [self.pets_by_id[item_id].as_dict() for item_id in sorted(scores, key=scores.get, reverse=True)]


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
    catalog = load_catalog()
    patient = catalog.pets_by_id.get(str(pet_id or "").strip()) if pet_id else None
    documents: list[dict[str, Any]] = []
    for pet in catalog.pets_by_client.get(str(client_id).strip(), []):
        if patient and pet.id != patient.id:
            continue
        documents.append(
            {
                "document_id": pet.id,
                "document_title": pet.label,
                "source_uri": "",
                "page_number": 1,
                "page_label": "Page 1",
                "source_page_url": "",
            }
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


def query_options_from_postgres(kind: str, query: str, client_id: str | None = None) -> list[dict[str, Any]]:
    connection = _pg_connect()
    if connection is None:
        return []

    kind = str(kind or "client").strip().lower()
    query_text = str(query or "").strip()
    tokens = [term for term in re.findall(r"[A-Za-z0-9]+", query_text) if len(term) >= 3][:8]
    cursor = connection.cursor()
    try:
        if kind == "pet":
            client_id = str(client_id or "").strip()
            if not client_id:
                return []
            sql = """
                select
                  patient_id::text as id,
                  coalesce(nullif(patient_name, ''), nullif(patient_pims_code, ''), patient_id::text) as label,
                  coalesce(nullif(patient_pims_code, ''), patient_id::text) as secondary,
                  coalesce(nullif(species, ''), '') as species,
                  coalesce(nullif(breed, ''), '') as breed,
                  coalesce(owner_name, '') as owner_name
                from public.instinct_patient_lookup
                where account_id = %s
            """
            params: list[Any] = [client_id]
            if tokens:
                likes = " and ".join(["(patient_name ilike %s or patient_pims_code ilike %s or owner_name ilike %s)"] * len(tokens))
                sql += f" and ({likes})"
                for term in tokens:
                    params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
            sql += " order by label asc limit 10"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": str(row[0] or "").strip(),
                    "label": str(row[1] or "").strip(),
                    "secondary": str(row[2] or "").strip(),
                    "clientId": client_id,
                    "clientLabel": str(row[5] or "").strip(),
                    "species": str(row[3] or "").strip(),
                    "breed": str(row[4] or "").strip(),
                    "birthdate": "",
                    "alertCount": 0,
                    "microchipId": None,
                }
                for row in rows
                if str(row[0] or "").strip()
            ]

        sql = """
            select
              account_id as id,
              coalesce(nullif(owner_name, ''), nullif(pims_code, ''), account_id) as label,
              coalesce(nullif(pims_code, ''), account_id) as secondary
            from public.instinct_owner_lookup_norm
        """
        params = []
        if tokens:
            likes = " and ".join(["(owner_name ilike %s or pims_code ilike %s or account_id ilike %s)"] * len(tokens))
            sql += f" where ({likes})"
            for term in tokens:
                params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
        sql += " order by label asc limit 10"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [
            {
                "id": str(row[0] or "").strip(),
                "label": str(row[1] or "").strip(),
                "secondary": str(row[2] or "").strip(),
                "petCount": 0,
            }
            for row in rows
            if str(row[0] or "").strip()
        ]
    finally:
        cursor.close()
        connection.close()


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


@lru_cache(maxsize=4)
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
_CATALOG_MEMORY: RagCatalog | None = None


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
        return _CATALOG_MEMORY
    catalog = refresh_catalog(data_path)
    if data_path is None:
        _CATALOG_MEMORY = catalog
    return catalog
