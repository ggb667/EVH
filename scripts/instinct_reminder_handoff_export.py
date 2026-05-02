from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evh_reminder_importer import build_import_plan, parse_grouped_spreadsheet
from scripts.instinct_accounts import InstinctAccountPatientAdapter


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "scripts" / "ReminderData.xlsx"
OUTPUT = ROOT / "scripts" / "instinct_reminder_handoff.csv"
CREDS = Path("/home/ggb66/dev/creds.txt")


def load_credentials() -> tuple[str, str]:
    values = [line.strip() for line in CREDS.read_text().splitlines() if line.strip()]
    if len(values) < 5:
        raise RuntimeError(f"Expected Instinct credentials in {CREDS}")
    return values[2], values[4]


def progress(label: str, current: int, total: int | None = None) -> None:
    if total:
        print(f"{label}: {current}/{total}", flush=True)
    else:
        print(f"{label}: {current}", flush=True)


def _resolve_group(adapter: InstinctAccountPatientAdapter, plan) -> tuple[str, str, str, str]:
    try:
        patient_record = adapter.find_patient(plan.patient)
        summary = adapter.summarize_patient(patient_record)
        patient_id = str(summary.get("patient_id") or "")
        account_id = str(summary.get("account_id") or "")
        pims_code = str(summary.get("pims_code") or "")
        if patient_id:
            return patient_id, account_id, pims_code, "resolved_by_live_lookup"
        return "", account_id, pims_code, "missing_patient_id"
    except Exception as exc:
        msg = str(exc).lower()
        if "ambiguous" in msg:
            return "", "", "", "ambiguous"
        if "could not find instinct account" in msg:
            return "", "", "", "no_account"
        if "could not find patient" in msg:
            return "", "", "", "no_patient"
        return "", "", "", "other"


def _resolve_reminder_label_id(adapter: InstinctAccountPatientAdapter, label: str) -> str:
    try:
        reminder_id = adapter.resolve_reminder_label_id(label)
    except Exception:
        reminder_id = None
    return "" if reminder_id is None else str(reminder_id)


def main() -> int:
    username, password = load_credentials()
    adapter = InstinctAccountPatientAdapter("https://partner.instinctvet.com", username, password)
    adapter.token = adapter.authenticate()

    plans = build_import_plan(parse_grouped_spreadsheet(WORKBOOK))
    progress("processing reminder groups", 0, len(plans))

    rows = []
    status_counts = Counter()
    reason_counts = Counter()
    resolved_groups = 0

    for index, plan in enumerate(plans, start=1):
        patient_id, account_id, pims_code, reason = _resolve_group(adapter, plan)
        status = "resolved_by_live_lookup" if patient_id else "unresolved"
        match_confidence = "high" if patient_id else "low"
        if patient_id:
            resolved_groups += 1

        status_counts[status] += 1
        reason_counts[reason] += 1

        for reminder in plan.valid_reminders:
            instinct_label_id = _resolve_reminder_label_id(adapter, reminder.mapped_label)
            rows.append(
                {
                    "avimark_client": plan.patient.client,
                    "client_name": plan.patient.client_name,
                    "phone_no": plan.patient.phone_no,
                    "patient_name": plan.patient.patient_name,
                    "species": plan.patient.species,
                    "breed": plan.patient.breed,
                    "header_row_number": plan.patient.header_row_number,
                    "instinct_patient_id": patient_id,
                    "instinct_account_id": account_id,
                    "instinct_patient_pims_code": pims_code,
                    "resolution_status": status,
                    "resolution_reason": reason,
                    "match_method": "client_code_then_owner_phone_then_patient_name",
                    "match_confidence": match_confidence,
                    "instinct_label_id": instinct_label_id,
                    "source_row_number": reminder.row_number,
                    "source_code": reminder.source_code,
                    "source_label": reminder.source_label,
                    "instinct_label": reminder.mapped_label,
                    "due_date": reminder.due_date,
                }
            )

        if index % 10 == 0:
            progress("processed groups", index, len(plans))
            print(
                f"  resolved={resolved_groups} unresolved={status_counts['unresolved']} "
                f"ambiguous={reason_counts['ambiguous']}",
                flush=True,
            )

    fields = [
        "avimark_client",
        "client_name",
        "phone_no",
        "patient_name",
        "species",
        "breed",
        "header_row_number",
        "instinct_patient_id",
        "instinct_account_id",
        "instinct_patient_pims_code",
        "resolution_status",
        "resolution_reason",
        "match_method",
        "match_confidence",
        "instinct_label_id",
        "source_row_number",
        "source_code",
        "source_label",
        "instinct_label",
        "due_date",
    ]
    tmp = OUTPUT.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(OUTPUT)

    progress("written rows", len(rows))
    print(f"status_counts={dict(status_counts)}", flush=True)
    print(f"reason_counts={dict(reason_counts)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
