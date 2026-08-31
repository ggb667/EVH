from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import requests

from scripts.evh_reminder_importer import InstinctApiAdapter


def _n(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _head_content_length(url: str, timeout: int = 30) -> tuple[int | None, str | None]:
    req = Request(url, method="HEAD")
    try:
        with urlopen(req, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            content_type = response.headers.get("Content-Type")
            return (int(content_length) if content_length and str(content_length).isdigit() else None, _n(content_type))
    except (HTTPError, URLError, ValueError):
        return None, None


def _graphql(session: requests.Session, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    resp = session.post("https://evh.api.instinctvet.com/", json={"query": query, "variables": variables}, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload["data"]


def _chart_files(session: requests.Session, patient_id: str) -> list[dict[str, Any]]:
    query = """
query medicalHistoryVisits($patientId: ID!, $chartTypes: [ChartType]) {
  charts(patientId: $patientId, chartTypes: $chartTypes) {
    __typename
    ... on ChartFile { id filename label type }
  }
}
""".strip()
    return _graphql(session, query, {"patientId": patient_id, "chartTypes": ["CHART_DOCUMENT", "CHART_FILE", "DIAGNOSTIC"]}).get("charts") or []


def _chart_url(session: requests.Session, chart_id: str) -> str:
    mutation = """
mutation createChartFileUrl($id: ID!, $inline: Boolean) {
  createChartFileUrl(id: $id, inline: $inline)
}
""".strip()
    url = _graphql(session, mutation, {"id": chart_id, "inline": True}).get("createChartFileUrl")
    if not isinstance(url, str) or not url.strip():
        raise RuntimeError(f"missing chart url for {chart_id}")
    return url


def _largest_gap_threshold(sizes: list[int]) -> int | None:
    unique = sorted(set(sizes))
    if len(unique) < 2:
        return None
    gaps = [(b - a, a, b) for a, b in zip(unique, unique[1:])]
    _, left, _ = max(gaps, key=lambda item: item[0])
    return left


def run(patient_checkpoint: Path, output: Path) -> dict[str, Any]:
    patients = json.loads(patient_checkpoint.read_text(encoding="utf-8"))
    if not isinstance(patients, list):
        raise ValueError("patient checkpoint must be a JSON array")

    base_url = os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com")
    username = os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME")
    password = os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD")
    if not username or not password:
        raise SystemExit("Missing Instinct credentials.")

    adapter = InstinctApiAdapter(base_url, username, password)
    adapter.token = adapter.authenticate()

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {adapter.token}", "Content-Type": "application/json"})

    rows: list[dict[str, Any]] = []
    for idx, patient in enumerate(patients, start=1):
        patient_id = _n(patient.get("patient_id"))
        if not patient_id:
            continue
        charts = _chart_files(session, patient_id)
        for chart in charts:
            if not isinstance(chart, dict) or chart.get("__typename") != "ChartFile":
                continue
            chart_id = _n(chart.get("id"))
            filename = _n(chart.get("filename"))
            if not chart_id or not filename:
                continue
            url = _chart_url(session, chart_id)
            content_length, content_type = _head_content_length(url)
            rows.append(
                {
                    "client_id": _n(patient.get("client_id")),
                    "client_name": _n(patient.get("client_name")),
                    "patient_id": patient_id,
                    "patient_name": _n(patient.get("patient_name")),
                    "chart_id": chart_id,
                    "filename": filename,
                    "content_length": content_length,
                    "content_type": content_type,
                }
            )
        if idx % 25 == 0:
            print(f"progress {idx} patients rows={len(rows)}", flush=True)

    known_sizes = [row["content_length"] for row in rows if isinstance(row.get("content_length"), int)]
    threshold = _largest_gap_threshold(known_sizes)
    for row in rows:
        cl = row.get("content_length")
        if isinstance(cl, int):
            row["size_bin"] = "huge_image_only" if threshold is not None and cl <= threshold else "real_text_pdf"
        else:
            row["size_bin"] = None

    output.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "rows": len(rows),
        "known_sizes": len(known_sizes),
        "known_total_bytes": sum(known_sizes),
        "known_total_mib": round(sum(known_sizes) / 1024 / 1024, 2),
        "threshold": threshold,
        "output": str(output),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Metadata-only PDF size pass from saved Instinct patients")
    parser.add_argument("--patients", default="/home/ggb66/dev/EVH/pony/worktrees/rd/patient_inventory.json")
    parser.add_argument("--output", default="/home/ggb66/dev/EVH/pony/worktrees/rd/pdf_size_table.json")
    args = parser.parse_args()
    run(Path(args.patients), Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
