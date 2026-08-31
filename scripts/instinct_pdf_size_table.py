"""Build a metadata-only size table for Instinct PDFs.

This script walks live Instinct clients -> patients -> chart files and records:
- client and patient identities
- chart/file identifiers
- HEAD-reported PDF content lengths
- a coarse size binning using the largest gap between sorted sizes

It does not download PDF bodies.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_document_state import probe_remote_pdf


@dataclass(frozen=True)
class PdfSizeRow:
    client_id: str
    client_name: str
    patient_id: str
    patient_name: str
    chart_id: str
    filename: str
    content_length: int | None
    content_type: str | None
    size_bin: str | None = None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _head(url: str, timeout: int = 30) -> tuple[int | None, str | None]:
    probe = probe_remote_pdf(url, timeout=timeout)
    return probe.content_length, _normalize_text(probe.content_type)


def _fetch_chart_url(adapter: InstinctApiAdapter, chart_id: str) -> str:
    query = """
mutation createChartFileUrl($id: ID!, $inline: Boolean) {
  createChartFileUrl(id: $id, inline: $inline)
}
""".strip()
    token = adapter.token or adapter.authenticate()
    adapter.token = token
    # Reuse the adapter's REST auth context by making the GraphQL request directly.
    import requests

    resp = requests.post(
        "https://evh.api.instinctvet.com/",
        json={"query": query, "variables": {"id": chart_id, "inline": True}},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    url = payload.get("data", {}).get("createChartFileUrl")
    if not isinstance(url, str) or not url.strip():
        raise RuntimeError(f"missing chart url for {chart_id}")
    return url


def _iter_accounts(adapter: InstinctApiAdapter):
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["pageCursor"] = cursor
        payload = adapter._get("/v1/accounts", params)
        for account in payload.get("data") or []:
            yield account
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        cursor = _normalize_text(metadata.get("after")) if isinstance(metadata, dict) else None
        if not cursor:
            break


def _iter_patients_for_account(adapter: InstinctApiAdapter, account_id: str):
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100, "accountId": account_id}
        if cursor:
            params["pageCursor"] = cursor
        payload = adapter._get("/v1/patients", params)
        for patient in payload.get("data") or []:
            yield patient
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        cursor = _normalize_text(metadata.get("after")) if isinstance(metadata, dict) else None
        if not cursor:
            break


def _chart_files_for_patient(adapter: InstinctApiAdapter, patient_id: str):
    query = """
query medicalHistoryVisits($patientId: ID!, $chartTypes: [ChartType]) {
  charts(patientId: $patientId, chartTypes: $chartTypes) {
    __typename
    ... on ChartFile { id filename label type }
  }
}
""".strip()
    import requests

    resp = requests.post(
        "https://evh.api.instinctvet.com/",
        json={"query": query, "variables": {"patientId": patient_id, "chartTypes": ["CHART_DOCUMENT", "CHART_FILE", "DIAGNOSTIC"]}},
        headers={"Authorization": f"Bearer {adapter.token}", "Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload.get("data", {}).get("charts") or []


def largest_gap_bin(sizes: list[int]) -> dict[int, str]:
    unique = sorted(set(sizes))
    if len(unique) < 2:
        return {size: "all" for size in unique}
    gaps = [(b - a, a, b) for a, b in zip(unique, unique[1:])]
    gap, left, right = max(gaps, key=lambda item: item[0])
    if gap <= 0:
        return {size: "all" for size in unique}
    bins: dict[int, str] = {}
    for size in unique:
        bins[size] = "huge_image_only" if size <= left else "real_text_pdf"
    return bins


def build_size_table(adapter: InstinctApiAdapter) -> list[PdfSizeRow]:
    rows: list[PdfSizeRow] = []
    for account in _iter_accounts(adapter):
        client_id = _normalize_text(account.get("id")) or ""
        client_name = _normalize_text(account.get("name") or account.get("displayName") or account.get("pimsCode")) or client_id
        if not client_id:
            continue
        for patient in _iter_patients_for_account(adapter, client_id):
            patient_id = _normalize_text(patient.get("id")) or ""
            patient_name = _normalize_text(patient.get("name") or patient.get("patientName")) or patient_id
            if not patient_id:
                continue
            charts = _chart_files_for_patient(adapter, patient_id)
            for chart in charts:
                if not isinstance(chart, dict) or chart.get("__typename") != "ChartFile":
                    continue
                chart_id = _normalize_text(chart.get("id")) or ""
                filename = _normalize_text(chart.get("filename")) or ""
                if not chart_id or not filename:
                    continue
                url = _fetch_chart_url(adapter, chart_id)
                content_length, content_type = _head(url)
                rows.append(
                    PdfSizeRow(
                        client_id=client_id,
                        client_name=client_name,
                        patient_id=patient_id,
                        patient_name=patient_name,
                        chart_id=chart_id,
                        filename=filename,
                        content_length=content_length,
                        content_type=content_type,
                    )
                )
    sizes = [row.content_length for row in rows if row.content_length is not None]
    bins = largest_gap_bin(sizes)
    return [PdfSizeRow(**{**asdict(row), "size_bin": bins.get(row.content_length) if row.content_length is not None else None}) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a live metadata-only Instinct PDF size table")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--output", default="pdf_size_table.json")
    args = parser.parse_args()

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials.")

    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.token = adapter.authenticate()
    rows = build_size_table(adapter)
    Path(args.output).write_text(json.dumps([asdict(row) for row in rows], indent=2, sort_keys=True), encoding="utf-8")

    known_sizes = [row.content_length for row in rows if row.content_length is not None]
    print(json.dumps({
        "rows": len(rows),
        "known_sizes": len(known_sizes),
        "known_total_bytes": sum(known_sizes),
        "known_total_mib": round(sum(known_sizes) / 1024 / 1024, 2),
        "output": args.output,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
