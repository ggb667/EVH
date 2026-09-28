from __future__ import annotations

from scripts import rd_validation_harness as harness


def test_ocr_lifecycle_fixture_reports_terminal_evidence(monkeypatch):
    monkeypatch.setattr(harness, "_ocr_process_snapshot", lambda: {})
    monkeypatch.setattr(
        harness,
        "ocr_pdf_text_pages",
        lambda _path, *, timeout_s: (["ISOLATED OCR LIFECYCLE VALIDATION 12345"], 1, "pdftoppm+tesseract"),
    )

    result = harness.run_ocr_lifecycle({"rd_validation_harness": "ocr-lifecycle-v1"})

    assert result["status"] == "ok"
    assert result["ocr_entered"] is True
    assert result["ocr_exit_status"] == "success"
    assert result["page_count"] == 1
    assert result["chunk_count"] == 1
    assert result["database_status"] == "isolated_no_db_mutation"
    assert result["duplicate_count"] == 0
    assert result["no_child_survived"] is True


def test_ocr_lifecycle_fixture_accepts_clean_timeout(monkeypatch):
    monkeypatch.setattr(harness, "_ocr_process_snapshot", lambda: {})

    def timeout(_path, *, timeout_s):
        raise TimeoutError(f"timed out after {timeout_s}s")

    monkeypatch.setattr(harness, "ocr_pdf_text_pages", timeout)
    result = harness.run_ocr_lifecycle({"rd_validation_harness": "ocr-lifecycle-v1"})

    assert result["status"] == "ok"
    assert result["ocr_exit_status"] == "timeout"
    assert result["no_child_survived"] is True
