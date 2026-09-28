import pytest

from scripts.rag_import_delta_lambda import (
    _cancelled_run_response,
    _merge_final_method_counts,
    _parse_exact_document_target,
    _parse_target_mode,
    _run_is_cancelled,
)


def test_final_method_counts_merge_across_continuation_segments():
    assert _merge_final_method_counts(
        {"pypdf": 2, "gs": 1},
        {"pypdf": 3, "pdftotext": 4},
    ) == {"gs": 1, "pdftotext": 4, "pypdf": 5}
    assert _merge_final_method_counts(None, {}, {"": 9, "gs": 0, "pypdf": "2"}) == {"pypdf": 2}


class _CancellationCursor:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.row


def test_run_cancellation_lookup_is_durable_and_parameterized():
    cur = _CancellationCursor((1,))
    assert _run_is_cancelled(cur, "rd-123") is True
    assert cur.executed == [
        ("SELECT 1 FROM public.rag_import_cancelled_run WHERE run_id=%s", ("rd-123",))
    ]
    assert _run_is_cancelled(cur, "") is False


def test_cancelled_run_response_is_terminal():
    response = _cancelled_run_response("rd-123")
    assert response["statusCode"] == 410
    assert response["headers"]["content-type"] == "application/json; charset=utf-8"
    assert response["body"] == '{"error": "RUN_CANCELLED", "run_id": "rd-123"}'


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
