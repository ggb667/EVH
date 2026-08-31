"""Shared Instinct document identity and remote-probe helpers.

These helpers keep the rerun path from scattering size-probe and identity
logic across the import scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RemoteProbe:
    outcome: Literal["success", "unsupported", "failed"]
    content_length: int | None
    etag: str | None
    last_modified: str | None
    content_type: str | None
    range_supported: bool
    error: str | None = None

    @property
    def has_comparable_identity(self) -> bool:
        return any((self.content_length is not None, self.etag is not None, self.last_modified is not None))

    def fingerprint(self) -> str | None:
        if not self.has_comparable_identity:
            return None
        key = "|".join(
            part
            for part in (
                f"content_length={self.content_length}" if self.content_length is not None else "",
                f"etag={self.etag}" if self.etag else "",
                f"last_modified={self.last_modified}" if self.last_modified else "",
                f"content_type={self.content_type}" if self.content_type else "",
            )
            if part
        )
        if not key:
            return None
        return sha256(key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LocalFileState:
    path: Path | None
    exists: bool
    size: int | None
    sha256: str | None
    looks_like_pdf: bool
    parseable: bool | None = None


@dataclass(frozen=True)
class DatabaseDocumentState:
    pdf_id: str
    status: str | None
    expected_chunk_count: int | None
    actual_chunk_count: int
    min_chunk_index: int | None
    max_chunk_index: int | None
    distinct_chunk_indexes: int
    page_count: int | None
    source_size: int | None
    source_sha256: str | None
    source_etag: str | None
    source_last_modified: str | None
    chunker_version: str | None = None
    embedding_model: str | None = None
    vector_dimensions: int | None = None
    contains_table_records: bool = False
    client_id: str | None = None
    patient_id: str | None = None


@dataclass(frozen=True)
class DocumentDecision:
    action: Literal[
        "VERIFIED_SKIP",
        "VERIFY_BY_SIZE_PROBE",
        "VERIFY_BY_DOWNLOAD",
        "RECHUNK_LOCAL",
        "DOWNLOAD_AND_RECHUNK",
        "OCR_REQUIRED",
        "REPAIR_DB_ONLY",
        "FAILED_RETRYABLE",
        "FAILED_PERMANENT",
    ]
    reasons: tuple[str, ...]

    @property
    def should_download(self) -> bool:
        return self.action in {"VERIFY_BY_DOWNLOAD", "DOWNLOAD_AND_RECHUNK", "RECHUNK_LOCAL"}

    @property
    def should_probe(self) -> bool:
        return self.action in {"VERIFY_BY_SIZE_PROBE", "VERIFY_BY_DOWNLOAD", "DOWNLOAD_AND_RECHUNK"}

    @property
    def should_skip(self) -> bool:
        return self.action == "VERIFIED_SKIP"


def _chunk_state_is_complete(db_state: DatabaseDocumentState) -> bool:
    if db_state.status != "loaded":
        return False
    if db_state.actual_chunk_count <= 0:
        return False
    if db_state.expected_chunk_count is not None and db_state.actual_chunk_count != db_state.expected_chunk_count:
        return False
    if db_state.distinct_chunk_indexes != db_state.actual_chunk_count:
        return False
    if db_state.min_chunk_index not in (None, 1):
        return False
    if db_state.max_chunk_index is not None and db_state.max_chunk_index != db_state.actual_chunk_count:
        return False
    if db_state.contains_table_records:
        return False
    return True


def classify_document_state(
    *,
    db_state: DatabaseDocumentState | None,
    remote_probe: RemoteProbe | None,
    local_state: LocalFileState | None,
    requested_embedding_model: str | None = None,
    requested_vector_dimensions: int | None = None,
) -> DocumentDecision:
    reasons: list[str] = []
    if db_state is None:
        if remote_probe is None:
            return DocumentDecision("VERIFY_BY_DOWNLOAD", ("no database state and no remote probe available",))
        if remote_probe.content_length is not None:
            return DocumentDecision("VERIFY_BY_DOWNLOAD", ("no database state", "remote size known but no prior load exists"))
        return DocumentDecision("DOWNLOAD_AND_RECHUNK", ("no database state", "remote size unavailable"))

    if not _chunk_state_is_complete(db_state):
        if db_state.status in {"failed", "error"}:
            return DocumentDecision("FAILED_RETRYABLE", ("database row is not complete", f"status={db_state.status!r}"))
        if db_state.contains_table_records:
            return DocumentDecision("REPAIR_DB_ONLY", ("legacy table_records contamination present",))
        if db_state.expected_chunk_count is not None and db_state.actual_chunk_count < db_state.expected_chunk_count:
            return DocumentDecision("DOWNLOAD_AND_RECHUNK", ("chunk count mismatch",))
        return DocumentDecision("VERIFY_BY_DOWNLOAD", ("database state incomplete or inconsistent",))

    if requested_embedding_model and db_state.embedding_model and db_state.embedding_model != requested_embedding_model:
        return DocumentDecision("DOWNLOAD_AND_RECHUNK", ("embedding model mismatch",))
    if requested_vector_dimensions and db_state.vector_dimensions and db_state.vector_dimensions != requested_vector_dimensions:
        return DocumentDecision("DOWNLOAD_AND_RECHUNK", ("vector dimension mismatch",))

    if local_state is not None and local_state.exists:
        if local_state.size is not None and db_state.source_size is not None and local_state.size != db_state.source_size:
            return DocumentDecision("VERIFY_BY_DOWNLOAD", ("local file size differs from DB size",))
        if local_state.looks_like_pdf is False:
            return DocumentDecision("VERIFY_BY_DOWNLOAD", ("local file does not look like a PDF",))

    if remote_probe is None:
        return DocumentDecision("VERIFY_BY_SIZE_PROBE", ("need remote probe before skip",))

    if remote_probe.content_length is None and remote_probe.fingerprint() is None:
        return DocumentDecision("VERIFY_BY_DOWNLOAD", ("remote probe inconclusive",))

    if db_state.source_size is not None and remote_probe.content_length is not None and db_state.source_size != remote_probe.content_length:
        return DocumentDecision("DOWNLOAD_AND_RECHUNK", ("remote size mismatch",))

    if db_state.source_sha256 is not None and local_state is not None and local_state.sha256 is not None and db_state.source_sha256 != local_state.sha256:
        return DocumentDecision("VERIFY_BY_DOWNLOAD", ("local hash differs from stored hash",))

    reasons.extend(
        [
            "database chunk state complete",
            "remote probe did not contradict stored size",
        ]
    )
    return DocumentDecision("VERIFIED_SKIP", tuple(reasons))



def probe_remote_pdf(url: str, *, timeout: int = 30) -> RemoteProbe:
    last_error: str | None = None
    for request in (
        Request(url, headers={"Range": "bytes=0-0"}),
        Request(url, method="HEAD"),
    ):
        try:
            with urlopen(request, timeout=timeout) as response:
                headers = response.headers
                content_length = headers.get("Content-Length")
                content_range = headers.get("Content-Range")
                total_length: int | None = int(content_length) if content_length and str(content_length).isdigit() else None
                if total_length is None and content_range and "/" in content_range:
                    total = content_range.rsplit("/", 1)[1]
                    if total.isdigit():
                        total_length = int(total)
                return RemoteProbe(
                    outcome="success",
                    content_length=total_length,
                    etag=headers.get("ETag"),
                    last_modified=headers.get("Last-Modified"),
                    content_type=headers.get("Content-Type"),
                    range_supported=request.headers.get("Range") is not None,
                    error=None,
                )
        except (HTTPError, URLError, ValueError) as exc:
            last_error = str(exc)
            continue
    return RemoteProbe(
        outcome="unsupported",
        content_length=None,
        etag=None,
        last_modified=None,
        content_type=None,
        range_supported=False,
        error=last_error,
    )
