from __future__ import annotations

import argparse
import csv
from collections import OrderedDict
from collections import Counter
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from scripts.instinct_partner_client import InstinctPartnerClient

VETCOVE_COLUMNS = (
    "Animal Id",
    "Division",
    "Animal Name",
    "Animal Weight (lb)",
    "Date of Birth",
    "Sex",
    "Has Passed Away",
    "Date of Passing",
    "Cause of Death",
    "Caution Status",
    "Species",
    "Breed",
    "Last Visit",
    "Owner First Name",
    "Owner Last Name",
    "Owner Contact Code",
    "Physical Address Street 1",
    "Physical Address Street 2",
    "Physical Address City",
    "Physical Address Postcode",
    "Physical Address State",
    "Physical Address Country",
    "Email Addresses",
    "Mobile Numbers",
    "Phone Numbers",
)

DIVISION_NAME = "Eustis Veterinary Hospital"
DEFAULT_CITY = "Eustis"
DEFAULT_STATE = "FL"
DEFAULT_POSTCODE = "32726"

SEX_MAP = {
    "female_spayed": "Female Spayed",
    "female": "Female",
    "male_castrated": "Male Neutered",
    "male_neutered": "Male Neutered",
    "male": "Male",
    "unknown": "Unknown Sex",
}

SPECIES_MAP = {
    "avian": "Avian",
    "bird": "Avian",
    "can": "Canine",
    "canine": "Canine",
    "dog": "Canine",
    "fel": "Feline",
    "feline": "Feline",
    "cat": "Feline",
    "ferret": "Ferret",
    "hamster": "Hamster",
    "rabbit": "Rabbit",
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def iso_to_mmddyyyy(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    date_part = text.split("T", 1)[0]
    try:
        dt = datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        return ""
    return dt.strftime("%m-%d-%Y")


def format_weight(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ""
    return format(number.quantize(Decimal("0.01")), "f")


def normalize_phone(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def dedupe_preserve(values: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys(v for v in values if v))


def map_sex(patient: dict[str, Any]) -> str:
    sex_id = normalize_text(patient.get("sexId")).lower()
    if sex_id in SEX_MAP:
        return SEX_MAP[sex_id]
    label = normalize_text((patient.get("sex") or {}).get("label"))
    return label if label in set(SEX_MAP.values()) else "Unknown Sex"


def map_species(patient: dict[str, Any]) -> str:
    species_id = normalize_text(patient.get("speciesId")).lower()
    if species_id in SPECIES_MAP:
        return SPECIES_MAP[species_id]
    label = normalize_text((patient.get("species") or {}).get("label"))
    return label if label in set(SPECIES_MAP.values()) else "Other"


def parse_address(value: Any) -> dict[str, str]:
    text = normalize_text(value)
    if not text:
        return {
            "street1": "",
            "street2": "",
            "city": "",
            "postcode": "",
            "state": "",
        }

    parts = [part.strip() for part in text.split(",")]
    street = parts[0] if parts else ""
    city = parts[1] if len(parts) > 1 else ""
    state_zip = parts[2] if len(parts) > 2 else ""

    state = ""
    postcode = ""
    if state_zip:
        tokens = state_zip.split()
        if tokens:
            state = tokens[0]
        if len(tokens) > 1:
            postcode = tokens[-1]

    return {
        "street1": street,
        "street2": "",
        "city": city,
        "postcode": postcode,
        "state": state,
    }


def collect_contact_details(account: dict[str, Any]) -> dict[str, str]:
    contacts: list[dict[str, Any]] = []
    primary = account.get("primaryContact")
    if isinstance(primary, dict):
        contacts.append(primary)
    alternates = account.get("alternateContacts") or []
    contacts.extend(item for item in alternates if isinstance(item, dict))

    emails: list[str] = []
    mobiles: list[str] = []
    phones: list[str] = []
    address = {
        "street1": "",
        "street2": "",
        "city": "",
        "postcode": "",
        "state": "",
    }

    for contact in contacts:
        for detail in contact.get("communicationDetails") or []:
            if not isinstance(detail, dict):
                continue
            kind = normalize_text(detail.get("type")).lower()
            value = detail.get("value")
            if kind == "email":
                email = normalize_text(value)
                if email:
                    emails.append(email)
            elif kind == "mobile":
                mobile = normalize_phone(value)
                if mobile:
                    mobiles.append(mobile)
                    phones.append(mobile)
            elif kind == "phone":
                phone = normalize_phone(value)
                if phone:
                    phones.append(phone)
            elif kind == "full_address" and not address["street1"]:
                address = parse_address(value)

    emails = dedupe_preserve(emails)
    mobiles = dedupe_preserve(mobiles)
    phones = dedupe_preserve(phones)

    # Instinct often stores the only reachable number as a generic phone.
    # Promote the first phone into the mobile slot when no explicit mobile exists.
    if not mobiles and phones:
        mobiles = [phones[0]]

    return {
        **address,
        "emails": ",".join(emails),
        "mobiles": ",".join(mobiles),
        "phones": ",".join(phones),
    }


def build_city_zip_map(accounts: dict[str, dict[str, Any]]) -> dict[str, str]:
    zip_by_city: dict[str, Counter[str]] = defaultdict(Counter)
    for account in accounts.values():
        contact_info = collect_contact_details(account)
        city = contact_info["city"]
        postcode = contact_info["postcode"]
        if city and postcode:
            zip_by_city[city][postcode] += 1
    return {
        city: counts.most_common(1)[0][0]
        for city, counts in zip_by_city.items()
        if counts
    }


def apply_location_defaults(row: dict[str, str], city_zip_map: dict[str, str]) -> dict[str, str]:
    city = row["Physical Address City"].strip()
    state = row["Physical Address State"].strip()
    postcode = row["Physical Address Postcode"].strip()

    if city and not state:
        state = DEFAULT_STATE
    if city and not postcode:
        postcode = city_zip_map.get(city, "")

    if not city:
        city = DEFAULT_CITY
    if not state:
        state = DEFAULT_STATE
    if not postcode:
        postcode = city_zip_map.get(city, DEFAULT_POSTCODE)

    row["Physical Address City"] = city
    row["Physical Address State"] = state
    row["Physical Address Postcode"] = postcode
    return row


def build_last_visit_map(client: InstinctPartnerClient) -> dict[int, str]:
    last_visits: dict[int, str] = {}
    now = datetime.now(timezone.utc)

    for appointment in client.iter_appointments(limit=100):
        if appointment.get("deletedAt"):
            continue
        status = normalize_text(appointment.get("status")).lower()
        if status in {"canceled", "cancelled"}:
            continue

        starts_at = normalize_text(appointment.get("startsAt"))
        if not starts_at:
            continue
        normalized = starts_at.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.astimezone(timezone.utc) > now:
            continue

        patient_id = appointment.get("patientId")
        if not isinstance(patient_id, int):
            patient_obj = appointment.get("patient") or {}
            patient_id = patient_obj.get("id")
        if not isinstance(patient_id, int):
            continue

        rendered = dt.strftime("%m-%d-%Y")
        previous = last_visits.get(patient_id)
        if previous is None or datetime.strptime(rendered, "%m-%d-%Y") > datetime.strptime(previous, "%m-%d-%Y"):
            last_visits[patient_id] = rendered

    return last_visits


def build_account_map(client: InstinctPartnerClient) -> dict[str, dict[str, Any]]:
    accounts: dict[str, dict[str, Any]] = {}
    for account in client.iter_accounts({"includeDeleted": "true"}, limit=100):
        account_id = normalize_text(account.get("id"))
        if account_id:
            accounts[account_id] = account
    return accounts


def patient_to_vetcove_row(
    patient: dict[str, Any],
    account: dict[str, Any],
    *,
    division: str,
    last_visit: str,
) -> dict[str, str]:
    primary = account.get("primaryContact") or patient.get("account", {}).get("primaryContact") or {}
    contact_info = collect_contact_details(account)
    alerts = patient.get("alerts") or []

    return {
        "Animal Id": normalize_text(patient.get("pimsCode") or patient.get("id")),
        "Division": division,
        "Animal Name": normalize_text(patient.get("name")),
        "Animal Weight (lb)": format_weight(patient.get("weight")),
        "Date of Birth": iso_to_mmddyyyy(patient.get("birthdate")),
        "Sex": map_sex(patient),
        "Has Passed Away": "No",
        "Date of Passing": "",
        "Cause of Death": "",
        "Caution Status": ", ".join(
            normalize_text(alert.get("label"))
            for alert in alerts
            if isinstance(alert, dict) and normalize_text(alert.get("label"))
        ),
        "Species": map_species(patient),
        "Breed": normalize_text((patient.get("breed") or {}).get("label")),
        "Last Visit": last_visit,
        "Owner First Name": normalize_text(primary.get("nameFirst")),
        "Owner Last Name": normalize_text(primary.get("nameLast")),
        "Owner Contact Code": normalize_text(account.get("pimsCode") or account.get("pimsId") or account.get("id")),
        "Physical Address Street 1": contact_info["street1"],
        "Physical Address Street 2": contact_info["street2"],
        "Physical Address City": contact_info["city"],
        "Physical Address Postcode": contact_info["postcode"],
        "Physical Address State": contact_info["state"],
        "Physical Address Country": "United States",
        "Email Addresses": contact_info["emails"],
        "Mobile Numbers": contact_info["mobiles"],
        "Phone Numbers": contact_info["phones"],
    }


def export_vetcove_patients(
    client: InstinctPartnerClient,
    output_path: str,
    *,
    division: str = DIVISION_NAME,
) -> dict[str, int]:
    accounts = build_account_map(client)
    city_zip_map = build_city_zip_map(accounts)
    last_visits = build_last_visit_map(client)

    total_patients = 0
    exported = 0
    skipped_non_living = 0
    missing_last_visit = 0
    missing_contact = 0

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VETCOVE_COLUMNS)
        writer.writeheader()

        for patient in client.iter_patients(limit=100):
            total_patients += 1
            if patient.get("deceasedDate") or patient.get("deletedAt") or patient.get("mergedIntoPatientId"):
                skipped_non_living += 1
                continue

            account_id = normalize_text(patient.get("accountId"))
            account = accounts.get(account_id) or patient.get("account") or {}
            row = patient_to_vetcove_row(
                patient,
                account,
                division=division,
                last_visit=last_visits.get(patient.get("id"), ""),
            )
            row = apply_location_defaults(row, city_zip_map)
            if not row["Last Visit"]:
                missing_last_visit += 1
            if not row["Email Addresses"] and not row["Mobile Numbers"]:
                missing_contact += 1
            writer.writerow(row)
            exported += 1

    return {
        "total_patients": total_patients,
        "exported": exported,
        "skipped_non_living": skipped_non_living,
        "missing_last_visit": missing_last_visit,
        "missing_contact": missing_contact,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Instinct patients into Vetcove CSV format.")
    parser.add_argument("--base-url", default="https://partner.instinctvet.com")
    parser.add_argument("--token", required=True)
    parser.add_argument("--output", default="vetcove_patients.csv")
    parser.add_argument("--division", default=DIVISION_NAME)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    client = InstinctPartnerClient(args.base_url, args.token)
    stats = export_vetcove_patients(client, args.output, division=args.division)
    for key, value in stats.items():
        print(f"{key}={value}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
