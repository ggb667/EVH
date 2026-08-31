"""Sample Instinct patient documents and infer recurring PDF families.

This is a discovery tool, not the production ingest path:
- sample patients from the live Instinct API
- fetch their chart-file PDFs through the GraphQL `medicalHistoryVisits` flow
- classify PDFs by filename and first-page text markers
- emit a compact JSON report for family discovery

Vector loading is intentionally disabled here. The goal is to understand the
document families before writing family-specific parsers.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import re
import traceback
from datetime import datetime, timezone
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_pdf_chunker import PatientPdfSource, extract_pdf_text_pages, load_term_index
from scripts.instinct_document_state import probe_remote_pdf
from scripts.http_session import get_session


GRAPHQL_URL = "https://evh.api.instinctvet.com/"
PDF_SIZE_CUTOFF_BYTES = 8 * 1024 * 1024
HTTP_SESSION = get_session()


@dataclass(frozen=True)
class ChartFileRef:
    patient_id: str
    patient_name: str
    account_id: str | None
    chart_id: str
    filename: str
    label: str | None
    chart_type: str | None


@dataclass(frozen=True)
class PdfSizeDecision:
    include: bool
    content_length: int | None
    reason: str


def _probe_pdf_content_length(url: str, timeout: int = 20) -> int | None:
    probe = probe_remote_pdf(url, timeout=timeout)
    return probe.content_length


def _decide_pdf_size_mode(
    *,
    content_length: int | None,
    size_mode: str,
    cutoff_bytes: int,
) -> PdfSizeDecision:
    if size_mode == "everything":
        return PdfSizeDecision(include=True, content_length=content_length, reason="everything")
    if content_length is None:
        return PdfSizeDecision(include=True, content_length=None, reason="unknown_size")
    if size_mode == "small_only":
        if content_length <= cutoff_bytes:
            return PdfSizeDecision(include=True, content_length=content_length, reason="small")
        return PdfSizeDecision(include=False, content_length=content_length, reason="large")
    if size_mode == "large_only":
        if content_length > cutoff_bytes:
            return PdfSizeDecision(include=True, content_length=content_length, reason="large")
        return PdfSizeDecision(include=False, content_length=content_length, reason="small")
    raise ValueError(f"unknown size_mode: {size_mode!r}")


def _get_token() -> str:
    token = os.environ.get("TOKEN")
    if token:
        return token

    shell_cmd = (
        "source /home/ggb66/dev/creds_and_token.zsh >/dev/null 2>&1 && "
        "instinct_refresh_token >/dev/null 2>&1 && "
        'printf "%s" "$TOKEN"'
    )
    proc = subprocess.run(
        ["zsh", "-lc", shell_cmd],
        check=False,
        text=True,
        capture_output=True,
        timeout=120,
    )
    token = proc.stdout.strip()
    if token:
        os.environ["TOKEN"] = token
        return token

    client_id = os.environ.get("INSTINCT_CLIENT_ID")
    client_secret = os.environ.get("INSTINCT_CLIENT_SECRET")
    if client_id and client_secret:
        resp = HTTP_SESSION.post(
            "https://partner.instinctvet.com/v1/auth/token",
            json={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        token = str(payload.get("access_token") or payload.get("token") or payload.get("jwt") or "").strip()
        if token:
            os.environ["TOKEN"] = token
            return token

    raise RuntimeError("TOKEN is not set; source /home/ggb66/dev/creds_and_token.zsh first.")


def _graph_ql_request(query: str, variables: dict[str, Any], *, timeout: int = 60) -> dict[str, Any]:
    token = _get_token()
    resp = HTTP_SESSION.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload["data"]


def fetch_medical_history_visits(patient_id: str, *, timeout: int = 5) -> dict[str, Any]:
    query = """
query medicalHistoryVisits($patientId: ID!, $chartTypes: [ChartType]) {
  patient(id: $patientId) {
    id
    name
    pimsId
    account { id pimsCode }
    __typename
  }
  charts(patientId: $patientId, chartTypes: $chartTypes) {
    __typename
    ... on ChartFile {
      id
      filename
      label
      contentType
      type
      insertedAt
    }
    ... on ChartDocument {
      id
      label
      description
      type
      insertedAt
    }
    ... on Diagnostic {
      id
      label
      diagnosticType
      displayStatus
      insertedAt
    }
  }
}
""".strip()
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return _graph_ql_request(
                query,
                {"patientId": patient_id, "chartTypes": ["CHART_DOCUMENT", "CHART_FILE", "DIAGNOSTIC"]},
                timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= 3:
                break
    raise RuntimeError(f"medicalHistoryVisits failed for patient_id={patient_id!r} after 3 attempts: {last_error}") from last_error


def fetch_patient_chart_count(patient_id: str) -> int:
    query = """
