from __future__ import annotations

import json
import os
import re
import subprocess
import sqlite3
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


def _normalize(value: Any) -> str:
    text = re.sub(r"[^a-z]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _normalize_tokens(value: Any) -> list[str]:
    normalized = _normalize(value)
    return normalized.split() if normalized else []


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
        import psycopg

        return psycopg.connect(
            host=env["EVH_PGHOST"],
            port=int(env["EVH_PGPORT"]),
            dbname=env["EVH_PGDATABASE"],
            user=env["EVH_PGUSER"],
            password=env["EVH_PGPASSWORD"],
            connect_timeout=10,
        )
    except Exception:
        import pg8000.dbapi as pg  # type: ignore

        return pg.connect(
            host=env["EVH_PGHOST"],
            port=int(env["EVH_PGPORT"]),
            database=env["EVH_PGDATABASE"],
            user=env["EVH_PGUSER"],
            password=env["EVH_PGPASSWORD"],
            timeout=10,
        )


def _table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(
        """
        select column_name
        from information_schema.columns
        where table_schema = 'public' and table_name = %s
        """,
        (table_name,),
    )
    return {str(row[0]) for row in cursor.fetchall()}


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
        }


@dataclass(frozen=True)
class RagCatalog:
    clients: list[ClientOption]
    pets_by_client: dict[str, list[PetOption]]
    clients_by_id: dict[str, ClientOption]
    pets_by_id: dict[str, PetOption]

    def search_clients(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        normalized = _normalize(query)
        ordered = sorted(self.clients, key=lambda item: (item.label.lower(), item.secondary.lower()))
        if len(normalized) < 3:
            return [item.as_dict() for item in ordered[:limit]]

        query_tokens = _normalize_tokens(query)
        if not query_tokens:
            return [item.as_dict() for item in ordered[:limit]]

        matches = [
            item
            for item in ordered
            if all(token in item.search_text for token in query_tokens)
            or item.label.lower().startswith(normalized)
            or item.search_text.startswith(normalized)
        ]
        ranked = sorted(
            matches,
            key=lambda item: (
                0 if item.label.lower().startswith(normalized) else 1,
                0 if item.search_text.startswith(normalized) else 1,
                0 if all(token in item.label.lower() for token in query_tokens) else 1,
                item.label.lower(),
                item.secondary.lower(),
            ),
        )
        return [item.as_dict() for item in ranked[:limit]]

    def search_pets(self, client_id: str | None, query: str, limit: int = 10) -> list[dict[str, Any]]:
        normalized = _normalize(query)
        if client_id and client_id in self.pets_by_client:
            source = self.pets_by_client[client_id]
        else:
            source = sorted(self.pets_by_id.values(), key=lambda item: (item.client_label.lower(), item.label.lower()))

        ordered = sorted(source, key=lambda item: (item.label.lower(), item.secondary.lower()))
        if len(normalized) < 3:
            return [item.as_dict() for item in ordered[:limit]]

        query_tokens = _normalize_tokens(query)
        if not query_tokens:
            return [item.as_dict() for item in ordered[:limit]]

        matches = [
            item
            for item in ordered
            if all(token in item.search_text for token in query_tokens)
            or item.label.lower().startswith(normalized)
            or item.search_text.startswith(normalized)
        ]
        ranked = sorted(
            matches,
            key=lambda item: (
                0 if item.label.lower().startswith(normalized) else 1,
                0 if item.search_text.startswith(normalized) else 1,
                0 if all(token in item.label.lower() for token in query_tokens) else 1,
                item.label.lower(),
                item.secondary.lower(),
            ),
        )
        return [item.as_dict() for item in ranked[:limit]]


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
            ORDER BY display_name COLLATE NOCASE, pims_code COLLATE NOCASE
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
            ORDER BY name COLLATE NOCASE, pims_code COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()

    clients: list[ClientOption] = []
    clients_by_id: dict[str, ClientOption] = {}

    for row in account_rows:
        client_id = str(row["id"] or "").strip()
        if not client_id:
            continue
        label = str(row["display_name"] or "").strip() or str(row["owner_first_name"] or "").strip() or str(row["pims_code"] or "").strip() or client_id
        secondary = " ".join(
            part
            for part in (
                str(row["pims_code"] or "").strip(),
                str(row["pims_id"] or "").strip(),
                client_id,
            )
            if part
        )
        search_text = _normalize(" ".join([label, secondary, str(row["owner_first_name"] or ""), str(row["owner_last_name"] or "")]))
        option = ClientOption(
            id=client_id,
            label=label,
            secondary=secondary,
            pet_count=0,
            search_text=search_text,
        )
        clients.append(option)
        clients_by_id[client_id] = option

    pets_by_client: dict[str, list[PetOption]] = {}
    pets_by_id: dict[str, PetOption] = {}
    pet_counts: dict[str, int] = {}

    for row in patient_rows:
        client_id = str(row["account_id"] or "").strip()
        if not client_id or client_id not in clients_by_id:
            continue
        pet_id = str(row["id"] or "").strip()
        if not pet_id:
            continue
        client_label = clients_by_id[client_id].label
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
            raw = {}
        secondary = _pet_secondary(
            {
                "species": {"label": species} if species else {},
                "breed": {"label": breed} if breed else {},
                "pimsCode": row["pims_code"] or "",
            }
        )
        search_text = _normalize(" ".join([name, secondary, client_label, str(row["pims_code"] or ""), pet_id]))
        option = PetOption(
            id=pet_id,
            label=name,
            secondary=secondary,
            client_id=client_id,
            client_label=client_label,
            species=species,
            breed=breed,
            birthdate=birthdate,
            alert_count=len(alerts),
            search_text=search_text,
        )
        pets_by_client.setdefault(client_id, []).append(option)
        pets_by_id[pet_id] = option
        pet_counts[client_id] = pet_counts.get(client_id, 0) + 1

    clients = [
        ClientOption(
            id=client.id,
            label=client.label,
            secondary=client.secondary,
            pet_count=pet_counts.get(client.id, 0),
            search_text=client.search_text,
        )
        for client in clients
    ]
    return RagCatalog(
        clients=clients,
        pets_by_client=pets_by_client,
        clients_by_id={client.id: client for client in clients},
        pets_by_id=pets_by_id,
    )


@lru_cache(maxsize=4)
def load_catalog_from_file(data_path: str) -> RagCatalog:
    path = Path(data_path)
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return _load_catalog_from_sqlite(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    raw_accounts = payload.get("accounts", [])
    raw_patients = payload.get("patients", [])

    clients: list[ClientOption] = []
    clients_by_id: dict[str, ClientOption] = {}

    for account in raw_accounts:
        if not isinstance(account, dict):
            continue
        if account.get("deletedAt") is not None:
            continue

        client_id = str(account.get("id") or "").strip()
        if not client_id:
            continue

        label = _client_display_name(account)
        secondary = _client_secondary(account)
        search_text = _normalize(
            " ".join(
                [
                    label,
                    secondary,
                    account.get("note") or "",
                ]
            )
        )
        option = ClientOption(
            id=client_id,
            label=label,
            secondary=secondary,
            pet_count=0,
            search_text=search_text,
        )
        clients.append(option)
        clients_by_id[client_id] = option

    pets_by_client: dict[str, list[PetOption]] = {}
    pets_by_id: dict[str, PetOption] = {}
    pet_counts: dict[str, int] = {}

    for patient in raw_patients:
        if not isinstance(patient, dict):
            continue
        if patient.get("deletedAt") is not None:
            continue

        client_id = str(patient.get("accountId") or "").strip()
        if not client_id or client_id not in clients_by_id:
            continue

        client_label = clients_by_id[client_id].label
        pet_id = str(patient.get("id") or "").strip()
        if not pet_id:
            continue

        species = (patient.get("species") or {}).get("label") or ""
        breed = (patient.get("breed") or {}).get("label") or ""
        birthdate = str(patient.get("birthdate") or "").strip()
        alert_count = len(patient.get("alerts") or [])
        label = _pet_display_name(patient)
        secondary = _pet_secondary(patient)
        search_text = _normalize(
            " ".join(
                [
                    label,
                    secondary,
                    client_label,
                    patient.get("pimsCode") or "",
                    str(patient.get("id") or ""),
                ]
            )
        )
        option = PetOption(
            id=pet_id,
            label=label,
            secondary=secondary,
            client_id=client_id,
            client_label=client_label,
            species=species,
            breed=breed,
            birthdate=birthdate,
            alert_count=alert_count,
            search_text=search_text,
        )
        pets_by_client.setdefault(client_id, []).append(option)
        pets_by_id[pet_id] = option
        pet_counts[client_id] = pet_counts.get(client_id, 0) + 1

    clients = [
        ClientOption(
            id=client.id,
            label=client.label,
            secondary=client.secondary,
            pet_count=pet_counts.get(client.id, 0),
            search_text=client.search_text,
        )
        for client in clients
    ]
    clients.sort(key=lambda item: (item.label.lower(), item.secondary.lower()))
    for client_id, pet_list in pets_by_client.items():
        pet_list.sort(key=lambda item: (item.label.lower(), item.secondary.lower()))

    clients_by_id = {client.id: client for client in clients}
    return RagCatalog(
        clients=clients,
        pets_by_client=pets_by_client,
        clients_by_id=clients_by_id,
        pets_by_id=pets_by_id,
    )


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
            order by lower(coalesce(owner_name_last_first, owner_name, pims_code, account_id)),
                     lower(coalesce(pims_code, account_id));
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
            order by lower(coalesce(patient_name, patient_pims_code, patient_id::text)),
                     lower(coalesce(patient_pims_code, patient_id::text));
            """
        )
        patient_rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    clients: list[ClientOption] = []
    clients_by_id: dict[str, ClientOption] = {}
    pets_by_client: dict[str, list[PetOption]] = {}
    pets_by_id: dict[str, PetOption] = {}
    pet_counts: dict[str, int] = {}

    for account_id, label, secondary, owner_name in owner_rows:
        client_id = str(account_id or "").strip()
        if not client_id:
            continue
        label = str(label or "").strip() or client_id
        secondary = str(secondary or "").strip()
        search_text = _normalize(" ".join([label, secondary, owner_name]))
        option = ClientOption(
            id=client_id,
            label=label,
            secondary=secondary,
            pet_count=0,
            search_text=search_text,
        )
        clients.append(option)
        clients_by_id[client_id] = option

    for patient_id, account_id, label, species, breed, pims_code, owner_name in patient_rows:
        client_id = str(account_id or "").strip()
        if not client_id or client_id not in clients_by_id:
            continue
        pet_id = str(patient_id or "").strip()
        if not pet_id:
            continue
        client_label = clients_by_id[client_id].label
        label = str(label or "").strip() or pet_id
        species = str(species or "").strip()
        breed = str(breed or "").strip()
        pims_code = str(pims_code or "").strip()
        secondary = _pet_secondary(
            {
                "species": {"label": species} if species else {},
                "breed": {"label": breed} if breed else {},
                "pimsCode": pims_code,
            }
        )
        search_text = _normalize(" ".join([label, secondary, client_label, pims_code, pet_id, owner_name]))
        option = PetOption(
            id=pet_id,
            label=label,
            secondary=secondary,
            client_id=client_id,
            client_label=client_label,
            species=species,
            breed=breed,
            birthdate="",
            alert_count=0,
            search_text=search_text,
        )
        pets_by_client.setdefault(client_id, []).append(option)
        pets_by_id[pet_id] = option
        pet_counts[client_id] = pet_counts.get(client_id, 0) + 1

    clients = [
        ClientOption(
            id=client.id,
            label=client.label,
            secondary=client.secondary,
            pet_count=pet_counts.get(client.id, 0),
            search_text=client.search_text,
        )
        for client in clients
    ]
    clients.sort(key=lambda item: (item.label.lower(), item.secondary.lower()))
    for client_id, pet_list in pets_by_client.items():
        pet_list.sort(key=lambda item: (item.label.lower(), item.secondary.lower()))
    clients_by_id = {client.id: client for client in clients}
    return RagCatalog(
        clients=clients,
        pets_by_client=pets_by_client,
        clients_by_id=clients_by_id,
        pets_by_id=pets_by_id,
    )


def _page_url(source_uri: str | None, source_reference_id: str | None, page_number: int) -> str:
    if source_uri and str(source_uri).strip():
        return f"{str(source_uri).strip()}#page={page_number}"
    if source_reference_id:
        return f"/api/rag/documents/{source_reference_id}/pages/{page_number}"
    return "#"


@dataclass(frozen=True)
class _CachedPetContext:
    loaded_at: float
    expires_at: float
    chunks: list[dict[str, Any]]


_PET_CONTEXT_CACHE: dict[tuple[str, str], _CachedPetContext] = {}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_pet_context_chunks_fresh(client_id: str, pet_id: str | None, limit: int | None = None) -> list[dict[str, Any]]:
    connection = _pg_connect()
    if connection is None:
        raise FileNotFoundError("Postgres env vars are missing")
    cursor = connection.cursor()
    try:
        columns = _table_columns(cursor, "pms_page_chunk")
        params: list[Any] = []
        where = ["chunk_text is not null"]
        if client_id:
            if "client_id" in columns:
                where.append("client_id = %s")
                params.append(client_id)
            elif "client_instinct_uuid" in columns:
                where.append("client_instinct_uuid = %s")
                params.append(client_id)
            else:
                where.append("(metadata->>'account_id' = %s or metadata->>'client_id' = %s)")
                params.extend([client_id, client_id])
        if pet_id:
            if "patient_id" in columns:
                where.append("patient_id = %s")
                params.append(pet_id)
            elif "pet_id" in columns:
                where.append("pet_id = %s")
                params.append(pet_id)
            else:
                where.append("(metadata->>'patient_id' = %s or metadata->>'pet_id' = %s)")
                params.extend([pet_id, pet_id])
        limit_clause = ""
        if limit is not None and limit > 0:
            limit_clause = " limit %s"
            params.append(limit)
        sql = f"""
            select
              coalesce(metadata->>'pdf_id', metadata->>'source_reference_id', source_name) as document_id,
              coalesce(metadata->>'document_title', source_name, metadata->>'patient_name', metadata->>'owner_name', 'Source PDF') as document_title,
              page_number,
              coalesce(metadata->>'page_label', 'Page ' || page_number::text) as page_label,
              source_uri,
              coalesce(chunk_text, '') as chunk_text,
              coalesce(source_name, '') as source_name,
              coalesce((metadata->>'confidence')::double precision, 0.87) as confidence,
              coalesce(metadata->>'document_date', metadata->>'record_date', metadata->>'updated_at', to_char(now(), 'YYYY-MM-DD')) as date
            from public.pms_page_chunk
            where {" and ".join(where)}
            order by page_number asc, confidence desc, source_name asc, chunk_index asc
            {limit_clause}
        """
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    chunks: list[dict[str, Any]] = []
    for document_id, document_title, page_number, page_label, source_uri, chunk_text, source_name, confidence, date in rows:
        page_number = int(page_number or 1)
        chunks.append(
            RagContextChunk(
                document_id=str(document_id or ""),
                document_title=str(document_title or "Source PDF"),
                page_number=page_number,
                page_label=str(page_label or f"Page {page_number}"),
                source_page_url=_page_url(str(source_uri or ""), str(document_id or ""), page_number),
                chunk_text=str(chunk_text or ""),
                source_name=str(source_name or ""),
                confidence=float(confidence or 0.0),
                date=str(date or ""),
            ).as_hit()
        )
    return chunks


def load_pet_context_chunks(client_id: str, pet_id: str | None, limit: int | None = None) -> list[dict[str, Any]]:
    cache_key = (str(client_id or ""), str(pet_id or ""))
    now = time.time()
    cached = _PET_CONTEXT_CACHE.get(cache_key)
    ttl = _context_ttl_seconds()

    if cached is not None:
        if now <= cached.expires_at:
            return cached.chunks[:limit]
        stale_for = max(0.0, now - cached.expires_at)
        print(
            f"[{_utc_timestamp()}] RAG context expired for client_id={cache_key[0]!r} pet_id={cache_key[1]!r}; "
            f"stale_for_seconds={stale_for:.1f}; rebuilding"
        )

    chunks = _load_pet_context_chunks_fresh(client_id, pet_id, limit=limit)
    _PET_CONTEXT_CACHE[cache_key] = _CachedPetContext(
        loaded_at=now,
        expires_at=now + ttl,
        chunks=chunks,
    )
    return chunks if limit is None or limit <= 0 else chunks[:limit]


def search_document_hits(client_id: str, pet_id: str | None, question: str, limit: int = 8) -> list[dict[str, Any]]:
    context_chunks = load_pet_context_chunks(client_id, pet_id, limit=None)
    if not question:
        return context_chunks[:limit]

    normalized = _normalize(question)
    query_tokens = _normalize_tokens(question)
    scored: list[tuple[tuple[int, int, int, int, str, str], dict[str, Any]]] = []
    for item in context_chunks:
        haystack = _normalize(" ".join([item.get("snippet", ""), item.get("document_title", ""), item.get("page_label", ""), item.get("document_id", "")]))
        score = (
            0 if normalized and haystack.startswith(normalized) else 1,
            0 if all(token in haystack for token in query_tokens) else 1,
            0 if normalized and normalized in haystack else 1,
            item.get("page_number", 0),
            str(item.get("document_title", "")).lower(),
            str(item.get("page_label", "")).lower(),
        )
        if not query_tokens or score[1] == 0 or score[2] == 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0])
    return [item for _, item in scored[:limit]]


_CATALOG_CACHE: dict[str, tuple[float, float, RagCatalog]] = {}


def refresh_catalog(data_path: str | None = None, *, force: bool = False) -> RagCatalog:
    if data_path:
        resolved = resolve_data_path(data_path)
        cache_key = str(resolved)
        now = time.time()
        cached = _CATALOG_CACHE.get(cache_key)
        mtime = resolved.stat().st_mtime if resolved.exists() else 0.0
        if not force and cached is not None:
            cached_mtime, cached_at, cached_catalog = cached
            if cached_mtime == mtime and (now - cached_at) < _refresh_interval_seconds():
                return cached_catalog
        catalog = load_catalog_from_file(cache_key)
        _CATALOG_CACHE[cache_key] = (mtime, now, catalog)
        return catalog

    explicit_env_path = os.environ.get("RAG_UI_DATA_PATH", "").strip() or os.environ.get("RAG_UI_DB_PATH", "").strip()
    if explicit_env_path:
        resolved = resolve_data_path(explicit_env_path)
        cache_key = str(resolved)
        now = time.time()
        cached = _CATALOG_CACHE.get(cache_key)
        mtime = resolved.stat().st_mtime if resolved.exists() else 0.0
        if not force and cached is not None:
            cached_mtime, cached_at, cached_catalog = cached
            if cached_mtime == mtime and (now - cached_at) < _refresh_interval_seconds():
                return cached_catalog
        catalog = load_catalog_from_file(cache_key)
        _CATALOG_CACHE[cache_key] = (mtime, now, catalog)
        return catalog

    pg_env = _pg_env()
    if pg_env is not None:
        cache_key = "postgres://instinct_lookup"
        now = time.time()
        cached = _CATALOG_CACHE.get(cache_key)
        if not force and cached is not None and (now - cached[1]) < _refresh_interval_seconds():
            return cached[2]
        catalog = _load_catalog_from_postgres()
        _CATALOG_CACHE[cache_key] = (0.0, now, catalog)
        return catalog

    resolved = resolve_data_path(data_path)
    cache_key = str(resolved)
    now = time.time()
    mtime = resolved.stat().st_mtime if resolved.exists() else 0.0
    cached = _CATALOG_CACHE.get(cache_key)

    if not force and cached is not None:
        cached_mtime, cached_at, cached_catalog = cached
        if cached_mtime == mtime and (now - cached_at) < _refresh_interval_seconds():
            return cached_catalog

    catalog = load_catalog_from_file(cache_key)
    _CATALOG_CACHE[cache_key] = (mtime, now, catalog)
    return catalog


def load_catalog(data_path: str | None = None) -> RagCatalog:
    return refresh_catalog(data_path)
