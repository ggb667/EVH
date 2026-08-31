"""Inventory Instinct clients and save a resumable checkpoint.

This is the first step of the full PDF corpus walk:
- page through all Instinct clients/accounts
- normalize them into a compact inventory
- optionally save the inventory to disk for later patient/PDF traversal

No PDF bodies are downloaded here.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.evh_reminder_importer import InstinctApiAdapter


@dataclass(frozen=True)
class ClientInventoryEntry:
    client_id: str
    client_name: str
    pims_code: str | None
    pims_id: str | None
    phone_no: str | None
    email: str | None
    raw_id: str | None = None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_primary_contact(account: dict[str, Any]) -> dict[str, Any]:
    primary = account.get("primaryContact")
    return primary if isinstance(primary, dict) else {}


def _extract_phone(contact: dict[str, Any]) -> str | None:
    details = contact.get("communicationDetails")
    if not isinstance(details, list):
        return None
    for item in details:
        if not isinstance(item, dict):
            continue
        kind = _normalize_text(item.get("type") or item.get("communicationType"))
        value = _normalize_text(item.get("value") or item.get("text") or item.get("address"))
        if kind and kind.lower() in {"phone", "mobile", "home", "work", "cell"} and value:
            return value
        if value and not kind:
            return value
    return None


def _extract_email(contact: dict[str, Any]) -> str | None:
    details = contact.get("communicationDetails")
    if not isinstance(details, list):
        return None
    for item in details:
        if not isinstance(item, dict):
            continue
        kind = _normalize_text(item.get("type") or item.get("communicationType"))
        value = _normalize_text(item.get("value") or item.get("text") or item.get("address"))
        if kind and kind.lower() == "email" and value:
            return value
    return None


def _display_name(account: dict[str, Any]) -> str:
    primary = _extract_primary_contact(account)
    parts = [
        _normalize_text(primary.get("nameFirst")),
        _normalize_text(primary.get("nameMiddle")),
        _normalize_text(primary.get("nameLast")),
    ]
    contact_name = " ".join(part for part in parts if part)
    if contact_name:
        return contact_name
    for key in ("name", "displayName", "accountName", "businessName"):
        value = _normalize_text(account.get(key))
        if value:
            return value
    return str(account.get("id") or "").strip() or "unknown-client"


def inventory_clients(adapter: InstinctApiAdapter) -> list[ClientInventoryEntry]:
    entries: list[ClientInventoryEntry] = []
    seen_ids: set[str] = set()

    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["pageCursor"] = cursor

        payload = adapter._get("/v1/accounts", params)
        accounts = payload.get("accounts") or payload.get("data") or payload.get("items") or payload.get("results") or []
        if not isinstance(accounts, list):
            accounts = []

        for account in accounts:
            if not isinstance(account, dict):
                continue
            raw_id = _normalize_text(account.get("id"))
            if raw_id and raw_id in seen_ids:
                continue
            if raw_id:
                seen_ids.add(raw_id)

            primary = _extract_primary_contact(account)
            entries.append(
                ClientInventoryEntry(
                    client_id=raw_id or "",
                    client_name=_display_name(account),
                    pims_code=_normalize_text(account.get("pimsCode") or account.get("pims_code")),
                    pims_id=_normalize_text(account.get("pimsId") or account.get("pims_id")),
                    phone_no=_extract_phone(primary),
                    email=_extract_email(primary),
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


def save_inventory(entries: Iterable[ClientInventoryEntry], path: Path) -> None:
    payload = [asdict(entry) for entry in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_inventory(path: Path) -> list[ClientInventoryEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("client inventory must be a JSON array")
    entries: list[ClientInventoryEntry] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        entries.append(
            ClientInventoryEntry(
                client_id=str(item.get("client_id") or ""),
                client_name=str(item.get("client_name") or ""),
                pims_code=_normalize_text(item.get("pims_code")),
                pims_id=_normalize_text(item.get("pims_id")),
                phone_no=_normalize_text(item.get("phone_no")),
                email=_normalize_text(item.get("email")),
                raw_id=_normalize_text(item.get("raw_id")),
            )
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory Instinct clients/accounts and save a checkpoint")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--username", default=os.environ.get("INSTINCT_CLIENT_ID") or os.environ.get("INSTINCT_API_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("INSTINCT_CLIENT_SECRET") or os.environ.get("INSTINCT_API_PASSWORD"))
    parser.add_argument("--output", default="client_inventory.json", help="Output JSON path for the saved client inventory")
    args = parser.parse_args()

    if not args.username or not args.password:
        raise SystemExit("Missing Instinct credentials: provide --username/--password or set INSTINCT_CLIENT_ID/SECRET.")

    adapter = InstinctApiAdapter(args.base_url, args.username, args.password)
    adapter.token = adapter.authenticate()

    entries = inventory_clients(adapter)
    save_inventory(entries, Path(args.output))

    print(json.dumps({"client_count": len(entries), "output": args.output}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
