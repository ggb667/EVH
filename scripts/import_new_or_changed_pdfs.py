"""Import PDFs for a client/patient pair when the remote source has changed.

The script is designed for the PDF-ingestion slice in RD's tree:
- compare a remote PDF source against the existing MariaDB record for a patient
- avoid downloading the full PDF when stable headers show nothing changed
- download only new or changed PDFs
- optionally persist the refreshed inventory back to MariaDB

The implementation keeps the source side generic on purpose. You can feed it a
JSON manifest of candidate PDFs, or point it at a remote source list endpoint
that returns the same shape.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import uuid
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from scripts.instinct_pdf_chunker import (
    ChunkingConfig,
    PatientPdfSource,
    chunk_patient_pdf,
    load_into_postgres as load_chunks_into_postgres,
    load_term_index,
)
from scripts.instinct_document_state import (
    DatabaseDocumentState,
    LocalFileState,
    RemoteProbe,
    classify_document_state,
    probe_remote_pdf,
)


@dataclass(frozen=True)
class PdfSource:
    client_id: str
    patient_id: str
    pdf_id: str
    url: str
    filename: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_length: int | None = None


@dataclass(frozen=True)
class PdfRecord:
    pdf_id: str
    url: str | None
    filename: str | None
    signature: str | None
    etag: str | None
    last_modified: str | None
    content_length: int | None
    sha256: str | None
    local_path: str | None
    updated_at: str | None


@dataclass(frozen=True)
class LedgerRecord:
    id: str
    source_system: str
    source_reference_id: str
    clinic_id: str
    client_id: str
    pet_id: str | None
    filename: str
    source_uri: str
    source_checksum: str
    mime_type: str
    page_count: int
    ingest_status: str
    ingest_error_code: str | None
    ingest_error_detail: str | None
    pulled_at: str | None
    chunked_at: str | None
    created_at: str | None
    modified_at: str | None


@dataclass(frozen=True)
class ImportDecision:
    action: str
    reasons: tuple[str, ...]


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def sql_quote(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _json_scalar_value(field: dict[str, Any]) -> Any:
    if "stringValue" in field:
        return field["stringValue"]
    if "longValue" in field:
        return field["longValue"]
    if "doubleValue" in field:
        return field["doubleValue"]
    if "booleanValue" in field:
        return field["booleanValue"]
    if "isNull" in field and field["isNull"]:
        return None
    return None


def load_pdf_sources(path: Path) -> list[PdfSource]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("source manifest must be a JSON array")

    sources: list[PdfSource] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each source entry must be a JSON object")

        client_id = _normalize_optional_text(item.get("client_id") or item.get("client")) or ""
        patient_id = _normalize_optional_text(item.get("patient_id") or item.get("patient")) or ""
        pdf_id = _normalize_optional_text(item.get("pdf_id") or item.get("id") or item.get("document_id")) or ""
        url = _normalize_optional_text(item.get("url") or item.get("pdf_url") or item.get("source_url")) or ""

        if not client_id or not patient_id or not pdf_id or not url:
            raise ValueError(f"source entry is missing a required field: {item!r}")

        sources.append(
            PdfSource(
                client_id=client_id,
                patient_id=patient_id,
                pdf_id=pdf_id,
                url=url,
                filename=_normalize_optional_text(item.get("filename") or item.get("name")),
                etag=_normalize_optional_text(item.get("etag")),
                last_modified=_normalize_optional_text(item.get("last_modified") or item.get("lastModified")),
                content_length=_coerce_optional_int(item.get("content_length") or item.get("contentLength")),
            )
        )

    return sources


def _url_filename(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    name = Path(path).name
    return name or "downloaded.pdf"


def probe_pdf_signature(url: str, timeout: int = 30) -> RemoteProbe:
    return probe_remote_pdf(url, timeout=timeout)


def probe_pdf_checksum(url: str, timeout: int = 30) -> tuple[RemoteProbe, str | None]:
    probe = probe_pdf_signature(url, timeout=timeout)
    return probe, probe.fingerprint()


def download_pdf(url: str, destination: Path, timeout: int = 60) -> tuple[str, int]:
    request = Request(url)
    with urlopen(request, timeout=timeout) as response:
        data = response.read()

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return hashlib.sha256(data).hexdigest(), len(data)


def load_ledger_record(
    *,
    db_executor: str,
    database: str,
    table_name: str,
    client_id: str,
    pet_id: str,
    source_system: str,
    source_reference_id: str,
) -> LedgerRecord | None:
    sql = f"""
