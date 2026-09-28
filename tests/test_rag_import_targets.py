import pytest

from scripts.rag_import_delta_lambda import _parse_exact_document_target, _parse_target_mode


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


def test_exact_document_target_requires_numeric_pair():
    assert _parse_exact_document_target(
        {"target_patient_id": "183", "target_document_pdf_id": "134819"}
    ) == ("183", "134819")

    with pytest.raises(ValueError):
        _parse_exact_document_target({"target_patient_id": "183"})
    with pytest.raises(ValueError):
        _parse_exact_document_target({"target_patient_id": "183", "target_document_pdf_id": "not-a-pdf-id"})


@pytest.mark.parametrize("selector", [
    {"patient_limit": 1},
    {"client_limit": 1},
    {"process_all": True},
    {"start_patient": 128},
])
def test_exact_document_target_rejects_bulk_or_positional_selectors(selector):
    with pytest.raises(ValueError):
        _parse_exact_document_target({
            "target_patient_id": "183",
            "target_document_pdf_id": "134819",
            **selector,
        })
