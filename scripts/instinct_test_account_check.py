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
from urllib import error, request

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

    def create_patient(self, payload: dict) -> tuple[int, dict | list | str | None]:
        return self._request("POST", "/v1/patients", payload)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Instinct test account + optional patient create")
    parser.add_argument("--base-url", required=True, help="Instinct API base URL (e.g. https://partner.instinctvet.com)")
    parser.add_argument("--api-key", help="Instinct Partner API key/token (Bearer auth)")
    parser.add_argument("--username", help="Instinct username (for Basic auth)")
    parser.add_argument("--password", help="Instinct password (for Basic auth)")
    parser.add_argument("--account-id", required=True, help="Test account UUID")
    parser.add_argument("--default-alert-id", required=True, type=int, help="Default alert ID to attach")
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
    args = parser.parse_args()

    if not args.api_key and not (args.username and args.password):
        parser.error("Provide either --api-key OR both --username and --password.")

    if args.api_key and (args.username or args.password):
        parser.error("Choose one auth mode: --api-key OR --username/--password.")

    if args.api_key:
        auth_header = f"Bearer {args.api_key}"
    else:
        encoded = base64.b64encode(f"{args.username}:{args.password}".encode("utf-8")).decode("ascii")
        auth_header = f"Basic {encoded}"

    defaults = ImportDefaults(
        default_alert_id=args.default_alert_id,
        default_reminder_ids=_parse_ids(args.default_reminder_ids),
    )
    builder = PatientPayloadBuilder(defaults)
    client = InstinctClient(base_url=args.base_url, auth_header=auth_header)

    print("== Preflight checks ==")
    for label, fn in (
        ("Account", lambda: client.fetch_account(args.account_id)),
        ("Alerts", client.fetch_alerts),
        ("Reminders", client.fetch_reminders),
    ):
        status, body = fn()
        print(f"{label}: HTTP {status}")
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

    return 0 if status < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
