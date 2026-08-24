from scripts.instinct_alert_weight_etl import (
    WorkbookRow,
    build_patient_patch_payload,
    map_alert_text,
)


def test_map_alert_text_returns_clean_alert_ids_only():
    mapped = map_alert_text("Will Bite. Needs muzzle. Go slow.")

    assert mapped.alert_ids == (215, 284, 209)
    assert mapped.pattern_names == ("will_bite", "needs_muzzle", "go_slow")


def test_map_alert_text_ignores_non_alert_free_text():
    mapped = map_alert_text("Possible Lepto reaction. Split vaccines.")

    assert mapped.alert_ids == ()
    assert mapped.pattern_names == ()


def test_build_patient_patch_payload_merges_alerts_and_weight():
    payload = build_patient_patch_payload(
        {
            "accountId": "acc-1",
            "breedId": 12,
            "name": "bob",
            "speciesId": "fel",
            "sexId": "male",
            "pimsCode": "FE261",
            "color": "Green on Black",
            "birthdate": "2014-04-07",
            "weight": 6.0,
            "alerts": [{"id": 215}],
        },
        mapped_alert_ids=(284,),
        weight=7.25,
    )

    assert payload["alertIds"] == [215, 284]
    assert payload["weight"] == 7.25
    assert payload["pimsCode"] == "FE261"


def test_workbook_row_shape_supports_weight_or_alerts():
    row = WorkbookRow(
        account_pims_code="10204",
        patient_name="Jack",
        weight=63.8,
        alert_text="Will Bite",
        source_row=7,
    )

    assert row.account_pims_code == "10204"
    assert row.patient_name == "Jack"
    assert row.weight == 63.8
