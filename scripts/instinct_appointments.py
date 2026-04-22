from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


@dataclass(frozen=True)
class NormalizedAppointment:
    appointment_id: str
    appointment_type_id: Optional[str]
    patient_id: Optional[str]
    starts_at: Optional[str]
    updated_at: Optional[str]
    is_canceled: bool
    is_confirmed: Optional[bool]


def normalize_appointment(appointment: dict[str, Any]) -> NormalizedAppointment:
    return NormalizedAppointment(
        appointment_id=normalize_text(appointment.get("id")),
        appointment_type_id=normalize_text(appointment.get("appointmentTypeId")) or None,
        patient_id=normalize_text(appointment.get("patientId")) or None,
        starts_at=normalize_text(appointment.get("startsAt")) or None,
        updated_at=normalize_text(appointment.get("updatedAt")) or None,
        is_canceled=bool(appointment.get("canceledAt") or appointment.get("status") == "canceled"),
        is_confirmed=appointment.get("isConfirmed"),
    )
