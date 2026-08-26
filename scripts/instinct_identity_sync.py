from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib import request as urllib_request

try:
    import psycopg
except Exception:  # pragma: no cover - optional in unit tests
    psycopg = None  # type: ignore[assignment]


OWNER_TABLE = "public.instinct_owner_lookup"
PATIENT_TABLE = "public.instinct_patient_lookup"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _merge_target_id(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _pick_contact(account: dict[str, Any], kind: str) -> str:
    primary = account.get("primaryContact") or {}
    details = primary.get("communicationDetails") or []
    if not isinstance(details, list):
        return ""
    for item in details:
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type") or item.get("kind") or "").lower()
        val = _as_text(item.get("value") or item.get("phoneNumber") or item.get("email"))
        if not val:
            continue
        if kind == "phone" and ("phone" in typ or "mobile" in typ or typ == ""):
            return val
        if kind == "email" and "email" in typ:
            return val
    return ""


def _all_contacts(account: dict[str, Any]) -> str:
    primary = account.get("primaryContact") or {}
    details = primary.get("communicationDetails") or []
    if not isinstance(details, list):
        return ""
    values: list[str] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        val = _as_text(item.get("value") or item.get("phoneNumber") or item.get("email"))
        if val and val not in values:
            values.append(val)
    return " | ".join(values)


def _owner_name(account: dict[str, Any]) -> str:
    primary = account.get("primaryContact") or {}
    first = _as_text(primary.get("nameFirst"))
    last = _as_text(primary.get("nameLast"))
    middle = _as_text(primary.get("nameMiddle"))
    label = " ".join(part for part in [first, middle, last] if part)
    return label or _as_text(account.get("label")) or _as_text(account.get("pimsCode")) or _as_text(account.get("id"))


def _patient_name(patient: dict[str, Any]) -> str:
    return _as_text(patient.get("name")) or _as_text(patient.get("pimsCode")) or _as_text(patient.get("id"))


def _db_url() -> str:
    url = os.environ.get("EVH_PGDATABASE_URL", "").strip()
    if url:
        return url
    user = os.environ["EVH_PGUSER"]
    pw = os.environ["EVH_PGPASSWORD"]
    host = os.environ["EVH_PGHOST"]
    port = os.environ["EVH_PGPORT"]
    db = os.environ["EVH_PGDATABASE"]
    from urllib.parse import quote

    return f"postgresql://{user}:{quote(pw, safe='')}@{host}:{port}/{db}"


def _connect():
    if psycopg is None:
        raise RuntimeError("psycopg is required for the identity sync runtime")
    return psycopg.connect(_db_url(), connect_timeout=10)


class InstinctApiSyncClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None

    def _auth(self) -> str:
        if self._token:
            return self._token
        body = json.dumps(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")
        req = urllib_request.Request(
            f"{self.base_url}/v1/auth/token",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = str(data.get("access_token") or data.get("token") or data.get("jwt") or "").strip()
        if not token:
            raise RuntimeError(f"Instinct auth response missing token: {data}")
        self._token = token
        return token

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        from urllib.parse import urlencode

        query = f"?{urlencode(params)}" if params else ""
        req = urllib_request.Request(
            f"{self.base_url}{path}{query}",
            headers={"Authorization": f"Bearer {self._auth()}"},
            method="GET",
        )
        with urllib_request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def iter_accounts(self) -> tuple[list[dict[str, Any]], float]:
        after = None
        rows: list[dict[str, Any]] = []
        started = time.perf_counter()
        while True:
            params: dict[str, Any] = {"limit": 100}
            if after:
                params["pageCursor"] = after
                params["pageDirection"] = "after"
            data = self._get("/v1/accounts", params)
            page_rows = data.get("data") or []
            if not isinstance(page_rows, list):
                raise RuntimeError(f"Unexpected accounts payload: {data}")
            rows.extend([row for row in page_rows if isinstance(row, dict)])
            metadata = data.get("metadata") if isinstance(data, dict) else None
            after = metadata.get("after") if isinstance(metadata, dict) else None
            if not after:
                break
        return rows, time.perf_counter() - started

    def iter_patients(self) -> tuple[list[dict[str, Any]], float]:
        after = None
        rows: list[dict[str, Any]] = []
        started = time.perf_counter()
        while True:
            params: dict[str, Any] = {"limit": 100}
            if after:
                params["pageCursor"] = after
                params["pageDirection"] = "after"
            data = self._get("/v1/patients", params)
            page_rows = data.get("data") or []
            if not isinstance(page_rows, list):
                raise RuntimeError(f"Unexpected patients payload: {data}")
            rows.extend([row for row in page_rows if isinstance(row, dict)])
            metadata = data.get("metadata") if isinstance(data, dict) else None
            after = metadata.get("after") if isinstance(metadata, dict) else None
            if not after:
                break
        return rows, time.perf_counter() - started


def _ensure_identity_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DO $$
            BEGIN
                IF to_regclass('public.instinct_owner_lookup_norm') IS NOT NULL
                   AND to_regclass('public.instinct_owner_lookup') IS NULL THEN
                    ALTER TABLE public.instinct_owner_lookup_norm RENAME TO instinct_owner_lookup;
                END IF;
            END$$
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.instinct_owner_lookup (
                account_id text PRIMARY KEY,
                pims_code text,
                owner_name text NOT NULL,
                phone_primary text,
                phone_all text,
                email text,
                address text,
                city_state_zip text,
                owner_name_lower text,
                owner_name_last_first text,
                phone_digits text,
                updated_at timestamptz NOT NULL,
                deleted_at timestamptz,
                merged_into_account_id text,
                synced_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            ALTER TABLE public.instinct_owner_lookup
                ADD COLUMN IF NOT EXISTS owner_name_lower text,
                ADD COLUMN IF NOT EXISTS owner_name_last_first text,
                ADD COLUMN IF NOT EXISTS phone_digits text,
                ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
                ADD COLUMN IF NOT EXISTS merged_into_account_id text,
                ADD COLUMN IF NOT EXISTS synced_at timestamptz NOT NULL DEFAULT now()
            """
        )
        cur.execute(
            """
            ALTER TABLE public.instinct_patient_lookup
                ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
                ADD COLUMN IF NOT EXISTS merged_into_patient_id bigint,
                ADD COLUMN IF NOT EXISTS synced_at timestamptz NOT NULL DEFAULT now()
            """
        )
        cur.execute(
            """
            ALTER TABLE public.instinct_patient_lookup
                ADD COLUMN IF NOT EXISTS patient_pims_code text,
                ADD COLUMN IF NOT EXISTS birthdate date,
                ADD COLUMN IF NOT EXISTS species text,
                ADD COLUMN IF NOT EXISTS breed text,
                ADD COLUMN IF NOT EXISTS color text,
                ADD COLUMN IF NOT EXISTS sex text,
                ADD COLUMN IF NOT EXISTS weight numeric,
                ADD COLUMN IF NOT EXISTS owner_name text,
                ADD COLUMN IF NOT EXISTS phone_primary text,
                ADD COLUMN IF NOT EXISTS address text,
                ADD COLUMN IF NOT EXISTS city_state_zip text
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'instinct_owner_lookup_pkey'
                ) THEN
                    ALTER TABLE public.instinct_owner_lookup
                        ADD CONSTRAINT instinct_owner_lookup_pkey PRIMARY KEY (account_id);
                END IF;
            END$$
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'instinct_patient_lookup_pkey'
                ) THEN
                    ALTER TABLE public.instinct_patient_lookup
                        ADD CONSTRAINT instinct_patient_lookup_pkey PRIMARY KEY (patient_id);
                END IF;
            END$$
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS instinct_owner_lookup_owner_name_lower_idx
                ON public.instinct_owner_lookup (lower(owner_name))
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS instinct_owner_lookup_owner_name_last_first_idx
                ON public.instinct_owner_lookup (owner_name_last_first)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS instinct_owner_lookup_phone_digits_idx
                ON public.instinct_owner_lookup (phone_digits)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS instinct_patient_lookup_account_patient_lower_idx
                ON public.instinct_patient_lookup (account_id, lower(patient_name))
            """
        )
    conn.commit()


def _account_payload(account: dict[str, Any]) -> dict[str, Any]:
    updated = _parse_dt(account.get("updatedAt")) or _now()
    owner_name = _owner_name(account)
    return {
        "account_id": _as_text(account.get("id")),
        "pims_code": _as_text(account.get("pimsCode")) or None,
        "owner_name": owner_name,
        "phone_primary": _pick_contact(account, "phone") or None,
        "phone_all": _all_contacts(account) or None,
        "email": _pick_contact(account, "email") or None,
        "address": _as_text(account.get("address")) or None,
        "city_state_zip": _as_text(account.get("cityStateZip")) or None,
        "owner_name_lower": owner_name.lower(),
        "owner_name_last_first": " ".join(
            part
            for part in [
                _as_text((account.get("primaryContact") or {}).get("nameLast")),
                _as_text((account.get("primaryContact") or {}).get("nameFirst")),
            ]
            if part
        ).lower()
        or None,
        "phone_digits": "".join(ch for ch in (_pick_contact(account, "phone") or "") if ch.isdigit()) or None,
        "updated_at": updated,
        "deleted_at": _parse_dt(account.get("deletedAt")),
        "merged_into_account_id": _as_text(account.get("mergedIntoAccountId")) or None,
        "synced_at": _now(),
    }


def _patient_payload(patient: dict[str, Any]) -> dict[str, Any]:
    updated = _parse_dt(patient.get("updatedAt")) or _now()
    account = patient.get("account") or {}
    return {
        "patient_id": int(patient.get("id")),
        "account_id": _as_text(patient.get("accountId") or account.get("id")),
        "patient_name": _patient_name(patient),
        "patient_pims_code": _as_text(patient.get("pimsCode")) or None,
        "birthdate": _as_text(patient.get("birthdate")) or None,
        "species": _as_text((patient.get("species") or {}).get("label")) or None,
        "breed": _as_text((patient.get("breed") or {}).get("label")) or None,
        "color": _as_text(patient.get("color")) or None,
        "sex": _as_text((patient.get("sex") or {}).get("label")) or None,
        "weight": patient.get("weight"),
        "owner_name": _owner_name(account) if isinstance(account, dict) else None,
        "phone_primary": _pick_contact(account, "phone") or None,
        "address": _as_text(patient.get("address")) or None,
        "city_state_zip": _as_text(patient.get("cityStateZip")) or None,
        "updated_at": updated,
        "deleted_at": _parse_dt(patient.get("deletedAt")),
        "merged_into_patient_id": _merge_target_id(patient.get("mergedIntoPatientId")),
        "synced_at": _now(),
    }


def _build_refresh_tables(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS public.instinct_owner_lookup_refresh")
        cur.execute("DROP TABLE IF EXISTS public.instinct_patient_lookup_refresh")
        cur.execute("CREATE TABLE public.instinct_owner_lookup_refresh (LIKE public.instinct_owner_lookup INCLUDING ALL)")
        cur.execute("CREATE TABLE public.instinct_patient_lookup_refresh (LIKE public.instinct_patient_lookup INCLUDING ALL)")
    conn.commit()


def _replace_live_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE public.instinct_owner_lookup, public.instinct_patient_lookup")
        cur.execute(
            """
            INSERT INTO public.instinct_owner_lookup
            SELECT * FROM public.instinct_owner_lookup_refresh
            """
        )
        cur.execute(
            """
            INSERT INTO public.instinct_patient_lookup
            SELECT * FROM public.instinct_patient_lookup_refresh
            """
        )
        cur.execute("DROP TABLE public.instinct_owner_lookup_refresh")
        cur.execute("DROP TABLE public.instinct_patient_lookup_refresh")
    conn.commit()


def _load_refresh_tables(conn, accounts: list[dict[str, Any]], patients: list[dict[str, Any]]) -> None:
    _build_refresh_tables(conn)
    owner_rows = [_account_payload(item) for item in accounts]
    patient_rows = [_patient_payload(item) for item in patients]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.instinct_owner_lookup_refresh (
                account_id, pims_code, owner_name, phone_primary, phone_all, email, address, city_state_zip,
                owner_name_lower, owner_name_last_first, phone_digits, updated_at, deleted_at, merged_into_account_id, synced_at
            ) VALUES (
                %(account_id)s, %(pims_code)s, %(owner_name)s, %(phone_primary)s, %(phone_all)s, %(email)s, %(address)s, %(city_state_zip)s,
                %(owner_name_lower)s, %(owner_name_last_first)s, %(phone_digits)s, %(updated_at)s, %(deleted_at)s, %(merged_into_account_id)s, %(synced_at)s
            )
            """,
            owner_rows,
        )
        cur.executemany(
            """
            INSERT INTO public.instinct_patient_lookup_refresh (
                patient_id, account_id, patient_name, patient_pims_code, birthdate, species, breed, color, sex,
                weight, owner_name, phone_primary, address, city_state_zip, updated_at, deleted_at, merged_into_patient_id, synced_at
            ) VALUES (
                %(patient_id)s, %(account_id)s, %(patient_name)s, %(patient_pims_code)s, %(birthdate)s, %(species)s, %(breed)s, %(color)s, %(sex)s,
                %(weight)s, %(owner_name)s, %(phone_primary)s, %(address)s, %(city_state_zip)s, %(updated_at)s, %(deleted_at)s, %(merged_into_patient_id)s, %(synced_at)s
            )
            """,
            patient_rows,
        )
    conn.commit()


def refresh_identity_tables(client: InstinctApiSyncClient, conn) -> dict[str, Any]:
    accounts, accounts_seconds = client.iter_accounts()
    patients, patients_seconds = client.iter_patients()
    _load_refresh_tables(conn, accounts, patients)
    _replace_live_tables(conn)
    return {
        "accounts": {"count": len(accounts), "seconds": round(accounts_seconds, 3)},
        "patients": {"count": len(patients), "seconds": round(patients_seconds, 3)},
        "total_seconds": round(accounts_seconds + patients_seconds, 3),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Full refresh Instinct identity tables into Aurora PostgreSQL.")
    parser.add_argument("--base-url", default=os.environ.get("INSTINCT_API_BASE_URL", "https://partner.instinctvet.com"))
    parser.add_argument("--client-id", default=os.environ.get("INSTINCT_CLIENT_ID", ""))
    parser.add_argument("--client-secret", default=os.environ.get("INSTINCT_CLIENT_SECRET", ""))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.client_id or not args.client_secret:
        raise SystemExit("INSTINCT client credentials are required")

    client = InstinctApiSyncClient(args.base_url, args.client_id, args.client_secret)

    with _connect() as conn:
        _ensure_identity_schema(conn)
        result = refresh_identity_tables(client, conn)
        print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
