from __future__ import annotations

import csv
from pathlib import Path

from scripts.export_vetcove_patients import (
    DIVISION_NAME,
    apply_location_defaults,
    collect_contact_details,
    export_vetcove_patients,
    patient_to_vetcove_row,
)


class FakeClient:
    def __init__(self) -> None:
        self._accounts = [
            {
                "id": "acct-1",
                "pimsCode": "C-100",
                "primaryContact": {
                    "nameFirst": "Jane",
                    "nameLast": "Doe",
                    "communicationDetails": [
                        {"type": "full_address", "value": "1111 Lakeshore Dr.  B3,Eustis, FL  32726"},
                        {"type": "phone", "value": "+13525551212"},
                    ],
                },
                "alternateContacts": [
                    {
                        "communicationDetails": [
                            {"type": "email", "value": "jane@example.com"},
                        ]
                    }
                ],
            }
        ]
        self._appointments = [
            {"patientId": 1, "startsAt": "2026-04-20T14:00:00-04:00", "status": "active", "deletedAt": None},
            {"patientId": 1, "startsAt": "2099-04-20T14:00:00-04:00", "status": "active", "deletedAt": None},
        ]
        self._patients = [
            {
                "id": 1,
                "accountId": "acct-1",
                "pimsCode": "P-100",
                "name": "Cadbury",
                "birthdate": "2017-03-06",
                "sexId": "female_spayed",
                "speciesId": "fel",
                "breed": {"label": "Domestic Shorthair"},
                "weight": 7.5,
                "alerts": [{"label": "Anxious"}],
                "deceasedDate": None,
                "deletedAt": None,
                "mergedIntoPatientId": None,
            },
            {
                "id": 2,
                "accountId": "acct-1",
                "pimsCode": "P-200",
                "name": "Ghost",
                "birthdate": "2015-01-01",
                "sexId": "male",
                "speciesId": "can",
                "breed": {"label": "Mixed Breed"},
                "weight": None,
                "alerts": [],
                "deceasedDate": "2026-01-01",
                "deletedAt": None,
                "mergedIntoPatientId": None,
            },
        ]

    def iter_accounts(self, params=None, *, limit=100):
        yield from self._accounts

    def iter_appointments(self, params=None, *, limit=100):
        yield from self._appointments

    def iter_patients(self, params=None, *, limit=100):
        yield from self._patients


def test_collect_contact_details_promotes_phone_to_mobile_if_needed():
    details = collect_contact_details(
        {
            "primaryContact": {
                "communicationDetails": [
                    {"type": "phone", "value": "+13525551212"},
                ]
            }
        }
    )

    assert details["mobiles"] == "3525551212"
    assert details["phones"] == "3525551212"


def test_patient_to_vetcove_row_maps_required_fields():
    patient = {
        "id": 1,
        "accountId": "acct-1",
        "pimsCode": "P-100",
        "name": "Cadbury",
        "birthdate": "2017-03-06",
        "sexId": "female_spayed",
        "speciesId": "fel",
        "breed": {"label": "Domestic Shorthair"},
        "weight": 7.5,
        "alerts": [{"label": "Anxious"}],
    }
    account = {
        "id": "acct-1",
        "pimsCode": "C-100",
        "primaryContact": {
            "nameFirst": "Jane",
            "nameLast": "Doe",
            "communicationDetails": [
                {"type": "full_address", "value": "1111 Lakeshore Dr.  B3,Eustis, FL  32726"},
                {"type": "phone", "value": "+13525551212"},
                {"type": "email", "value": "jane@example.com"},
            ],
        },
    }

    row = patient_to_vetcove_row(patient, account, division=DIVISION_NAME, last_visit="04-20-2026")

    assert row["Division"] == DIVISION_NAME
    assert row["Animal Id"] == "P-100"
    assert row["Animal Name"] == "Cadbury"
    assert row["Animal Weight (lb)"] == "7.50"
    assert row["Date of Birth"] == "03-06-2017"
    assert row["Sex"] == "Female Spayed"
    assert row["Has Passed Away"] == "No"
    assert row["Species"] == "Feline"
    assert row["Breed"] == "Domestic Shorthair"
    assert row["Last Visit"] == "04-20-2026"
    assert row["Owner First Name"] == "Jane"
    assert row["Owner Last Name"] == "Doe"
    assert row["Owner Contact Code"] == "C-100"
    assert row["Physical Address Street 1"] == "1111 Lakeshore Dr. B3"
    assert row["Physical Address City"] == "Eustis"
    assert row["Physical Address Postcode"] == "32726"
    assert row["Physical Address State"] == "FL"
    assert row["Physical Address Country"] == "United States"
    assert row["Email Addresses"] == "jane@example.com"
    assert row["Mobile Numbers"] == "3525551212"
    assert row["Phone Numbers"] == "3525551212"


def test_export_vetcove_patients_writes_only_living_rows(tmp_path: Path):
    output = tmp_path / "vetcove_patients.csv"

    stats = export_vetcove_patients(FakeClient(), str(output))

    with output.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert stats == {
        "total_patients": 2,
        "exported": 1,
        "skipped_non_living": 1,
        "missing_last_visit": 0,
        "missing_contact": 0,
    }
    assert len(rows) == 1
    assert rows[0]["Division"] == DIVISION_NAME
    assert rows[0]["Animal Id"] == "P-100"


def test_apply_location_defaults_prefers_city_zip_map_then_evh_default():
    row = {
        "Physical Address City": "Leesburg",
        "Physical Address State": "",
        "Physical Address Postcode": "",
    }
    updated = apply_location_defaults(row, {"Leesburg": "34788"})
    assert updated["Physical Address City"] == "Leesburg"
    assert updated["Physical Address State"] == "FL"
    assert updated["Physical Address Postcode"] == "34788"

    row2 = {
        "Physical Address City": "",
        "Physical Address State": "",
        "Physical Address Postcode": "",
    }
    updated2 = apply_location_defaults(row2, {})
    assert updated2["Physical Address City"] == "Eustis"
    assert updated2["Physical Address State"] == "FL"
    assert updated2["Physical Address Postcode"] == "32726"