SELECT
  id,
  source_system,
  source_reference_id,
  clinic_id,
  client_id,
  pet_id,
  filename,
  source_uri,
  source_checksum,
  mime_type,
  page_count,
  ingest_status,
  ingest_error_code,
  ingest_error_detail,
  pulled_at,
  chunked_at,
  created_at,
  modified_at
FROM {table_name}
WHERE client_id = {sql_quote(client_id)}
  AND pet_id = {sql_quote(pet_id)}
  AND source_system = {sql_quote(source_system)}
  AND source_reference_id = {sql_quote(source_reference_id)}
LIMIT 1
""".strip()
    row = run_ledger_select(
        db_executor=db_executor,
        database=database,
        sql=sql,
    )
    if row is None:
        return None

    if len(row) != 18:
        raise ValueError(f"unexpected MariaDB row shape: {row!r}")
    return LedgerRecord(
        id=_normalize_optional_text(row[0]) or "",
        source_system=_normalize_optional_text(row[1]) or "",
        source_reference_id=_normalize_optional_text(row[2]) or "",
        clinic_id=_normalize_optional_text(row[3]) or "",
        client_id=_normalize_optional_text(row[4]) or "",
        pet_id=_normalize_optional_text(row[5]),
        filename=_normalize_optional_text(row[6]) or "",
        source_uri=_normalize_optional_text(row[7]) or "",
        source_checksum=_normalize_optional_text(row[8]) or "",
        mime_type=_normalize_optional_text(row[9]) or "",
        page_count=int(row[10] or 0),
        ingest_status=_normalize_optional_text(row[11]) or "",
        ingest_error_code=_normalize_optional_text(row[12]),
        ingest_error_detail=_normalize_optional_text(row[13]),
        pulled_at=_normalize_optional_text(row[14]),
        chunked_at=_normalize_optional_text(row[15]),
        created_at=_normalize_optional_text(row[16]),
        modified_at=_normalize_optional_text(row[17]),
    )


def load_database_document_state(
    *,
    db_executor: str,
    database: str,
    source_document_table_name: str,
    chunk_table_name: str,
    pdf_id: str,
) -> DatabaseDocumentState | None:
    sql = f"""
WITH chunk_state AS (
    SELECT
        COUNT(*)::int AS actual_chunk_count,
        MIN(chunk_index)::int AS min_chunk_index,
        MAX(chunk_index)::int AS max_chunk_index,
        COUNT(DISTINCT chunk_index)::int AS distinct_chunk_indexes,
        BOOL_OR(COALESCE(metadata::text LIKE '%table_records%', FALSE)) AS contains_table_records
    FROM {chunk_table_name}
    WHERE metadata->>'pdf_id' = {sql_quote(pdf_id)}
       OR metadata->>'source_reference_id' = {sql_quote(pdf_id)}
       OR source_uri LIKE '%' || {sql_quote(pdf_id)} || '%'
),
source_state AS (
    SELECT
        status,
        page_count,
        chunk_count,
        source_uri,
        metadata
    FROM {source_document_table_name}
    WHERE metadata->>'pdf_id' = {sql_quote(pdf_id)}
       OR metadata->>'source_reference_id' = {sql_quote(pdf_id)}
       OR source_uri LIKE '%' || {sql_quote(pdf_id)} || '%'
    ORDER BY processed_at DESC
    LIMIT 1
)
SELECT
    COALESCE(source_state.status, ''),
    source_state.page_count,
    source_state.chunk_count,
    source_state.source_uri,
    source_state.metadata,
    chunk_state.actual_chunk_count,
    chunk_state.min_chunk_index,
    chunk_state.max_chunk_index,
    chunk_state.distinct_chunk_indexes,
    chunk_state.contains_table_records
