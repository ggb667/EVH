from scripts.instinct_test_account_check import (
    _build_initial_visit,
    _extract_object_id,
    _extract_rows,
)


def test_extract_object_id_from_common_response_shapes():
    assert _extract_object_id({"id": "patient-1"}) == "patient-1"
    assert _extract_object_id({"data": {"patientId": 42}}) == "42"
    assert _extract_object_id({"result": {"uuid": "abc"}}) == "abc"


def test_extract_rows_supports_list_and_wrapped_data_shapes():
    direct = _extract_rows([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    wrapped = _extract_rows({"data": [{"id": 3, "name": "C"}]})

    assert [row["id"] for row in direct] == [1, 2]
    assert [row["id"] for row in wrapped] == [3]


def test_build_initial_visit_includes_required_fields_and_optional_type():
    payload = _build_initial_visit(
        account_id="acc-1",
        patient_id="patient-1",
        visit_reason="initial",
        visit_type_id=7,
    )

    assert payload["accountId"] == "acc-1"
    assert payload["patientId"] == "patient-1"
    assert payload["notes"] == "initial"
    assert payload["visitTypeId"] == 7
    assert "startedAt" in payload