query patientChartCount($patientId: ID!) {
  charts(patientId: $patientId, chartTypes: [CHART_DOCUMENT, CHART_FILE, DIAGNOSTIC]) {
    __typename
    ... on ChartFile { id }
    ... on ChartDocument { id }
    ... on Diagnostic { id }
  }
}
""".strip()
    data = _graph_ql_request(query, {"patientId": patient_id})
    charts = data.get("charts") or []
    return len(charts)


def create_chart_file_url(chart_id: str, inline: bool = True) -> str:
    mutation = """
mutation createChartFileUrl($id: ID!, $inline: Boolean) {
  createChartFileUrl(id: $id, inline: $inline)
}
""".strip()
    data = _graph_ql_request(mutation, {"id": chart_id, "inline": inline})
    url = data.get("createChartFileUrl")
    if not isinstance(url, str) or not url.strip():
        raise RuntimeError(f"No download URL returned for chart file id={chart_id!r}")
    return url


def classify_family(filename: str, first_page_text: str) -> str:
    haystack = f"{filename} {first_page_text}".lower()
    if "vaccine history" in haystack or "vaccinehistory" in haystack:
        return "vaccine_history"
    if "diagnoses" in haystack:
        return "diagnoses"
    if "communications" in haystack:
        return "communications"
    if "transaction history" in haystack:
        return "transaction_history"
    if "lab test history" in haystack or "labresults" in haystack:
        return "antech_lab"
    if "prescription" in haystack or "rx" in haystack:
        return "prescriptions"
    if "wellness" in haystack:
        return "wellness"
    return "other"


def _normalize_signature_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_pattern_signature(filename: str, first_page_text: str) -> str:
    filename_sig = _normalize_signature_text(Path(filename).stem)
    text_lines = [_normalize_signature_text(line) for line in first_page_text.splitlines()[:12]]
    text_sig = " ".join(line for line in text_lines if line)
    headline = " ".join(text_sig.split()[:18])
    return f"{filename_sig} || {headline}" if headline else filename_sig


def _safe_first_page_text(pdf_bytes: bytes) -> tuple[str, int]:
    pages, page_count = extract_pdf_text_pages(pdf_bytes)
    first = next((page.strip() for page in pages if page.strip()), "")
    return first, page_count


def _sample_patients(adapter: InstinctApiAdapter, limit: int, seed: int) -> list[dict[str, Any]]:
    patients = list(adapter.iter_patients())
    rng = random.Random(seed)
    rng.shuffle(patients)
    return patients[:limit]


def _chart_files_for_patient(patient: dict[str, Any], max_docs: int) -> list[ChartFileRef]:
    patient_id = str(patient.get("id") or "")
    patient_name = str(patient.get("name") or "")
    account = patient.get("account") or {}
    account_id = account.get("id")
    history = fetch_medical_history_visits(patient_id)
    charts = history.get("charts") or []

    refs: list[ChartFileRef] = []
    for chart in charts:
        if chart.get("__typename") != "ChartFile":
            continue
        chart_id = str(chart.get("id") or "")
        filename = str(chart.get("filename") or "")
        if not chart_id or not filename:
            continue
        refs.append(
            ChartFileRef(
                patient_id=patient_id,
                patient_name=patient_name,
                account_id=str(account_id) if account_id else None,
                chart_id=chart_id,
                filename=filename,
                label=str(chart.get("label") or "") or None,
                chart_type=str(chart.get("type") or "") or None,
            )
        )
        if max_docs > 0 and len(refs) >= max_docs:
            break
    return refs


def _load_checkpoint(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_checkpoint(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _write_heartbeat(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    heartbeat = {
        **payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(heartbeat, indent=2, sort_keys=True), encoding="utf-8")


def sample_document_families(
    *,
    patient_limit: int,
    max_docs_per_patient: int,
    seed: int,
    checkpoint_path: Path | None = None,
    heartbeat_path: Path | None = None,
    pdf_timeout: int = 45,
    size_mode: str = "small_only",
    size_cutoff_bytes: int = PDF_SIZE_CUTOFF_BYTES,
) -> dict[str, Any]:
    adapter = InstinctApiAdapter(
        base_url=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"),
        username=os.environ.get("INSTINCT_API_USERNAME", ""),
        password=os.environ.get("INSTINCT_API_PASSWORD", ""),
    )
    adapter.token = _get_token()

    sampled_patients = _sample_patients(adapter, patient_limit, seed)
    term_index = load_term_index()
    checkpoint = _load_checkpoint(checkpoint_path)

    family_counts: Counter[str] = Counter()
    signature_counts: Counter[str] = Counter()
    doc_rows: list[dict[str, Any]] = list(checkpoint.get("documents") or [])
    patient_rows: list[dict[str, Any]] = list(checkpoint.get("patients") or [])
    for row in doc_rows:
        family = row.get("family")
        signature = row.get("signature")
        if isinstance(family, str) and family:
            family_counts[family] += 1
        if isinstance(signature, str) and signature:
            signature_counts[signature] += 1
    seen_patient_ids = {str(row.get("patient_id") or "") for row in patient_rows if row.get("patient_id") is not None}

    try:
        for patient in sampled_patients:
            patient_id = str(patient.get("id") or "")
            if patient_id and patient_id in seen_patient_ids:
                continue
            _write_heartbeat(
                heartbeat_path,
                {
                    "phase": "patient_start",
                    "patient_id": patient_id,
                    "patient_name": patient.get("name"),
                    "processed_patients": len(patient_rows),
                    "processed_documents": len(doc_rows),
                    "sampled_patients": len(sampled_patients),
                },
            )
            try:
                chart_count = fetch_patient_chart_count(patient_id)
                chart_refs = _chart_files_for_patient(patient, max_docs_per_patient)
            except Exception as exc:
                patient_rows.append(
                    {
                        "patient_id": patient_id or patient.get("id"),
                        "patient_name": patient.get("name"),
                        "chart_count": chart_count if "chart_count" in locals() else None,
                        "status": "charts_error",
                        "error": str(exc),
                    }
                )
                _write_checkpoint(
                    checkpoint_path,
                    {
                        "sampled_patients": len(sampled_patients),
                        "patients": patient_rows,
                        "documents": doc_rows,
                        "family_counts": dict(family_counts),
                        "signature_counts": dict(signature_counts),
                        "term_index_count": len(term_index),
                        "last_error": {
                            "type": type(exc).__name__,
                            "detail": str(exc),
                        },
                    },
                )
                continue

            patient_rows.append(
                {
                    "patient_id": patient_id,
                    "patient_name": patient.get("name"),
                    "chart_count": chart_count,
                    "chart_files": len(chart_refs),
                }
            )

            for chart_ref in chart_refs:
                try:
                    _write_heartbeat(
                        heartbeat_path,
                        {
                            "phase": "chart_fetch",
                            "patient_id": patient_id,
                            "patient_name": patient.get("name"),
                            "chart_id": chart_ref.chart_id,
                            "chart_filename": chart_ref.filename,
                            "processed_patients": len(patient_rows),
                            "processed_documents": len(doc_rows),
                            "sampled_patients": len(sampled_patients),
                        },
                    )
                    pdf_url = create_chart_file_url(chart_ref.chart_id, inline=True)
                    content_length = _probe_pdf_content_length(pdf_url, timeout=20)
                    decision = _decide_pdf_size_mode(
                        content_length=content_length,
                        size_mode=size_mode,
                        cutoff_bytes=size_cutoff_bytes,
                    )
                    if not decision.include:
                        doc_rows.append(
                            {
                                "patient_id": chart_ref.patient_id,
                                "patient_name": chart_ref.patient_name,
                                "chart_id": chart_ref.chart_id,
                                "filename": chart_ref.filename,
                                "label": chart_ref.label,
                                "status": "skipped_size",
                                "size_mode": size_mode,
                                "content_length": content_length,
                                "reason": decision.reason,
                            }
                        )
                        continue

                    pdf_bytes = requests.get(pdf_url, timeout=pdf_timeout).content
                    first_page_text, page_count = _safe_first_page_text(pdf_bytes)
                    family = classify_family(chart_ref.filename, first_page_text)
                    signature = build_pattern_signature(chart_ref.filename, first_page_text)
                    family_counts[family] += 1
                    signature_counts[signature] += 1
                    doc_rows.append(
                        {
                            "patient_id": chart_ref.patient_id,
                            "patient_name": chart_ref.patient_name,
                            "chart_id": chart_ref.chart_id,
                            "filename": chart_ref.filename,
                            "label": chart_ref.label,
                            "page_count": page_count,
                            "family": family,
                            "signature": signature,
                            "content_length": content_length,
                            "first_page_text": first_page_text[:500],
                        }
                    )
                except Exception as exc:
                    doc_rows.append(
                        {
                            "patient_id": chart_ref.patient_id,
                            "patient_name": chart_ref.patient_name,
                            "chart_id": chart_ref.chart_id,
                            "filename": chart_ref.filename,
                            "label": chart_ref.label,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )

            seen_patient_ids.add(patient_id)
            _write_checkpoint(
                checkpoint_path,
                {
                    "sampled_patients": len(sampled_patients),
                    "patients": patient_rows,
                    "documents": doc_rows,
                    "family_counts": dict(family_counts),
                    "signature_counts": dict(signature_counts),
                    "term_index_count": len(term_index),
                },
            )
            _write_heartbeat(
                heartbeat_path,
                {
                    "phase": "patient_complete",
                    "patient_id": patient_id,
                    "patient_name": patient.get("name"),
                    "processed_patients": len(patient_rows),
                    "processed_documents": len(doc_rows),
                    "sampled_patients": len(sampled_patients),
                    "family_counts": dict(family_counts),
                },
            )
    except Exception as exc:
        _write_checkpoint(
            checkpoint_path,
            {
                "sampled_patients": len(sampled_patients),
                "patients": patient_rows,
                "documents": doc_rows,
                "family_counts": dict(family_counts),
                "signature_counts": dict(signature_counts),
                "term_index_count": len(term_index),
                "last_error": {
                    "type": type(exc).__name__,
                    "detail": str(exc),
                    "traceback": traceback.format_exc(),
                },
            },
        )
        _write_heartbeat(
            heartbeat_path,
            {
                "phase": "failed",
                "error_type": type(exc).__name__,
                "error_detail": str(exc),
                "processed_patients": len(patient_rows),
                "processed_documents": len(doc_rows),
                "sampled_patients": len(sampled_patients),
            },
        )
        raise

    return {
        "sampled_patients": len(sampled_patients),
        "patients": patient_rows,
        "documents": doc_rows,
        "family_counts": dict(sorted(family_counts.items(), key=lambda item: (-item[1], item[0]))),
        "signature_counts": dict(sorted(signature_counts.items(), key=lambda item: (-item[1], item[0]))),
        "term_index_count": len(term_index),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample Instinct patients and infer PDF document families.")
    parser.add_argument("--patient-limit", type=int, default=200)
    parser.add_argument("--max-docs-per-patient", type=int, default=0, help="0 means fetch all chart files for each sampled patient.")
    parser.add_argument("--seed", type=int, default=11525)
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--checkpoint", type=Path, default=None, help="Optional checkpoint path for crash-resume state.")
    parser.add_argument("--heartbeat", type=Path, default=None, help="Optional heartbeat file path.")
    parser.add_argument("--pdf-timeout", type=int, default=45, help="Timeout in seconds for PDF downloads.")
    parser.add_argument(
        "--size-mode",
        choices=("small_only", "large_only", "everything"),
        default="small_only",
        help="PDF size filter mode; small_only skips PDFs larger than the cutoff.",
    )
    parser.add_argument("--size-cutoff-mb", type=int, default=8, help="Cutoff size in MB for small/large filtering.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = sample_document_families(
        patient_limit=args.patient_limit,
        max_docs_per_patient=args.max_docs_per_patient,
        seed=args.seed,
        checkpoint_path=args.checkpoint or args.output,
        heartbeat_path=args.heartbeat,
        pdf_timeout=args.pdf_timeout,
        size_mode=args.size_mode,
        size_cutoff_bytes=args.size_cutoff_mb * 1024 * 1024,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
