from __future__ import annotations

from scripts.evh_reminder_importer import InstinctApiAdapter, ParsedPatientGroup


def test_summarize_patient_derives_owner_phone_and_reminder_count(monkeypatch):
    reminder_rows = iter(
        (
            {"patientId": 25038, "id": 10},
            {"patient": {"id": "25038"}, "id": 11},
            {"patientId": 99999, "id": 12},
        )
    )

    monkeypatch.setattr(InstinctApiAdapter, "iter_reminders", lambda self: reminder_rows)

    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")
    summary = adapter.summarize_patient(
        {
            "id": 25038,
            "name": "Max Deschenes",
            "accountId": "acct-1",
            "pimsCode": "25038",
            "account": {
                "primaryContact": {
                    "nameFirst": "Nathan",
                    "nameMiddle": None,
                    "nameLast": "Deschenes",
                    "communicationDetails": [
                        {"type": "email", "value": "nathan@example.com"},
                        {"type": "mobile", "value": "(555) 010-1212"},
                    ],
                }
            },
        }
    )

    assert summary == {
        "client_name": "Nathan Deschenes",
        "patient_name": "Max Deschenes",
        "phone_no": "(555) 010-1212",
        "reminder_count": 2,
        "patient_id": 25038,
        "account_id": "acct-1",
        "pims_code": "25038",
    }


def test_summarize_patient_leaves_reminder_count_unknown_without_patient_links(monkeypatch):
    monkeypatch.setattr(
        InstinctApiAdapter,
        "iter_reminders",
        lambda self: iter(({"id": 10, "label": "Rabies"}, {"id": 11, "label": "DA2P"})),
    )

    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")
    summary = adapter.summarize_patient(
        {
            "id": 1,
            "name": "INSTINCT 1",
            "accountId": "acct-1",
            "pimsCode": "INSTINCT001",
            "account": {"primaryContact": {"nameFirst": "INSTINCT", "nameLast": "TEST"}},
        }
    )

    assert summary["client_name"] == "INSTINCT TEST"
    assert summary["reminder_count"] is None


def test_find_patient_matches_account_by_client_code_then_patient_name(monkeypatch):
    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")
    account_queries: list[dict[str, object]] = []

    def fake_get(path, params=None):
        if path == "/v1/accounts":
            account_queries.append(dict(params or {}))
            if params == {"limit": 100, "pimsCode": "10204"}:
                return {
                    "data": [
                        {
                            "id": "acct-10204",
                            "primaryContact": {"nameFirst": "Kindra", "nameLast": "Abner"},
                        }
                    ]
                }
            if params == {"limit": 100, "pimsId": "10204"}:
                return {"data": []}
        if path == "/v1/patients":
            assert params == {"limit": 100, "accountId": "acct-10204"}
            return {"data": [{"id": 77, "name": "Jack"}, {"id": 78, "name": "Milo"}]}
        if path == "/v1/patients/77":
            return {"id": 77, "name": "Jack", "accountId": "acct-10204", "pimsCode": "PAT-77"}
        raise AssertionError(f"unexpected path {path!r} params={params!r}")

    monkeypatch.setattr(adapter, "_get", fake_get)

    patient = adapter.find_patient(
        ParsedPatientGroup(
            client="10204",
            client_name="Abner, Kindra",
            phone_no="(352) 636-2110",
            patient_name="Jack",
            species="Canine",
            breed="Australian Shepherd",
            header_row_number=2,
        )
    )

    assert patient == {"id": 77, "name": "Jack", "accountId": "acct-10204", "pimsCode": "PAT-77"}
    assert account_queries == [
        {"limit": 100, "pimsCode": "10204"},
        {"limit": 100, "pimsId": "10204"},
    ]


def test_find_patient_falls_back_to_owner_name_and_phone(monkeypatch):
    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")

    account_queries: list[dict[str, object]] = []

    def fake_get(path, params=None):
        if path == "/v1/accounts":
            account_queries.append(dict(params or {}))
            if params == {"limit": 100, "pimsCode": "99999"}:
                return {"data": []}
            if params == {"limit": 100, "pimsId": "99999"}:
                return {"data": []}
            if params == {"limit": 100, "name": "Nathan Deschenes"}:
                return {
                    "data": [
                        {
                            "id": "acct-other",
                            "primaryContact": {
                                "nameFirst": "Nathan",
                                "nameLast": "Deschenes",
                                "communicationDetails": [{"type": "mobile", "value": "(555) 000-0000"}],
                            },
                        },
                        {
                            "id": "acct-match",
                            "primaryContact": {
                                "nameFirst": "Nathan",
                                "nameLast": "Deschenes",
                                "communicationDetails": [{"type": "mobile", "value": "(352) 636-2110"}],
                            },
                        },
                    ]
                }
        if path == "/v1/patients":
            assert params == {"limit": 100, "accountId": "acct-match"}
            return {"data": [{"id": 25038, "name": "Max Deschenes"}]}
        if path == "/v1/patients/25038":
            return {"id": 25038, "name": "Max Deschenes", "accountId": "acct-match"}
        raise AssertionError(f"unexpected path {path!r} params={params!r}")

    monkeypatch.setattr(adapter, "_get", fake_get)

    patient = adapter.find_patient(
        ParsedPatientGroup(
            client="99999",
            client_name="Nathan Deschenes",
            phone_no="352-636-2110",
            patient_name="Max Deschenes",
            species="Canine",
            breed="German Shepherd Dog",
            header_row_number=8090,
        )
    )

    assert patient["id"] == 25038
    assert account_queries == [
        {"limit": 100, "pimsCode": "99999"},
        {"limit": 100, "pimsId": "99999"},
        {"limit": 100, "name": "Nathan Deschenes"},
    ]
