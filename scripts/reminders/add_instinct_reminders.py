from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import error, parse, request
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests


DEFAULT_BASE_URL = "https://evh.api.instinctvet.com/"
DEFAULT_AUTH_URL = "https://partner.instinctvet.com/v1/auth/token"
DEFAULT_ORIGIN = "https://app.instinctvet.cloud"
DEFAULT_REFERER = "https://app.instinctvet.cloud/"
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReminderRow:
    source_row_number: int
    patient_id: str
    reminder_label_id: str
    remind_on: str
    notes: str
    location_id: str = "1"


def fetch_partner_token(auth_url: str, client_id: str, client_secret: str) -> str:
    body = parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    req = request.Request(
        url=auth_url,
        method="POST",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            if resp.status >= 400:
                raise RuntimeError(f"Token request failed with HTTP {resp.status}: {parsed}")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        raise RuntimeError(f"Token request failed with HTTP {exc.code}: {parsed}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Token response was not JSON.")

    token = parsed.get("access_token") or parsed.get("token") or parsed.get("jwt") or parsed.get("id_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(f"Token response missing access token field: {parsed}")
    return token


def load_rows(csv_path: Path) -> list[ReminderRow]:
    rows: list[ReminderRow] = []
    seen: set[tuple[str, str, str]] = set()

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            patient_id = (row.get("instinct_patient_id") or "").strip()
            reminder_label_id = (row.get("instinct_label_id") or "").strip()
            remind_on = (row.get("due_date") or "").strip()
            notes = (row.get("source_label") or "").strip()
            source_row_number = int((row.get("source_row_number") or "0").strip() or "0")

            if not patient_id or not reminder_label_id or not remind_on:
                continue

            dedupe_key = (patient_id, reminder_label_id, remind_on)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            rows.append(
                ReminderRow(
                    source_row_number=source_row_number,
                    patient_id=patient_id,
                    reminder_label_id=reminder_label_id,
                    remind_on=remind_on,
                    notes=notes,
                )
            )

    return rows


def build_payload(row: ReminderRow) -> dict[str, Any]:
    return {
        "operationName": "AddPatientReminder",
        "variables": {
            "params": {
                "isActive": True,
                "lastAdministeredOn": None,
                "locationId": row.location_id,
                "notes": row.notes,
                "remindOn": row.remind_on,
                "patientId": row.patient_id,
                "reminderLabelId": row.reminder_label_id,
            }
        },
        "query": (
            "mutation AddPatientReminder($params: AddPatientReminderParams!) { "
            "addPatientReminder(params: $params) { id __typename } }"
        ),
    }


def post_reminder(base_url: str, token: str, row: ReminderRow, *, dry_run: bool = False) -> dict[str, Any]:
    payload = build_payload(row)
    if dry_run:
        return {"dry_run": True, "payload": payload}

    resp = requests.post(
        base_url,
        headers={
            "accept": "*/*",
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "origin": DEFAULT_ORIGIN,
            "referer": DEFAULT_REFERER,
        },
        json=payload,
        timeout=30,
    )
    return {
        "status_code": resp.status_code,
        "ok": resp.ok,
        "response_text": resp.text,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch-add Instinct reminders from the handoff CSV.")
    parser.add_argument("--csv", type=Path, default=ROOT / "scripts" / "instinct_reminder_handoff.csv")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=os.getenv("INSTINCT_BEARER_TOKEN", ""))
    parser.add_argument("--client-id", default=os.getenv("INSTINCT_CLIENT_ID", ""))
    parser.add_argument("--client-secret", default=os.getenv("INSTINCT_CLIENT_SECRET", ""))
    parser.add_argument("--auth-url", default=DEFAULT_AUTH_URL)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    token = args.token.strip()
    if not args.dry_run and not token:
        if args.client_id and args.client_secret:
            token = fetch_partner_token(args.auth_url, args.client_id, args.client_secret)
        else:
            raise SystemExit(
                "Missing bearer token. Pass --token or set INSTINCT_BEARER_TOKEN, "
                "or pass --client-id and --client-secret to fetch one."
            )

    rows = load_rows(args.csv)
    if args.offset:
        rows = rows[args.offset :]
    if args.limit is not None:
        rows = rows[: args.limit]

    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        result = post_reminder(args.base_url, token, row, dry_run=args.dry_run)
        result["source_row_number"] = row.source_row_number
        result["patient_id"] = row.patient_id
        result["reminder_label_id"] = row.reminder_label_id
        result["remind_on"] = row.remind_on
        results.append(result)
        print(json.dumps(result, sort_keys=True))
        if index < len(rows):
            time.sleep(args.delay)

    print(f"submitted={len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
