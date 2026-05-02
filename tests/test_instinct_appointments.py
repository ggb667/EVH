from __future__ import annotations

from scripts.instinct_appointments import normalize_appointment


def test_normalize_appointment_detects_cancel_and_confirm_state():
    appt = normalize_appointment(
        {
            "id": 42,
            "appointmentTypeId": 7,
            "patientId": 99,
            "startsAt": "2026-05-01T10:00:00Z",
            "updatedAt": "2026-04-20T12:00:00Z",
            "canceledAt": None,
            "isConfirmed": True,
        }
    )

    assert appt.appointment_id == "42"
    assert appt.appointment_type_id == "7"
    assert appt.is_canceled is False
    assert appt.is_confirmed is True