FROM source_state
LEFT JOIN chunk_state ON TRUE;
""".strip()
    row = run_ledger_select(
        db_executor=db_executor,
        database=database,
        sql=sql,
    )
    if row is None:
        return None

    status = _normalize_optional_text(row[0])
    page_count = _coerce_optional_int(row[1])
    expected_chunk_count = _coerce_optional_int(row[2])
    metadata = row[4] if len(row) > 4 else None
    actual_chunk_count = _coerce_optional_int(row[5]) or 0
    min_chunk_index = _coerce_optional_int(row[6])
    max_chunk_index = _coerce_optional_int(row[7])
    distinct_chunk_indexes = _coerce_optional_int(row[8]) or 0
    contains_table_records = bool(row[9]) if len(row) > 9 else False
    source_uri = _normalize_optional_text(row[3]) if len(row) > 3 else None
    source_size = None
    source_sha256 = None
    source_etag = None
    source_last_modified = None
    client_id = None
    patient_id = None
    if isinstance(metadata, dict):
        source_size = _coerce_optional_int(metadata.get("content_length") or metadata.get("source_size"))
        source_sha256 = _normalize_optional_text(metadata.get("downloaded_sha256") or metadata.get("source_sha256"))
        source_etag = _normalize_optional_text(metadata.get("remote_etag"))
        source_last_modified = _normalize_optional_text(metadata.get("remote_last_modified"))
        client_id = _normalize_optional_text(metadata.get("client_id"))
        patient_id = _normalize_optional_text(metadata.get("patient_id"))
    return DatabaseDocumentState(
        pdf_id=pdf_id,
        status=status,
        expected_chunk_count=expected_chunk_count,
        actual_chunk_count=actual_chunk_count,
        min_chunk_index=min_chunk_index,
        max_chunk_index=max_chunk_index,
        distinct_chunk_indexes=distinct_chunk_indexes,
        page_count=page_count,
        source_size=source_size,
        source_sha256=source_sha256,
        source_etag=source_etag,
        source_last_modified=source_last_modified,
        contains_table_records=contains_table_records,
        client_id=client_id,
        patient_id=patient_id,
    )


def should_fetch_pdf(source: PdfSource, probe_checksum: str | None, existing: LedgerRecord | None) -> bool:
    if probe_checksum is None:
        return True
    if existing is None:
        return True
    if existing.ingest_status not in {"succeeded", "skipped"}:
        return True
    return existing.source_checksum != probe_checksum


def classify_rerun(
    *,
    source: PdfSource,
    probe: RemoteProbe | None,
    existing: LedgerRecord | None,
    local_path: Path | None,
) -> ImportDecision:
    db_state = None
    if existing is not None:
        db_state = DatabaseDocumentState(
            pdf_id=source.pdf_id,
            status=existing.ingest_status,
            expected_chunk_count=existing.page_count,
            actual_chunk_count=existing.page_count if existing.ingest_status == "succeeded" else 0,
            min_chunk_index=1 if existing.ingest_status == "succeeded" else None,
            max_chunk_index=existing.page_count if existing.ingest_status == "succeeded" else None,
            distinct_chunk_indexes=existing.page_count if existing.ingest_status == "succeeded" else 0,
            page_count=existing.page_count,
            source_size=existing.content_length,
            source_sha256=existing.source_checksum,
            source_etag=None,
            source_last_modified=None,
            client_id=source.client_id,
            patient_id=source.patient_id,
        )
    local_state = None
    if local_path is not None:
        local_state = LocalFileState(
            path=local_path,
            exists=local_path.exists(),
            size=local_path.stat().st_size if local_path.exists() else None,
            sha256=None,
            looks_like_pdf=local_path.suffix.lower() == ".pdf" and local_path.exists(),
        )
    decision = classify_document_state(
        db_state=db_state,
        remote_probe=probe,
        local_state=local_state,
    )
    return ImportDecision(action=decision.action, reasons=decision.reasons)


def should_download(source: PdfSource, probe: SignatureProbe, existing: PdfRecord | None) -> bool:
    """Legacy compatibility wrapper for pre-ledger PDF download checks."""
    if existing is None:
        return True
    stable_key = probe.stable_key()
    if existing.signature and stable_key:
        return existing.signature != stable_key
    return existing.sha256 != probe.checksum()


def write_local_pdf(
    *,
    source: PdfSource,
    output_dir: Path,
) -> Path:
    filename = source.filename or _url_filename(source.url)
    safe_name = f"{source.client_id}_{source.patient_id}_{source.pdf_id}_{filename}"
    destination = output_dir / safe_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def persist_inventory(
    *,
    db_executor: str,
    database: str,
    table_name: str,
    source: PdfSource,
    ledger_record: LedgerRecord | None,
    probe: SignatureProbe,
    probe_checksum: str | None,
    page_count: int,
    ingest_status: str,
    ingest_error_code: str | None = None,
    ingest_error_detail: str | None = None,
    pulled_at: str | None = None,
    chunked_at: str | None = None,
) -> None:
    record_id = ledger_record.id if ledger_record else str(uuid.uuid4())
    sql = f"""
