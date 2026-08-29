"""Reusable Instinct account and patient adapter utilities."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Optional


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


def extract_collection(payload: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def extract_phone_no(communication_details: Iterable[Any]) -> Optional[str]:
    for item in communication_details:
        if not isinstance(item, dict):
            continue

        value = item.get("value") or item.get("number") or item.get("phoneNumber")
        kind = (item.get("type") or item.get("kind") or "").lower()

        if value and ("phone" in kind or "mobile" in kind or kind == ""):
            return value

    return None


def normalize_lookup_text(value: Any) -> str:
    return normalize_text(value).casefold()


def normalize_phone_no(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def account_display_name(account: Any) -> Optional[str]:
    if not isinstance(account, dict):
        return None

    primary = account.get("primaryContact") or {}
    if not isinstance(primary, dict):
        return None

    first = normalize_text(primary.get("nameFirst"))
    middle = normalize_text(primary.get("nameMiddle"))
    last = normalize_text(primary.get("nameLast"))
    name_parts = [part for part in (first, middle, last) if part]
    if name_parts:
        return " ".join(name_parts)
    return None


@dataclass(frozen=True)
class NormalizedAccount:
    account_id: str
    pims_code: str
    pims_id: Optional[str]
    first_name: str
    middle_name: str
    last_name: str
    display_name: str
    primary_phone: str
    email: Optional[str]
    updated_at: Optional[str]
    deleted_at: Optional[str]
    is_deleted: bool


@dataclass(frozen=True)
class WeaveContactProjection:
    source_system: str
    source_account_id: str
    clinic_id: str
    pims_code: str
    pims_id: Optional[str]
    display_name: str
    first_name: str
    middle_name: str
    last_name: str
    primary_phone: str
    email: Optional[str]
    is_active: bool
    updated_at: Optional[str]
    deleted_at: Optional[str]
    payload_hash: str


def _extract_email(communication_details: Iterable[Any]) -> Optional[str]:
    for item in communication_details:
        if not isinstance(item, dict):
            continue
        kind = (item.get("type") or item.get("kind") or "").lower()
        value = item.get("value") or item.get("email")
        if value and "email" in kind:
            return normalize_text(value) or None
    return None


def normalize_account(account: dict[str, Any]) -> NormalizedAccount:
    primary = account.get("primaryContact") or {}
    communication = primary.get("communicationDetails") or []
    first = normalize_text(primary.get("nameFirst"))
    middle = normalize_text(primary.get("nameMiddle"))
    last = normalize_text(primary.get("nameLast"))
    display_name = " ".join(part for part in (first, middle, last) if part)
    deleted_at = normalize_text(account.get("deletedAt")) or None
    return NormalizedAccount(
        account_id=normalize_text(account.get("id")),
        pims_code=normalize_text(account.get("pimsCode")),
        pims_id=normalize_text(account.get("pimsId")) or None,
        first_name=first,
        middle_name=middle,
        last_name=last,
        display_name=display_name,
        primary_phone=normalize_phone_no(extract_phone_no(communication)),
        email=_extract_email(communication),
        updated_at=normalize_text(account.get("updatedAt")) or None,
        deleted_at=deleted_at,
        is_deleted=bool(deleted_at),
    )


def _hash_projection(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_account_to_weave_contact(account: NormalizedAccount, clinic_id: str) -> WeaveContactProjection:
    payload = {
        "source_system": "instinct",
        "source_account_id": account.account_id,
        "clinic_id": clinic_id,
        "pims_code": account.pims_code,
        "pims_id": account.pims_id,
        "display_name": account.display_name,
        "first_name": account.first_name,
        "middle_name": account.middle_name,
        "last_name": account.last_name,
        "primary_phone": account.primary_phone,
        "email": account.email,
        "is_active": not account.is_deleted,
        "updated_at": account.updated_at,
        "deleted_at": account.deleted_at,
    }
    return WeaveContactProjection(payload_hash=_hash_projection(payload), **payload)


class InstinctAccountPatientAdapter:
    """Instinct API adapter for account and patient identity operations."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token: Optional[str] = None

    def authenticate(self) -> str:
        import requests

        url = f"{self.base_url}/v1/auth/token"
        resp = requests.post(
            url,
            json={
                "grant_type": "client_credentials",
                "client_id": self.username,
                "client_secret": self.password,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        self.token = data["access_token"]
        return self.token

    def _get(self, path: str, params=None):
        import requests

        resp = requests.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            params=params or {},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, payload: dict[str, Any]):
        import requests

        resp = requests.patch(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def iter_patients(self, *, limit: int = 100):
        after = None

        while True:
            params = {"limit": limit}
            if after:
                params["pageCursor"] = after
                params["pageDirection"] = "after"

            data = self._get("/v1/patients", params)

            patients = data.get("data", [])
            for patient in patients:
                patient_id = patient.get("id")
                if patient_id is None:
                    yield patient
                else:
                    yield self._get(f"/v1/patients/{patient_id}")

            metadata = data.get("metadata") if isinstance(data, dict) else None
            after = metadata.get("after") if isinstance(metadata, dict) else None
            if not after:
                break

    def iter_accounts(self, params: Optional[dict[str, Any]] = None, *, limit: int = 100):
        after = None

        while True:
            request_params: dict[str, Any] = {"limit": limit}
            if params:
                request_params.update(params)
            if after:
                request_params["pageCursor"] = after
                request_params["pageDirection"] = "after"

            data = self._get("/v1/accounts", request_params)
            accounts = extract_collection(data, ("accounts", "data", "items", "results"))
            for account in accounts:
                yield account

            metadata = data.get("metadata") if isinstance(data, dict) else None
            after = metadata.get("after") if isinstance(metadata, dict) else None
            if not after:
                break

    def iter_patients_for_account(self, account_id: str, *, limit: int = 100):
        after = None

        while True:
            params: dict[str, Any] = {"limit": limit, "accountId": account_id}
            if after:
                params["pageCursor"] = after
                params["pageDirection"] = "after"

            data = self._get("/v1/patients", params)
            patients = extract_collection(data, ("patients", "data", "items", "results"))
            for patient in patients:
                yield patient

            metadata = data.get("metadata") if isinstance(data, dict) else None
            after = metadata.get("after") if isinstance(metadata, dict) else None
            if not after:
                break

    def iter_patients_for_account_id(self, account_id: str):
        yield from self.iter_patients_for_account(account_id)

    def _find_accounts_by_client_code(self, client_code: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for field_name in ("pimsCode", "pimsId"):
            for account in self.iter_accounts({field_name: client_code}):
                account_id = str(account.get("id") or "")
                if account_id and account_id not in seen_ids:
                    matches.append(account)
                    seen_ids.add(account_id)

        return matches

    def _find_accounts_by_owner(self, owner_name: str, phone_no: str) -> list[dict[str, Any]]:
        candidates = list(self.iter_accounts({"name": owner_name}))
        owner_name_normalized = normalize_lookup_text(owner_name)
        phone_digits = normalize_phone_no(phone_no)

        exact_name_matches = [
            account
            for account in candidates
            if normalize_lookup_text(account_display_name(account)) == owner_name_normalized
        ]
        narrowed = exact_name_matches or candidates

        if not phone_digits:
            return narrowed

        phone_matches = []
        for account in narrowed:
            primary = account.get("primaryContact") or {}
            account_phone = normalize_phone_no(extract_phone_no((primary.get("communicationDetails") or [])))
            if account_phone and account_phone == phone_digits:
                phone_matches.append(account)

        return phone_matches or narrowed

    def _account_matches_source_patient(self, account: dict[str, Any], source_patient: Any) -> bool:
        normalized_name = normalize_lookup_text(source_patient.client_name)
        account_name = normalize_lookup_text(account_display_name(account))
        if normalized_name and account_name and normalized_name == account_name:
            source_phone = normalize_phone_no(source_patient.phone_no)
            account_phone = normalize_phone_no(
                extract_phone_no((account.get("primaryContact") or {}).get("communicationDetails") or [])
            )
            if source_phone and account_phone:
                return source_phone == account_phone
            return True
        return False

    def _find_account_for_source_patient(self, source_patient: Any) -> Optional[dict[str, Any]]:
        matches = self._find_accounts_by_client_code(normalize_text(source_patient.client))
        if matches:
            return matches[0]

        source_name = normalize_text(source_patient.client_name)
        if not source_name:
            return None

        candidate_accounts = list(self.iter_accounts({"limit": 100, "name": source_name}))
        if not candidate_accounts:
            return None

        for account in candidate_accounts:
            if self._account_matches_source_patient(account, source_patient):
                return account

        return candidate_accounts[0]

    def find_patient(self, source_patient: Any) -> dict[str, Any]:
        account = self._find_account_for_source_patient(source_patient)
        if not account:
            raise RuntimeError(
                f"Could not find Instinct account for client={source_patient.client!r} owner={source_patient.client_name!r}"
            )

        account_id = account.get("id")
        if not account_id:
            raise RuntimeError(f"Matched account is missing id for client={source_patient.client!r}")

        wanted_name = normalize_lookup_text(source_patient.patient_name)
        patient_matches = [
            patient
            for patient in self.iter_patients_for_account(str(account_id))
            if normalize_lookup_text(patient.get("name")) == wanted_name
        ]

        if not patient_matches:
            raise RuntimeError(
                f"Could not find patient name={source_patient.patient_name!r} in account_id={account_id!r}"
            )

        if len(patient_matches) > 1:
            patient_ids = [patient.get("id") for patient in patient_matches]
            raise RuntimeError(
                f"Patient lookup was ambiguous for name={source_patient.patient_name!r} in account_id={account_id!r}: {patient_ids}"
            )

        patient_id = patient_matches[0].get("id")
        if patient_id is None:
            raise RuntimeError(
                f"Matched patient is missing id for name={source_patient.patient_name!r} in account_id={account_id!r}"
            )

        return self._get(f"/v1/patients/{patient_id}")

    def summarize_patient(self, patient_record: dict[str, Any], *, reminder_count: Optional[int] = None) -> dict[str, Any]:
        account = patient_record.get("account") or {}
        primary = account.get("primaryContact") or {}

        first = (primary.get("nameFirst") or "").strip()
        middle = (primary.get("nameMiddle") or "").strip()
        last = (primary.get("nameLast") or "").strip()

        name_parts = [part for part in (first, middle, last) if part]
        client_name = " ".join(name_parts) if name_parts else None

        phone_no = extract_phone_no(primary.get("communicationDetails") or [])

        return {
            "client_name": client_name,
            "patient_name": patient_record.get("name"),
            "phone_no": phone_no,
            "reminder_count": reminder_count,
            "patient_id": patient_record.get("id"),
            "account_id": patient_record.get("accountId"),
            "pims_code": patient_record.get("pimsCode"),
        }
