"""Smoke-test Instinct API connectivity and patient payloads against a test account.

Usage examples:

# Preflight only (recommended first step)
python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --username "$INSTINCT_USERNAME" \
  --password "$INSTINCT_PASSWORD" \
  --account-id "<test-account-uuid>" \
  --default-alert-id 101 \
  --default-reminder-ids 201,202 \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261"

# Preflight + create a test patient
python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --username "$INSTINCT_USERNAME" \
  --password "$INSTINCT_PASSWORD" \
  --account-id "<test-account-uuid>" \
  --default-alert-id 101 \
  --default-reminder-ids 201,202 \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261" \
  --create-patient
"""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from collections.abc import Sequence
from urllib import error, parse, request

try:
    from scripts.instinct_import_payload_builder import ImportDefaults, PatientPayloadBuilder
except ImportError:  # pragma: no cover - direct script execution path
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

    def fetch_alerts(self) -> tuple[int, dict | list | str | None]:
        return self._request("GET", "/v1/alerts")

    def fetch_reminders(self) -> tuple[int, dict | list | str | None]:
        return self._request("GET", "/v1/reminders")

    def fetch_appointments(self) -> tuple[int, dict | list | str | None]:
        return self._request("GET", "/v1/appointments", {"limit": 1, "pageDirection": "after"})

    def fetch_appointment_types(self) -> tuple[int, dict | list | str | None]:
        return self._request("GET", "/v1/appointment-types", {"limit": 1, "pageDirection": "after"})

    def create_patient(self, payload: dict) -> tuple[int, dict | list | str | None]:
        return self._request("POST", "/v1/patients", payload)


def _parse_json_or_text(raw: str) -> dict | list | str | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _collect_ids(payload: dict | list | str | None) -> list[int]:
    found: list[int] = []

    def visit(node: object) -> None:
        if isinstance(node, dict):
            for key in ("id", "alertId", "reminderId"):
                value = node.get(key)
                if isinstance(value, int):
                    found.append(value)
                elif isinstance(value, str) and value.strip().isdigit():
                    found.append(int(value))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
        elif isinstance(node, str) and node.strip().isdigit():
            found.append(int(node))

    visit(payload)

    deduped: list[int] = []
    seen: set[int] = set()
    for value in found:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _collect_reminder_label_ids(payload: dict | list | str | None) -> list[int]:
    found: list[int] = []

    def visit(node: object) -> None:
        if isinstance(node, dict):
            for key in ("reminderLabelId", "reminder_id", "reminderId"):
                value = node.get(key)
                if isinstance(value, int):
                    found.append(value)
                elif isinstance(value, str) and value.strip().isdigit():
                    found.append(int(value))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)

    deduped: list[int] = []
    seen: set[int] = set()
    for value in found:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _extract_fallback_collection(payload: dict | list | str | None, keys: Sequence[str]) -> list[int]:
    if isinstance(payload, list):
        return _collect_ids(payload)
    if not isinstance(payload, dict):
        return []

    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            ids = _collect_ids(value)
            if ids:
                return ids

    return _collect_ids(payload)


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

    token = parsed.get("access_token") or parsed.get("token") or parsed.get("jwt") or parsed.get("id_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(f"Token response missing access token field: {parsed}")
    return token


def _discover_account_defaults(client: InstinctClient) -> tuple[int, tuple[int, ...]]:
    alert_status, alert_body = client.fetch_alerts()
    if alert_status >= 400:
        raise RuntimeError(f"Failed to fetch alerts: HTTP {alert_status}\n{json.dumps(alert_body, indent=2, default=str)}")

    reminder_status, reminder_body = client.fetch_reminders()
    if reminder_status >= 400:
        raise RuntimeError(
            f"Failed to fetch reminders: HTTP {reminder_status}\n{json.dumps(reminder_body, indent=2, default=str)}"
        )

    alert_ids = _extract_fallback_collection(alert_body, ("alerts", "data", "items", "results"))
    reminder_ids = _collect_reminder_label_ids(reminder_body)
    if not reminder_ids:
        reminder_ids = _extract_fallback_collection(reminder_body, ("reminders", "data", "items", "results"))

    if not alert_ids:
        raise RuntimeError(f"No alert IDs discovered from /v1/alerts response: {json.dumps(alert_body, indent=2, default=str)}")
    if not reminder_ids:
        raise RuntimeError(
            f"No reminder IDs discovered from /v1/reminders response: {json.dumps(reminder_body, indent=2, default=str)}"
        )

    return alert_ids[0], tuple(reminder_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Instinct test account + optional patient create")
    parser.add_argument("--base-url", required=True, help="Instinct API base URL (e.g. https://partner.instinctvet.com)")
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
    parser.add_argument("--account-id", required=True, help="Test account UUID")
    parser.add_argument("--patient-name", default="bob TEST", help="Patient name for create test (default: bob TEST)")
    parser.add_argument("--patient-pms-id", default="FE261", help="Patient PMS code / pimsCode (default: FE261)")
    parser.add_argument("--breed-id", default=12, type=int, help="Breed ID to use for test patient (default: 12)")
    parser.add_argument("--species-id", default="canine", help="Species ID to use for test patient (default: canine)")
    parser.add_argument("--sex-id", default="unknown", help="Sex ID to use for test patient (default: unknown)")
    parser.add_argument(
        "--create-patient",
        action="store_true",
        help="If set, performs POST /v1/patients with a generated test patient payload",
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
        parser.error("Choose one auth mode: --api-key OR --username/--password OR --client-id/--client-secret.")
    if enabled_auth_modes > 1:
        parser.error(
            "Choose exactly one auth mode: --api-key OR --username/--password OR --client-id/--client-secret."
        )

    if has_api_key:
        auth_header = f"Bearer {args.api_key}"
    elif args.username and args.password:
        encoded = base64.b64encode(f"{args.username}:{args.password}".encode("utf-8")).decode("ascii")
        auth_header = f"Basic {encoded}"
    else:
        print("Fetching OAuth token...")
        token = _fetch_partner_token(args.auth_url, args.client_id, args.client_secret)
        auth_header = f"Bearer {token}"

    client = InstinctClient(base_url=args.base_url, auth_header=auth_header)

    print("== Preflight checks ==")
    for label, fn in (
        ("Account", lambda: client.fetch_account(args.account_id)),
        ("Appointments", client.fetch_appointments),
        ("Appointment Types", client.fetch_appointment_types),
    ):
        status, body = fn()
        print(f"{label}: HTTP {status}")
        if status >= 400:
            print(json.dumps(body, indent=2, default=str))
            return 1

    alert_id, reminder_ids = _discover_account_defaults(client)
    print(f"Discovered alert ID: {alert_id}")
    print(f"Discovered reminder IDs: {', '.join(str(value) for value in reminder_ids)}")

    defaults = ImportDefaults(default_alert_id=alert_id, default_reminder_ids=reminder_ids)
    builder = PatientPayloadBuilder(defaults)

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

    return 0 if status < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
