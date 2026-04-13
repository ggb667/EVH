"""Audit Active Patients CSV for import-readiness and unique patient identification.

This script is intentionally read-only. Use it before any production import to answer:
1) Is there a stable unique key for each patient?
2) Do we have enough required fields for Instinct patient payloads?

Usage:
  python scripts/instinct_active_patients_audit.py --csv "Active Patients.csv"
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


IDENTIFIER_CANDIDATES: dict[str, tuple[str, ...]] = {
    "pms_id": (
        "pms id",
        "pims id",
        "pimsid",
        "pmsid",
        "patient pms id",
        "patient_pms_id",
        "patient id",
        "id",
        "external id",
        "external_id",
        "code",
    ),
    "patient_name": ("patient", "patient name", "name", "pet name", "pet"),
    "owner_name": ("owner", "owner name", "client", "client name"),
    "owner_email": ("email", "owner email", "client email"),
    "owner_phone": ("phone", "owner phone", "client phone", "mobile"),
    "species": ("species",),
    "breed": ("breed", "breed name"),
    "sex": ("sex", "gender"),
}


@dataclass(frozen=True)
class AuditReport:
    total_rows: int
    selected_identifier_column: str | None
    missing_identifier_rows: int
    duplicate_identifier_values: int
    missing_required_counts: dict[str, int]

    @property
    def has_unique_identifier(self) -> bool:
        return (
            self.selected_identifier_column is not None
            and self.missing_identifier_rows == 0
            and self.duplicate_identifier_values == 0
        )


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().replace("_", " ").split())


def _locate_columns(fieldnames: list[str]) -> dict[str, str]:
    normalized_to_original = {_normalize(name): name for name in fieldnames}
    found: dict[str, str] = {}
    for logical_name, aliases in IDENTIFIER_CANDIDATES.items():
        for alias in aliases:
            if alias in normalized_to_original:
                found[logical_name] = normalized_to_original[alias]
                break
    return found


def _count_missing(rows: list[dict[str, str]], column: str | None) -> int:
    if not column:
        return len(rows)
    return sum(1 for row in rows if not (row.get(column) or "").strip())


def _count_duplicates(rows: list[dict[str, str]], column: str | None) -> int:
    if not column:
        return 0
    values = [(row.get(column) or "").strip() for row in rows if (row.get(column) or "").strip()]
    counts = Counter(values)
    return sum(1 for count in counts.values() if count > 1)


def audit_rows(rows: list[dict[str, str]], columns: dict[str, str]) -> AuditReport:
    identifier_column = columns.get("pms_id")
    missing_required = {
        "account mapping input (owner/email/phone)": min(
            _count_missing(rows, columns.get("owner_name")),
            _count_missing(rows, columns.get("owner_email")),
            _count_missing(rows, columns.get("owner_phone")),
        ),
        "patient_name": _count_missing(rows, columns.get("patient_name")),
        "species": _count_missing(rows, columns.get("species")),
        "breed": _count_missing(rows, columns.get("breed")),
        "sex": _count_missing(rows, columns.get("sex")),
    }

    return AuditReport(
        total_rows=len(rows),
        selected_identifier_column=identifier_column,
        missing_identifier_rows=_count_missing(rows, identifier_column),
        duplicate_identifier_values=_count_duplicates(rows, identifier_column),
        missing_required_counts=missing_required,
    )


def load_csv(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row.")
        rows = [dict(row) for row in reader]
        columns = _locate_columns(reader.fieldnames)
        return rows, columns


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit active-patients CSV before Instinct import")
    parser.add_argument("--csv", required=True, help='Path to CSV file, e.g. "Active Patients.csv"')
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        print(f"CSV not found: {path}")
        return 1

    rows, columns = load_csv(path)
    report = audit_rows(rows, columns)

    print("== Active Patients CSV audit ==")
    print(f"Rows: {report.total_rows}")
    print(f"Identifier column: {report.selected_identifier_column or 'NOT FOUND'}")
    print(f"Rows missing identifier: {report.missing_identifier_rows}")
    print(f"Duplicate identifier values: {report.duplicate_identifier_values}")

    print("\nMissing-field counts (should be 0 before full import):")
    for key, value in report.missing_required_counts.items():
        print(f"- {key}: {value}")

    print("\nRecommendation:")
    if report.has_unique_identifier:
        print("- ✅ PMS/patient ID appears unique per row.")
    else:
        print("- ❌ PMS/patient ID is missing, duplicated, or not discoverable by header name.")
        print("  Add/clean a unique patient external ID column before bulk import.")

    missing_required_total = sum(report.missing_required_counts.values())
    if missing_required_total:
        print("- ❌ Additional fields are needed for reliable import mapping (see missing counts above).")
    else:
        print("- ✅ Core fields for mapping are present.")

    print("\nRun this only after your test-account patient create succeeds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
