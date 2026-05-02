from __future__ import annotations

from scripts.evh_reminder_importer import (
    InstinctApiAdapter,
    ParsedPatientGroup,
    PatientImportPlan,
    ReminderCandidate,
    ReminderQuery,
    build_simulation_payload,
    map_source_label,
)


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


def test_get_reminders_for_patient_filters_paginated_rows(monkeypatch):
    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")

    def fake_iter_reminders(self, *, status=None, due_after=None, due_before=None):
        assert status == "active"
        assert due_after == "2026-01-01"
        assert due_before == "2026-12-31"
        yield {"id": "r1", "patientId": 16558, "deactivatedAt": None, "dueAt": "2026-04-15"}
        yield {"id": "r2", "patientId": 16558, "deactivatedAt": "2026-04-16T00:00:00Z", "dueAt": "2026-05-01"}
        yield {"id": "r3", "patientId": 99999, "deactivatedAt": None, "dueAt": "2026-06-01"}

    monkeypatch.setattr(InstinctApiAdapter, "iter_reminders", fake_iter_reminders)

    reminders = adapter.get_reminders_for_patient(
        ReminderQuery(
            patient_id=16558,
            status="active",
            due_after="2026-01-01",
            due_before="2026-12-31",
        )
    )

    assert reminders == [{"id": "r1", "patientId": 16558, "deactivatedAt": None, "dueAt": "2026-04-15"}]


def test_iter_reminders_uses_metadata_after_cursor(monkeypatch):
    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")
    calls: list[dict[str, object]] = []

    responses = iter(
        [
            {
                "data": [{"id": "r1"}, {"id": "r2"}],
                "metadata": {"after": "cursor-1", "before": None, "limit": 2, "totalCount": 4},
            },
            {
                "data": [{"id": "r3"}, {"id": "r4"}],
                "metadata": {"after": None, "before": "cursor-1", "limit": 2, "totalCount": 4},
            },
        ]
    )

    def fake_get(path, params=None):
        assert path == "/v1/reminders"
        calls.append(dict(params or {}))
        return next(responses)

    monkeypatch.setattr(adapter, "_get", fake_get)

    reminders = list(adapter.iter_reminders(limit=2))

    assert reminders == [{"id": "r1"}, {"id": "r2"}, {"id": "r3"}, {"id": "r4"}]
    assert calls == [
        {"limit": 2},
        {"limit": 2, "pageCursor": "cursor-1", "pageDirection": "after"},
    ]


def test_map_source_label_normalizes_whitespace():
    assert map_source_label("DA2PP + Leptospirosis 4 Annual ") == "DA2P + Leptospirosis 4"
    assert map_source_label("  Dermatonin Implant 8.0mg  ") == "Dermatonin Implant"


def test_find_reminder_label_normalizes_whitespace(monkeypatch):
    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")
    labels = [
        {"id": 1, "label": "DA2P + Leptospirosis 4 "},
        {"id": 2, "label": "Dermatonin Implant"},
    ]

    monkeypatch.setattr(InstinctApiAdapter, "iter_reminder_labels", lambda self, limit=100: iter(labels))

    assert adapter.find_reminder_label("DA2P + Leptospirosis 4") == {"id": 1, "label": "DA2P + Leptospirosis 4 "}
    assert adapter.find_reminder_label("  dermatonin implant  ") == {"id": 2, "label": "Dermatonin Implant"}
    assert adapter.resolve_reminder_label_id("da2p + leptospirosis 4 ") == 1
    assert adapter.resolve_reminder_label_id("DERMATONIN IMPLANT") == 2


def test_build_simulation_payload_uses_valid_reminders_only():
    plan = PatientImportPlan(
        patient=ParsedPatientGroup(
            client="27117",
            client_name="Kathleen Hetherman",
            phone_no="(407) 617-8309",
            patient_name="Ember Hetherman",
            species="Canine",
            breed="Rhodesian Ridgeback",
            header_row_number=6,
        ),
        valid_reminders=[
            ReminderCandidate(
                source_code="A1",
                source_label="DA2PP + Leptospirosis 4 Annual",
                mapped_label="DA2P + Leptospirosis 4",
                due_date="2026-11-01",
                row_number=6,
            )
        ],
    )

    payload = build_simulation_payload(plan)

    assert payload["patient"]["patient_name"] == "Ember Hetherman"
    assert payload["reminders"] == [
        {
            "source_code": "A1",
            "source_label": "DA2PP + Leptospirosis 4 Annual",
            "mapped_label": "DA2P + Leptospirosis 4",
            "due_date": "2026-11-01",
            "row_number": 6,
        }
    ]


def test_add_reminders_merges_existing_ids_and_patches_patient(monkeypatch):
    adapter = InstinctApiAdapter("https://partner.instinctvet.com", "user", "pass")
    patient_record = {"id": 20376, "reminderIds": [40, 51]}
    reminders = [
        ReminderCandidate(
            source_code="A1",
            source_label="DA2PP + Leptospirosis 4 Annual",
            mapped_label="DA2P + Leptospirosis 4",
            due_date="2026-11-01",
            row_number=6,
        ),
        ReminderCandidate(
            source_code="A2",
            source_label="Dermatonin Implant 8.0mg",
            mapped_label="Dermatonin Implant",
            due_date="2026-12-26",
            row_number=7,
        ),
    ]
    patches: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(adapter, "resolve_reminder_label_id", lambda label_text: {"DA2P + Leptospirosis 4": 12, "Dermatonin Implant": 13}[label_text])

    def fake_patch(path, payload):
        patches.append((path, payload))
        return {"ok": True, "path": path, "payload": payload}

    monkeypatch.setattr(adapter, "_patch", fake_patch)

    result = adapter.add_reminders(patient_record, reminders)

    assert result == {"ok": True, "path": "/v1/patients/20376", "payload": {"reminderIds": [40, 51, 12, 13]}}
    assert patches == [("/v1/patients/20376", {"reminderIds": [40, 51, 12, 13]})]
