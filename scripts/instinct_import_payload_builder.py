"""Utilities for building Instinct Partner API patient import payloads.

This module focuses on two import concerns requested by operations:
1. Each patient should be assigned a single alert.
2. Each patient can carry multiple reminders, but we only assign a small, known set.

The builder returns payloads shaped for `POST /v1/patients` and `PATCH /v1/patients/{id}`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ImportDefaults:
    """Static defaults applied to every imported patient."""

    default_alert_id: int
    default_reminder_ids: tuple[int, ...] = field(default_factory=tuple)


class PatientPayloadBuilder:
    """Build Instinct patient payloads with required alert/reminder behavior."""

    def __init__(self, defaults: ImportDefaults) -> None:
        self.defaults = defaults

    def build(self, source_patient: Mapping[str, Any]) -> dict[str, Any]:
        """Build a patient payload from source data."""

        payload: dict[str, Any] = {
            "accountId": source_patient["accountId"],
            "breedId": source_patient["breedId"],
            "name": source_patient["name"],
            "speciesId": source_patient["speciesId"],
        }

        payload["alertIds"] = self._merge_ids(
            source_patient.get("alertIds"),
            [self.defaults.default_alert_id],
        )
        payload["reminderIds"] = self._merge_ids(
            source_patient.get("reminderIds"),
            self.defaults.default_reminder_ids,
        )

        for optional_field in (
            "birthdate",
            "color",
            "deceasedDate",
            "insuranceInfo",
            "microchipInfo",
            "pimsCode",
            "sexId",
        ):
            if optional_field in source_patient and source_patient[optional_field] is not None:
                payload[optional_field] = source_patient[optional_field]

        return payload

    @staticmethod
    def _merge_ids(values: Iterable[int] | None, defaults: Iterable[int]) -> list[int]:
        merged: list[int] = []
        seen: set[int] = set()

        for value in [*(values or []), *defaults]:
            int_value = int(value)
            if int_value not in seen:
                merged.append(int_value)
                seen.add(int_value)

        return merged


if __name__ == "__main__":
    defaults = ImportDefaults(default_alert_id=101, default_reminder_ids=(201, 202, 203))
    builder = PatientPayloadBuilder(defaults)

    sample = {
        "accountId": "9e13d2a0-7ab0-4de7-9982-30e2df8a9f41",
        "breedId": 12,
        "name": "Milo",
        "speciesId": "canine",
    }

    print(builder.build(sample))
