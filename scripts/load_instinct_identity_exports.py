from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ACCOUNT_COLUMNS = [
    "id",
    "pims_code",
    "pims_id",
    "owner_first_name",
    "owner_last_name",
    "display_name",
    "primary_phone",
    "email_addresses",
    "communication_details",
    "updated_at",
    "deleted_at",
    "is_deleted",
    "raw_payload",
]

PATIENT_COLUMNS = [
    "id",
    "account_id",
    "pims_code",
    "name",
    "birthdate",
    "sex_id",
    "species_id",
    "breed",
    "deceased_date",
    "deleted_at",
    "merged_into_patient_id",
    "alerts",
    "raw_payload",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _display_name(first: Any, last: Any) -> str:
    parts = [part for part in [first or "", last or ""] if part]
    return " ".join(parts)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _prepare_account_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        raw = row.get("raw") or {}
        first_name = row.get("ownerFirstName") or ""
        last_name = row.get("ownerLastName") or ""
        prepared.append(
            {
                "id": row.get("id") or "",
                "pims_code": row.get("pimsCode") or "",
                "pims_id": row.get("pimsId") or "",
                "owner_first_name": first_name,
                "owner_last_name": last_name,
                "display_name": _display_name(first_name, last_name),
                "primary_phone": row.get("primaryPhone") or "",
                "email_addresses": _json_text(row.get("emailAddresses") or []),
                "communication_details": _json_text(row.get("communicationDetails") or []),
                "updated_at": row.get("updatedAt") or "",
                "deleted_at": row.get("deletedAt") or "",
                "is_deleted": "true" if row.get("deletedAt") else "false",
                "raw_payload": _json_text(raw),
            }
        )
    return prepared


def _prepare_patient_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        raw = row.get("raw") or {}
        prepared.append(
            {
                "id": row.get("id") or "",
                "account_id": row.get("accountId") or "",
                "pims_code": row.get("pimsCode") or "",
                "name": row.get("name") or "",
                "birthdate": row.get("birthdate") or "",
                "sex_id": row.get("sexId") or "",
                "species_id": row.get("speciesId") or "",
                "breed": row.get("breed") or "",
                "deceased_date": row.get("deceasedDate") or "",
                "deleted_at": row.get("deletedAt") or "",
                "merged_into_patient_id": row.get("mergedIntoPatientId") or "",
                "alerts": _json_text(row.get("alerts") or []),
                "raw_payload": _json_text(raw),
            }
        )
    return prepared


def _write_plan(
    path: Path,
    *,
    output_dir: Path,
    accounts_csv: Path,
    patients_csv: Path,
    accounts_count: int,
    patients_count: int,
) -> None:
    plan = {
        "target_database": "separate EVH PostgreSQL database",
        "load_order": [
            "instinct_accounts",
            "instinct_patients",
        ],
        "inputs": {
            "accounts_jsonl_rows": accounts_count,
            "patients_jsonl_rows": patients_count,
        },
        "outputs": {
            "accounts_csv": str(accounts_csv.relative_to(output_dir)),
            "patients_csv": str(patients_csv.relative_to(output_dir)),
        },
        "notes": [
            "Keep identity rows separate from the EVH RAG vector store.",
            "Load the prepared CSVs into the target Postgres database with a migration tool or COPY step.",
        ],
    }
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare Instinct account and patient exports for a separate EVH PostgreSQL migration."
    )
    parser.add_argument("--accounts-jsonl", required=True)
    parser.add_argument("--patients-jsonl", required=True)
    parser.add_argument("--output-dir", default="exports/instinct_identity_migration")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    accounts_path = Path(args.accounts_jsonl)
    patients_path = Path(args.patients_jsonl)
    if not accounts_path.exists():
        raise SystemExit(f"Accounts export not found: {accounts_path}")
    if not patients_path.exists():
        raise SystemExit(f"Patients export not found: {patients_path}")

    output_dir = Path(args.output_dir)

    accounts_rows = _prepare_account_rows(_read_jsonl(accounts_path))
    patients_rows = _prepare_patient_rows(_read_jsonl(patients_path))

    accounts_csv = output_dir / "instinct_accounts.csv"
    patients_csv = output_dir / "instinct_patients.csv"
    plan_path = output_dir / "migration_plan.json"

    if args.dry_run:
        print(f"accounts: {len(accounts_rows)} -> {accounts_csv}")
        print(f"patients: {len(patients_rows)} -> {patients_csv}")
        print(f"plan: {plan_path}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(accounts_csv, accounts_rows, ACCOUNT_COLUMNS)
    _write_csv(patients_csv, patients_rows, PATIENT_COLUMNS)
    _write_plan(
        plan_path,
        output_dir=output_dir,
        accounts_csv=accounts_csv,
        patients_csv=patients_csv,
        accounts_count=len(accounts_rows),
        patients_count=len(patients_rows),
    )

    print(f"wrote {accounts_csv}")
    print(f"wrote {patients_csv}")
    print(f"wrote {plan_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
