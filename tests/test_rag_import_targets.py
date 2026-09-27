import pytest

from scripts.rag_import_delta_lambda import _parse_target_mode


def test_patient_target_defaults_batch():
    assert _parse_target_mode({"patient_limit": 1000, "patient_batch": 100}) == ("patient", 1000, 100)


def test_client_target_uses_client_batch():
    assert _parse_target_mode({"client_limit": 1000, "client_batch": 100}) == ("client", 1000, 100)


def test_full_target():
    assert _parse_target_mode({"process_all": True}) == ("full", None, 500)


@pytest.mark.parametrize("event", [
    {"process_all": True, "patient_limit": 1},
    {"process_all": True, "client_limit": 1},
    {"patient_limit": 1, "client_limit": 1},
])
def test_target_modes_are_mutually_exclusive(event):
    with pytest.raises(ValueError):
        _parse_target_mode(event)