INSERT INTO {table_name} (
  id,
  source_system,
  source_reference_id,
  clinic_id,
  client_id,
  pet_id,
  filename,
  source_uri,
  source_checksum,
  mime_type,
  page_count,
  ingest_status,
  ingest_error_code,
  ingest_error_detail,
  pulled_at,
  chunked_at
)
VALUES (
  {sql_quote(record_id)},
  {sql_quote("instinct")},
  {sql_quote(source.pdf_id)},
  {sql_quote(source.client_id)},
  {sql_quote(source.client_id)},
  {sql_quote(source.patient_id)},
  {sql_quote(source.filename or _url_filename(source.url))},
  {sql_quote(source.url)},
  {sql_quote(probe_checksum)},
  {sql_quote(probe.content_type or "application/pdf")},
  {page_count},
  {sql_quote(ingest_status)},
  {sql_quote(ingest_error_code)},
  {sql_quote(ingest_error_detail)},
  {sql_quote(pulled_at)},
  {sql_quote(chunked_at)}
)
ON DUPLICATE KEY UPDATE
  source_system = VALUES(source_system),
  source_reference_id = VALUES(source_reference_id),
  clinic_id = VALUES(clinic_id),
  client_id = VALUES(client_id),
  pet_id = VALUES(pet_id),
  filename = VALUES(filename),
  source_uri = VALUES(source_uri),
  source_checksum = VALUES(source_checksum),
  mime_type = VALUES(mime_type),
  page_count = VALUES(page_count),
  ingest_status = VALUES(ingest_status),
  ingest_error_code = VALUES(ingest_error_code),
  ingest_error_detail = VALUES(ingest_error_detail),
  pulled_at = VALUES(pulled_at),
  chunked_at = VALUES(chunked_at);
