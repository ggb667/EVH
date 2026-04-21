"""Smoke-test Instinct API connectivity and patient payloads against a test account.

Usage examples:

# Discover account/alert/reminder IDs first
python scripts/instinct_test_account_check.py \
  --base-url "https://api.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --discover-only

# Preflight only (recommended first step)
python scripts/instinct_test_account_check.py \
  --base-url "https://api.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<test-account-uuid>" \
  --default-alert-id 101 \
  --default-reminder-ids 201,202 \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261"

# Preflight + create a test patient + create an initial visit
python scripts/instinct_test_account_check.py \
  --base-url "https://api.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<test-account-uuid>" \
  --default-alert-id 101 \
  --default-reminder-ids 201,202 \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261" \
  --create-patient \
  --create-initial-visit
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from instinct_import_payload_builder import ImportDefaults, PatientPayloadBuilder


@dataclass(frozen=True)
class InstinctClient:
    base_url: str
    auth_header: str

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | list | str | None]:
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": self.auth_header,
        }

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(
            url=f"{self.base_url.rstrip('/')}{path}",
            method=method,
            data=data,
            headers=headers,
        )

        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                parsed = _parse_json_or_text(raw)
                return resp.status, parsed
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            parsed = _parse_json_or_text(raw)
            return exc.code, parsed

    def fetch_account(self, account_id: str) -> tuple[int, dict | list | str | None]:
        return self._request("GET", f"/v1/accounts/{account_id}")

    def fetch_accounts(self) -> tuple[int, dict | list | str | None]:
        return self._request("GET", "/v1/accounts")

    def fetch_alerts(self) -> tuple[int, dict | list | str | None]:
        return self._request("GET", "/v1/alerts")

    def fetch_reminders(
        self,
        limit: int | None = None,
        page_cursor: str | None = "",
        page_direction: str | None = "after",
    ) -> tuple[int, dict | list | str | None]:
        query: list[tuple[str, str]] = []
        if limit is not None:
            query.append(("limit", str(limit)))
        if page_cursor is not None:
            query.append(("pageCursor", page_cursor))
        if page_direction:
            query.append(("pageDirection", page_direction))

        path = "/v1/reminders"
        if query:
            path = f"{path}?{parse.urlencode(query)}"
        return self._request("GET", path)

    def create_patient(self, payload: dict) -> tuple[int, dict | list | str | None]:
        return self._request("POST", "/v1/patients", payload)

    def create_visit(self, path: str, payload: dict) -> tuple[int, dict | list | str | None]:
        return self._request("POST", path, payload)


def _parse_json_or_text(raw: str) -> dict | list | str | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _parse_ids(values: str) -> tuple[int, ...]:
    if not values.strip():
        return tuple()
    return tuple(int(v.strip()) for v in values.split(",") if v.strip())


def _build_test_patient(
    account_id: str,
    patient_name: str,
    breed_id: int,
    species_id: str,
    sex_id: str,
    pms_id: str | None,
) -> dict[str, str | int]:
    return {
        "accountId": account_id,
        "breedId": breed_id,
        "name": patient_name,
        "speciesId": species_id,
        "sexId": sex_id,
        **({"pimsCode": pms_id} if pms_id else {}),
    }


def _build_initial_visit(
    account_id: str,
    patient_id: str,
    visit_reason: str,
    visit_type_id: int | None,
) -> dict[str, str | int]:
    payload: dict[str, str | int] = {
        "accountId": account_id,
        "patientId": patient_id,
        "notes": visit_reason,
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }
    if visit_type_id is not None:
        payload["visitTypeId"] = visit_type_id
    return payload


def _extract_object_id(body: dict | list | str | None) -> str | None:
    if not isinstance(body, dict):
        return None

    for key in ("id", "patientId", "uuid"):
        value = body.get(key)
        if isinstance(value, (str, int)):
            return str(value)

    for container_key in ("data", "result", "patient"):
        inner = body.get(container_key)
        if isinstance(inner, dict):
            for key in ("id", "patientId", "uuid"):
                value = inner.get(key)
                if isinstance(value, (str, int)):
                    return str(value)
    return None


def _extract_rows(body: dict | list | str | None) -> list[dict]:
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    if isinstance(body, dict):
        for key in ("data", "items", "results", "accounts", "alerts", "reminders"):
            value = body.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _print_lookup_table(label: str, body: dict | list | str | None) -> None:
    rows = _extract_rows(body)
    if not rows:
        print(f"{label}: response did not include a list payload; raw body follows.")
        print(json.dumps(body, indent=2, default=str))
        return

    print(f"{label}:")
    for row in rows:
        row_id = row.get("id") or row.get("uuid") or row.get("accountId") or row.get("patientId")
        row_name = row.get("name") or row.get("displayName") or row.get("title")
        print(f"  - id={row_id} name={row_name}")


def _fetch_partner_token(auth_url: str, client_id: str, client_secret: str) -> str:
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
            parsed = _parse_json_or_text(raw)
            if resp.status >= 400:
                raise RuntimeError(f"Token request failed with HTTP {resp.status}: {parsed}")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        parsed = _parse_json_or_text(raw)
        raise RuntimeError(f"Token request failed with HTTP {exc.code}: {parsed}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Token response was not JSON.")

    token = (
        parsed.get("access_token")
        or parsed.get("token")
        or parsed.get("jwt")
        or parsed.get("id_token")
    )
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(f"Token response missing access token field: {parsed}")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Instinct test account + optional patient/visit create")
    parser.add_argument("--base-url", required=True, help="Instinct API base URL (e.g. https://api.instinctvet.com)")
    parser.add_argument("--api-key", help="Instinct Partner API key/token (Bearer auth)")
    parser.add_argument("--username", help="Instinct username (for Basic auth)")
    parser.add_argument("--password", help="Instinct password (for Basic auth)")
    parser.add_argument("--client-id", help="OAuth client_id for POST /v1/auth/token")
    parser.add_argument("--client-secret", help="OAuth client_secret for POST /v1/auth/token")
    parser.add_argument(
        "--auth-url",
        default="https://partner.instinctvet.com/v1/auth/token",
        help="Token endpoint for client credentials flow",
    )
    parser.add_argument("--account-id", help="Test account UUID")
    parser.add_argument("--default-alert-id", type=int, help="Default alert ID to attach")
    parser.add_argument("--patient-name", default="bob TEST", help="Patient name for create test (default: bob TEST)")
    parser.add_argument("--patient-pms-id", default="FE261", help="Patient PMS code / pimsCode (default: FE261)")
    parser.add_argument("--breed-id", default=12, type=int, help="Breed ID to use for test patient (default: 12)")
    parser.add_argument("--species-id", default="canine", help="Species ID to use for test patient (default: canine)")
    parser.add_argument("--sex-id", default="unknown", help="Sex ID to use for test patient (default: unknown)")
    parser.add_argument(
        "--default-reminder-ids",
        default="",
        help="Comma-separated reminder IDs to attach (e.g. 201,202,203)",
    )
    parser.add_argument(
        "--create-patient",
        action="store_true",
        help="If set, performs POST /v1/patients with a generated test patient payload",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Only list accounts/alerts/reminders to look up IDs, then exit.",
    )
    parser.add_argument(
        "--reminders-limit",
        type=int,
        default=10,
        help="Limit used for GET /v1/reminders during discovery (default: 10).",
    )
    parser.add_argument(
        "--reminders-page-cursor",
        default="",
        help="Optional pageCursor used for GET /v1/reminders during discovery.",
    )
    parser.add_argument(
        "--reminders-page-direction",
        choices=("after", "before"),
        default="after",
        help="pageDirection used for GET /v1/reminders during discovery (default: after).",
    )
    parser.add_argument(
        "--create-initial-visit",
        action="store_true",
        help="After patient create, attempt POST to create an initial visit for the patient.",
    )
    parser.add_argument(
        "--visit-path",
        default="/v1/visits",
        help="Visit create endpoint path used with --create-initial-visit (default: /v1/visits).",
    )
    parser.add_argument(
        "--visit-type-id",
        type=int,
        help="Optional visit type ID to include in initial visit payload.",
    )
    parser.add_argument(
        "--visit-reason",
        default="Initial import visit for patient setup",
        help="Visit note/reason to include for --create-initial-visit.",
    )
    args = parser.parse_args()

    has_api_key = bool(args.api_key)
    has_basic = bool(args.username or args.password)
    has_client_credentials = bool(args.client_id or args.client_secret)

    if has_basic and not (args.username and args.password):
        parser.error("For Basic auth provide both --username and --password.")
    if has_client_credentials and not (args.client_id and args.client_secret):
        parser.error("For token auth provide both --client-id and --client-secret.")

    enabled_auth_modes = sum((has_api_key, bool(args.username and args.password), bool(args.client_id and args.client_secret)))
    if enabled_auth_modes == 0:
        parser.error(
            "Choose one auth mode: --api-key OR --username/--password OR --client-id/--client-secret."
        )
    if enabled_auth_modes > 1:
        parser.error(
            "Choose exactly one auth mode: --api-key OR --username/--password OR --client-id/--client-secret."
        )

    if not args.discover_only and not args.account_id:
        parser.error("Provide --account-id unless running with --discover-only.")
    if not args.discover_only and args.default_alert_id is None:
        parser.error("Provide --default-alert-id unless running with --discover-only.")
    if args.create_initial_visit and not args.create_patient:
        parser.error("--create-initial-visit requires --create-patient.")

    if args.api_key:
        auth_header = f"Bearer {args.api_key}"
    elif args.username and args.password:
        encoded = base64.b64encode(f"{args.username}:{args.password}".encode("utf-8")).decode("ascii")
        auth_header = f"Basic {encoded}"
    else:
        print("Fetching OAuth token...")
        token = _fetch_partner_token(args.auth_url, args.client_id, args.client_secret)
        auth_header = f"Bearer {token}"

    client = InstinctClient(base_url=args.base_url, auth_header=auth_header)

    print("== Lookup checks ==")
    lookup_calls = (
        ("Accounts", client.fetch_accounts),
        ("Alerts", client.fetch_alerts),
        (
            "Reminders",
            lambda: client.fetch_reminders(
                limit=args.reminders_limit,
                page_cursor=args.reminders_page_cursor,
                page_direction=args.reminders_page_direction,
            ),
        ),
    )
    for label, fn in lookup_calls:
        status, body = fn()
        print(f"{label}: HTTP {status}")
        if status >= 400:
            print(json.dumps(body, indent=2, default=str))
            return 1
        _print_lookup_table(label, body)

    if args.discover_only:
        print("\nDiscovery complete. Re-run with --account-id and --default-alert-id once IDs are confirmed.")
        return 0

    defaults = ImportDefaults(
        default_alert_id=args.default_alert_id,
        default_reminder_ids=_parse_ids(args.default_reminder_ids),
    )
    builder = PatientPayloadBuilder(defaults)

    status, body = client.fetch_account(args.account_id)
    print(f"\nAccount ({args.account_id}): HTTP {status}")
    if status >= 400:
        print(json.dumps(body, indent=2, default=str))
        return 1

    sample_payload = builder.build(
        _build_test_patient(
            account_id=args.account_id,
            patient_name=args.patient_name,
            breed_id=args.breed_id,
            species_id=args.species_id,
            sex_id=args.sex_id,
            pms_id=args.patient_pms_id,
        )
    )
    print("\nGenerated payload:")
    print(json.dumps(sample_payload, indent=2))

    if not args.create_patient:
        print("\nDry run complete. Re-run with --create-patient to actually create the test patient.")
        return 0

    status, body = client.create_patient(sample_payload)
    print(f"\nCreate patient: HTTP {status}")
    print(json.dumps(body, indent=2, default=str))
    if status >= 400:
        return 1

    if not args.create_initial_visit:
        return 0

    patient_id = _extract_object_id(body)
    if not patient_id:
        print("\nUnable to determine patient ID from create response; skipping initial visit create.")
        return 1

    visit_payload = _build_initial_visit(
        account_id=args.account_id,
        patient_id=patient_id,
        visit_reason=args.visit_reason,
        visit_type_id=args.visit_type_id,
    )
    visit_status, visit_body = client.create_visit(args.visit_path, visit_payload)
    print(f"\nCreate initial visit ({args.visit_path}): HTTP {visit_status}")
    print(json.dumps(visit_body, indent=2, default=str))
    return 0 if visit_status < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
