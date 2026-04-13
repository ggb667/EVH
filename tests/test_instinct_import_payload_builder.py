from scripts.instinct_import_payload_builder import ImportDefaults, PatientPayloadBuilder


def test_build_includes_required_default_alert_and_optional_fields():
    builder = PatientPayloadBuilder(ImportDefaults(default_alert_id=101, default_reminder_ids=(201, 202)))

    payload = builder.build(
        {
            "accountId": "acc-1",
            "breedId": 12,
            "name": "Milo",
            "speciesId": "canine",
            "birthdate": "2021-01-01",
        }
    )

    assert payload["alertIds"] == [101]
    assert payload["reminderIds"] == [201, 202]
    assert payload["birthdate"] == "2021-01-01"


def test_build_merges_and_deduplicates_ids_preserving_source_order():
    builder = PatientPayloadBuilder(ImportDefaults(default_alert_id=101, default_reminder_ids=(201, 202)))

    payload = builder.build(
        {
            "accountId": "acc-1",
            "breedId": 12,
            "name": "Milo",
            "speciesId": "canine",
            "alertIds": [999, 101, 999],
            "reminderIds": [777, 202],
        }
    )

    assert payload["alertIds"] == [999, 101]
    assert payload["reminderIds"] == [777, 202, 201]