""".strip()
    run_ledger_write(
        db_executor=db_executor,
        database=database,
        sql=sql,
    )


def _build_data_api_env() -> dict[str, str]:
    cluster_arn = os.environ.get("DB_CLUSTER_ARN")
    secret_arn = os.environ.get("DB_SECRET_ARN")
    database = os.environ.get("DB_NAME")
    if not cluster_arn or not secret_arn or not database:
        raise RuntimeError(
            "AWS Data API needs DB_CLUSTER_ARN, DB_SECRET_ARN, and DB_NAME in the environment."
        )
    return {"cluster_arn": cluster_arn, "secret_arn": secret_arn, "database": database}


def _sql_to_field(value: Any) -> dict[str, Any]:
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"longValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _execute_data_api_statement(
    sql: str,
    *,
    database: str,
    include_results: bool,
) -> dict[str, Any]:
    env = _build_data_api_env()
    command = [
        "aws",
        "rds-data",
        "execute-statement",
        "--resource-arn",
        env["cluster_arn"],
        "--secret-arn",
        env["secret_arn"],
        "--database",
        database,
        "--sql",
        sql,
    ]
    if include_results:
        command.extend(["--include-result-metadata", "--format-records-as", "JSON"])

    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, 4):
        try:
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except subprocess.CalledProcessError as exc:
            last_error = exc
            stderr = (exc.stderr or "").lower()
            wake_signals = (
                "databaseunavailableexception",
                "database is not available",
                "please retry",
                "throttl",
                "timeout",
                "temporarily unavailable",
                "cluster is resuming",
            )
            if attempt >= 3 or not any(signal in stderr for signal in wake_signals):
                raise
            time.sleep(2 * attempt)

    if last_error is not None:
        raise last_error
    return {}


def run_ledger_select(
    *,
    db_executor: str,
    sql: str,
    database: str,
) -> list[Any] | None:
    if db_executor == "mysql":
        mysql_command = shutil.which("mariadb") or shutil.which("mysql")
        if not mysql_command:
            raise RuntimeError("mysql executor requested but no mariadb/mysql client is installed.")
        result = subprocess.run(
            [mysql_command, "-N", "-B", "-D", database, "-e", sql],
            check=True,
            text=True,
            capture_output=True,
        )
        line = result.stdout.strip()
        if not line:
            return None
        return line.split("\t")

    payload = _execute_data_api_statement(sql, database=database, include_results=True)
    records = payload.get("records") or []
    if not records:
        return None
    first_row = records[0]
    return [_json_scalar_value(field) for field in first_row]


def run_ledger_write(
    *,
    db_executor: str,
    sql: str,
    database: str,
) -> None:
    if db_executor == "mysql":
        mysql_command = shutil.which("mariadb") or shutil.which("mysql")
        if not mysql_command:
            raise RuntimeError("mysql executor requested but no mariadb/mysql client is installed.")
        subprocess.run([mysql_command, "-D", database, "-e", sql], check=True, text=True, capture_output=True)
        return

    _execute_data_api_statement(sql, database=database, include_results=False)


def extract_page_count(pdf_path: Path) -> int:
    from io import BytesIO

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment-specific dependency
        raise RuntimeError("pypdf is required to inspect PDF page counts.") from exc

    reader = PdfReader(BytesIO(pdf_path.read_bytes()))
    return len(reader.pages)


def run(args: argparse.Namespace) -> int:
    sources = load_pdf_sources(Path(args.source_manifest))
    selected = [source for source in sources if source.client_id == args.client_id and source.patient_id == args.patient_id]
    if not selected:
        print("No PDFs matched the requested client/patient.")
        return 0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    refreshed: list[dict[str, Any]] = []
    for source in selected:
        print(
            f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] start "
            f"filename={source.filename or 'unknown'}",
            flush=True,
        )
        probe, probe_checksum = probe_pdf_checksum(source.url, timeout=args.timeout)
        print(
            f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] probe "
            f"content_length={probe.content_length} changed={probe_checksum}",
            flush=True,
        )
        existing = load_ledger_record(
            db_executor=args.db_executor,
            database=args.database,
            table_name=args.table_name,
            client_id=args.client_id,
            pet_id=args.patient_id,
            source_system=args.source_system,
            source_reference_id=source.pdf_id,
        )

        if not should_fetch_pdf(source, probe_checksum, existing):
            print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] unchanged", flush=True)
            refreshed.append(
                {
                    "pdf_id": source.pdf_id,
                    "status": "unchanged",
                    "source_checksum": existing.source_checksum if existing else probe_checksum,
                    "local_path": existing.ingest_error_detail if existing else None,
                }
            )
            continue

        if args.persist:
            print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] marking running", flush=True)
            persist_inventory(
                db_executor=args.db_executor,
                database=args.database,
                table_name=args.table_name,
                source=source,
                ledger_record=existing,
                probe=probe,
                probe_checksum=probe_checksum,
                page_count=0,
                ingest_status="running",
                pulled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
            )

        destination = write_local_pdf(
            source=source,
            output_dir=output_dir,
        )
        try:
            print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] downloading", flush=True)
            sha256, content_length = download_pdf(source.url, destination, timeout=args.timeout)
            page_count = extract_page_count(destination)
            print(
                f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] downloaded "
                f"bytes={content_length} pages={page_count}",
                flush=True,
            )
        except Exception as exc:
            if args.persist:
                persist_inventory(
                    db_executor=args.db_executor,
                    database=args.database,
                    table_name=args.table_name,
                    source=source,
                    ledger_record=existing,
                    probe=probe,
                    probe_checksum=probe_checksum,
                    page_count=0,
                    ingest_status="failed",
                    ingest_error_code=type(exc).__name__,
                    ingest_error_detail=str(exc),
                    pulled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                )
            refreshed.append(
                {
                    "pdf_id": source.pdf_id,
                    "status": "failed",
                    "source_checksum": probe_checksum,
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }
            )
            continue

        chunk_report: dict[str, Any] | None = None
        if args.chunk_after_download:
            print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] chunking", flush=True)
            patient_source = PatientPdfSource(
                patient_id=source.patient_id,
                patient_name=args.patient_name or source.client_id,
                pdf_path=destination,
            )
            chunk_docs, _ = chunk_patient_pdf(
                patient_source,
                ChunkingConfig(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap),
                term_index=load_term_index(Path(args.dictionary_csv) if args.dictionary_csv else None),
            )
            chunk_report = {
                "chunk_count": len(chunk_docs),
                "clinical_summary": chunk_docs[0].metadata.get("clinical_summary", "") if chunk_docs else "",
                "summary_style": chunk_docs[0].metadata.get("clinical_summary_style", "") if chunk_docs else "",
                "term_summary": chunk_docs[0].metadata.get("term_summary", {}) if chunk_docs else {},
            }
            if args.vector_load:
                if not args.vector_database_url:
                    raise RuntimeError("--vector-database-url is required when --vector-load is enabled.")
                print(
                    f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] loading vectors "
                    f"model={args.embedding_model} dims={args.vector_dimensions}",
                    flush=True,
                )
                load_chunks_into_postgres(
                    database_url=args.vector_database_url,
                    table_name=args.vector_table_name,
                    source_name=f"{source.client_id}:{source.patient_id}",
                    source_uri=str(destination),
                    documents=chunk_docs,
                    embedding_model=args.embedding_model,
                    vector_dimensions=args.vector_dimensions,
                )
                print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] vector load complete", flush=True)

        if args.persist:
            print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] persisting success", flush=True)
            persist_inventory(
                db_executor=args.db_executor,
                database=args.database,
                table_name=args.table_name,
                source=source,
                ledger_record=existing,
                probe=probe,
                probe_checksum=probe_checksum,
                page_count=page_count,
                ingest_status="succeeded",
                pulled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                chunked_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f") if args.chunk_after_download else None,
            )

        refreshed.append(
            {
                "pdf_id": source.pdf_id,
                "status": "downloaded",
                "source_checksum": probe_checksum,
                "local_path": str(destination),
                "sha256": sha256,
                "content_length": content_length,
                "page_count": page_count,
                "chunk_report": chunk_report,
            }
        )

        if args.delete_local_after_load:
            try:
                destination.unlink(missing_ok=True)
                print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] deleted local file", flush=True)
            except Exception:
                pass
        print(f"[{source.client_id}:{source.patient_id}:{source.pdf_id}] done", flush=True)

    print(
        json.dumps(
            {
                "client_id": args.client_id,
                "patient_id": args.patient_id,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "download_dir": str(output_dir),
                "results": refreshed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import new or changed PDFs for a client/patient pair.")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--source-manifest", required=True, help="JSON manifest containing candidate PDF URLs.")
    parser.add_argument("--database", required=True, help="MariaDB database name.")
    parser.add_argument("--table-name", default="patient_pdfs")
    parser.add_argument("--source-system", default="instinct")
    parser.add_argument(
        "--db-executor",
        choices=("auto", "mysql", "aws-data-api"),
        default="auto",
        help="Use local MySQL/MariaDB CLI or AWS RDS Data API.",
    )
    parser.add_argument("--output-dir", default="downloads/pdfs")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--persist", action="store_true", help="Write refreshed inventory back to MariaDB.")
    parser.add_argument("--chunk-after-download", action="store_true", help="Run the chunker after each successful download.")
    parser.add_argument("--vector-load", action="store_true", help="Load chunks into the vector DB after chunking.")
    parser.add_argument(
        "--delete-local-after-load",
        action="store_true",
        help="Delete the downloaded local PDF after successful processing/loading.",
    )
    parser.add_argument("--vector-database-url", default="", help="Postgres connection URL for vector loading.")
    parser.add_argument("--vector-table-name", default="pms_page_chunk")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--vector-dimensions", type=int, default=1536)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument("--patient-name", default="", help="Optional patient name for chunk metadata.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.db_executor == "auto":
        args.db_executor = "mysql" if (shutil.which("mariadb") or shutil.which("mysql")) else "aws-data-api"
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
