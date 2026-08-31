"""Inventory Instinct patients for a saved client checkpoint.

Reads a client inventory JSON file and walks each client to collect patients.
This stays metadata-only: no PDF bodies are downloaded here.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.evh_reminder_importer import InstinctApiAdapter
from scripts.instinct_client_inventory import ClientInventoryEntry, load_inventory as load_client_inventory


@dataclass(frozen=True)
class PatientInventoryEntry:
    client_id: str
    client_name: str
    patient_id: str
    patient_name: str
    pims_code: str | None
    species: str | None
    breed: str | None
    sex: str | None
    raw_id: str | None = None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_clients(path: Path) -> list[ClientInventoryEntry]:
    return load_client_inventory(path)


def inventory_patients(adapter: InstinctApiAdapter, clients: Iterable[ClientInventoryEntry]) -> list[PatientInventoryEntry]:
    entries: list[PatientInventoryEntry] = []
    seen_ids: set[str] = set()

    for client in clients:
        if not client.client_id:
            continue
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100, "accountId": client.client_id}
            if cursor:
                params["pageCursor"] = cursor
            payload = adapter._get("/v1/patients", params)
            patients = payload.get("patients") or payload.get("data") or payload.get("items") or payload.get("results") or []
            if not isinstance(patients, list):
                patients = []

            for patient in patients:
                if not isinstance(patient, dict):
                    continue
                raw_id = _normalize_text(patient.get("id"))
                if raw_id and raw_id in seen_ids:
                    continue
                if raw_id:
                    seen_ids.add(raw_id)
                entries.append(
                    PatientInventoryEntry(
                        client_id=client.client_id,
                        client_name=client.client_name,
                        patient_id=raw_id or "",
                        patient_name=_normalize_text(patient.get("name") or patient.get("patientName")) or "",
                        pims_code=_normalize_text(patient.get("pimsCode") or patient.get("pims_code")),
                        species=_normalize_text(patient.get("species")),
                        breed=_normalize_text(patient.get("breed")),
                        sex=_normalize_text(patient.get("sex")),
                        raw_id=raw_id,
                    )
                )

            metadata = payload.get("metadata") if isinstance(payload, dict) else None
            cursor = None
            if isinstance(metadata, dict):
                cursor = _normalize_text(metadata.get("after")) or None
            if not cursor:
                break

    return entries


def save_inventory(entries: Iterable[PatientInventoryEntry], path: Path) -> None:
    payload = [asdict(entry) for entry in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory Instinct patients from a saved client checkpoint")
    parser.add_argument("--clients", required=True, help="Path to a client inventory JSON file")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--output", default="patient_inventory.json", help="Output JSON path for the saved patient inventory")
    args = parser.parse_args()

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials: provide --username/--password or set INSTINCT_CLIENT_ID/SECRET.")

    clients = _load_clients(Path(args.clients))
    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.token = adapter.authenticate()

    entries = inventory_patients(adapter, clients)
    save_inventory(entries, Path(args.output))

    print(json.dumps({"patient_count": len(entries), "client_count": len(clients), "output": args.output}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
