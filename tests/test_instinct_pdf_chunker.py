import json
import sys
import types
from io import BytesIO
from pathlib import Path

import pytest
from langchain_core.documents import Document

from scripts.instinct_pdf_chunker import (
    ChunkingConfig,
    DetectedTerm,
    DictionaryTerm,
    NoTextLayerError,
    PatientPdfSource,
    chunk_patient_pdf,
    generate_veterinary_clinical_summary,
    detect_terms_in_text,
    extract_pdf_text_pages,
    load_patient_manifest,
    load_term_index,
    print_chunk_metadata,
    _extract_openai_api_key_from_secret_payload,
    _openai_api_key,
    _read_pdf_text_from_path,
    ocr_pdf_text_pages,
)


def test_load_patient_manifest_accepts_required_fields(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        """
        [
          {"patient_id": "12", "patient_name": "Milo", "pdf_path": "milo.pdf"},
          {"id": "34", "name": "Mia", "pdf": "mia.pdf"}
        ]
        """,
        encoding="utf-8",
    )

    entries = load_patient_manifest(manifest_path)

    assert entries == [
        PatientPdfSource(patient_id="12", patient_name="Milo", pdf_path=Path("milo.pdf")),
        PatientPdfSource(patient_id="34", patient_name="Mia", pdf_path=Path("mia.pdf")),
    ]


def test_extract_pdf_text_pages_raises_when_text_layer_missing():
    class FakePage:
        def extract_text(self, extraction_mode=None):
            return ""

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage(), FakePage()]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("scripts.instinct_pdf_chunker.PdfReader", FakeReader)
    try:
        with pytest.raises(NoTextLayerError):
            extract_pdf_text_pages(b"%PDF-1.4 fake")
    finally:
        monkeypatch.undo()


def test_text_route_exhaustion_waits_for_all_methods_and_preserves_page_count(tmp_path, monkeypatch, capsys):
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"not-used")
    calls = []

    def fail(name):
        def run(*args, **kwargs):
            calls.append(name)
            raise NoTextLayerError(3)
        return run

    monkeypatch.setattr("scripts.instinct_pdf_chunker.safe_extract_pdf_text_pages", fail("pdftotext"))
    monkeypatch.setattr("scripts.instinct_pdf_chunker._extract_pdf_text_pages_impl", fail("pypdf"))
    monkeypatch.setattr("scripts.instinct_pdf_chunker._extract_with_pymupdf", fail("pymupdf"))
    with pytest.raises(NoTextLayerError) as raised:
        _read_pdf_text_from_path(pdf_path)

    assert calls == ["pdftotext", "pypdf", "pymupdf"]
    assert raised.value.page_count == 3
    assert '"status": "extraction_route_exhausted"' in capsys.readouterr().out


def test_ocr_timeout_is_reported_and_propagated(tmp_path, monkeypatch, capsys):
    pdf_path = tmp_path / "image.pdf"
    pdf_path.write_bytes(b"pdf")

    def timeout(*args, **kwargs):
        raise TimeoutError("ocr child timed out")

    monkeypatch.setattr("scripts.instinct_pdf_chunker._run_child_process", timeout)
    with pytest.raises(TimeoutError, match="ocr child timed out"):
        ocr_pdf_text_pages(pdf_path, timeout_s=1)
    assert '"stage": "ocr"' in capsys.readouterr().out


def test_detect_terms_in_text_uses_aliases():
    term = DictionaryTerm(
        term_type="medication",
        canonical_name="Carprofen",
        aliases=("Carprofen", "Rimadyl"),
        category="evh-medications",
    )

    hits = detect_terms_in_text("Rimadyl was dispensed twice. rimadyl again.", [term], page_number=2)

    assert len(hits) == 1
    assert hits[0].canonical_name == "Carprofen"
    assert hits[0].count == 2


def test_chunk_patient_pdf_builds_enriched_documents(monkeypatch):
    source = PatientPdfSource(
        patient_id="11525",
        patient_name="Emmett Bleu (#4)",
        pdf_path=Path("/tmp/sample.pdf"),
        pdf_url=None,
    )
    pages = ["Carprofen was prescribed. Recheck in 2 weeks."]

    monkeypatch.setattr("scripts.instinct_pdf_chunker.read_pdf_text_from_source", lambda _source: (pages, 1))
    monkeypatch.setattr(
        "scripts.instinct_pdf_chunker.load_term_index",
        lambda dictionary_csv=None, term_types=None: [
            DictionaryTerm("medication", "Carprofen", ("Carprofen", "Rimadyl"), "evh-medications", 0.9),
            DictionaryTerm("treatment", "Recheck", ("recheck",), "evh-treatments", 0.9),
        ],
    )

    docs, page_count = chunk_patient_pdf(source, ChunkingConfig(chunk_size=20, chunk_overlap=2))

    assert page_count == 1
    assert docs
    assert docs[0].metadata["clinical_summary"]
    assert docs[0].metadata["clinical_summary_style"] == "clinical_summary"
    assert "Carprofen" in docs[0].metadata["term_summary"]["medication"]
    assert any(hit["canonical_name"] == "Recheck" for hit in docs[0].metadata["full_pdf_detected_terms"])
    assert "table_records" not in docs[0].metadata


def test_generate_veterinary_clinical_summary_switches_to_history_style():
    source = PatientPdfSource(
        patient_id="11525",
        patient_name="Emmett Bleu (#4)",
    )
    pages = [f"Page {i} with Carprofen and Recheck." for i in range(1, 10)]
    summary = generate_veterinary_clinical_summary(
        source,
        pages,
        [
            DetectedTerm(
                term_type="medication",
                canonical_name="Carprofen",
                matched_text="Carprofen",
                page_number=1,
                count=1,
                confidence=0.9,
            )
        ],
    )

    assert "Patient history summary" in summary
    assert "History signals:" in summary
    assert "Historical excerpt:" in summary


def test_generate_veterinary_clinical_summary_short_pdf_is_concise():
    source = PatientPdfSource(
        patient_id="11525",
        patient_name="Emmett Bleu (#4)",
    )
    summary = generate_veterinary_clinical_summary(
        source,
        ["Carprofen was prescribed. Recheck in 2 weeks."],
        [],
    )

    assert summary.startswith("Clinical summary for Emmett Bleu (#4) (11525) from 1 page(s).")
    assert "Clinical excerpt:" in summary


def test_generate_veterinary_clinical_summary_includes_table_rows():
    source = PatientPdfSource(
        patient_id="11525",
        patient_name="Emmett Bleu (#4)",
    )
    pages = [
        """CodeName Manufacture Lot Number Tag Issued Date Expiration Provider Description Comments
RK MERIA 22144 0906-25 8/25/2025 8/25/2026 Christine B. Cassidy, DVM Imrab 1 Rabies Canine 1yr, A FEW PETS EXPERIENCE SOME LETHARGY AND SORENESS""",
    ]

    summary = generate_veterinary_clinical_summary(
        source,
        pages,
        [
            DetectedTerm(
                term_type="medication",
                canonical_name="Imrab 1 Rabies Canine 1yr",
                matched_text="Imrab 1 Rabies Canine 1yr",
                page_number=1,
                count=1,
                confidence=0.9,
            )
        ],
    )

    assert "Table rows:" in summary
    assert "RK" in summary
    assert "Christine B. Cassidy, DVM" in summary
    assert "Imrab 1 Rabies Canine 1yr" in summary


def test_chunk_patient_pdf_keeps_table_records_out_of_chunk_metadata(monkeypatch):
    source = PatientPdfSource(
        patient_id="11525",
        patient_name="Emmett Bleu (#4)",
        pdf_path=Path("/tmp/sample.pdf"),
        pdf_url=None,
    )
    pages = [
        """CodeName Manufacture Lot Number Tag Issued Date Expiration Provider Description Comments
RK MERIA 22144 0906-25 8/25/2025 8/25/2026 Christine B. Cassidy, DVM Imrab 1 Rabies Canine 1yr, A FEW PETS EXPERIENCE SOME LETHARGY AND SORENESS""",
    ]

    monkeypatch.setattr("scripts.instinct_pdf_chunker.read_pdf_text_from_source", lambda _source: (pages, 1))
    monkeypatch.setattr(
        "scripts.instinct_pdf_chunker.load_term_index",
        lambda dictionary_csv=None, term_types=None: [
            DictionaryTerm("medication", "Imrab 1 Rabies Canine 1yr", ("Imrab 1 Rabies Canine 1yr",), "evh-medications", 0.9),
        ],
    )

    docs, _ = chunk_patient_pdf(source, ChunkingConfig(chunk_size=20, chunk_overlap=2))

    assert "table_records" not in docs[0].metadata


def test_chunk_patient_pdf_stores_table_records_on_source_document(monkeypatch):
    source = PatientPdfSource(
        patient_id="11525",
        patient_name="Emmett Bleu (#4)",
        pdf_path=Path("/tmp/sample.pdf"),
        pdf_url=None,
    )
    pages = [
        """CodeName Manufacture Lot Number Tag Issued Date Expiration Provider Description Comments
RK MERIA 22144 0906-25 8/25/2025 8/25/2026 Christine B. Cassidy, DVM Imrab 1 Rabies Canine 1yr, A FEW PETS EXPERIENCE SOME LETHARGY AND SORENESS""",
    ]

    monkeypatch.setattr("scripts.instinct_pdf_chunker.read_pdf_text_from_source", lambda _source: (pages, 1))
    monkeypatch.setattr(
        "scripts.instinct_pdf_chunker.load_term_index",
        lambda dictionary_csv=None, term_types=None: [
            DictionaryTerm("medication", "Imrab 1 Rabies Canine 1yr", ("Imrab 1 Rabies Canine 1yr",), "evh-medications", 0.9),
        ],
    )

    docs, _ = chunk_patient_pdf(source, ChunkingConfig(chunk_size=20, chunk_overlap=2))

    assert docs[0].metadata["full_pdf_detected_terms"]
    assert docs[0].metadata["term_summary"]


def test_print_chunk_metadata_outputs_preview(capsys):
    doc = Document(
        page_content="Apoquel given daily",
        metadata={
            "patient_id": "11525",
            "patient_name": "Emmett Bleu (#4)",
            "page_number": 1,
            "chunk_index": 1,
            "source": "instinct-patient-pdf",
            "clinical_summary": "Clinical summary: example",
            "term_summary": {"medication": ["Apoquel"]},
            "detected_terms": [],
        },
    )

    print_chunk_metadata([doc])

    out = capsys.readouterr().out
    assert "chunk_index" in out
    assert "Apoquel given daily" in out


def test_load_term_index_prefers_database(monkeypatch):
    monkeypatch.setattr(
        "scripts.instinct_pdf_chunker._aws_data_api_query",
        lambda sql: [
            {"canonical_name": "Carprofen", "aliases": '["Carprofen","Rimadyl"]', "term_type": "medication", "category": "evh-medications", "confidence_score": "0.9"},
            {"canonical_name": "Dental cleaning", "aliases": '["Dental cleaning"]', "term_type": "treatment", "category": "evh-treatments", "confidence_score": "0.8"},
        ]
        if "FROM rag_dictionary_term" in sql and "JOIN" not in sql
        else [],
    )

    terms = load_term_index()

    assert {term.canonical_name for term in terms} >= {"Carprofen", "Dental cleaning"}


def test_openai_api_key_secret_payload_accepts_plain_or_json():
    assert _extract_openai_api_key_from_secret_payload("sk-test") == "sk-test"
    assert _extract_openai_api_key_from_secret_payload(json.dumps({"OPENAI_API_KEY": "sk-json"})) == "sk-json"
    assert _extract_openai_api_key_from_secret_payload(json.dumps({"api_key": "sk-api"})) == "sk-api"


def test_openai_api_key_can_resolve_secret_arn_without_logging_value(monkeypatch):
    import scripts.instinct_pdf_chunker as chunker

    class FakeSecretsClient:
        def get_secret_value(self, *, SecretId):
            assert SecretId == "arn:test:openai"
            return {"SecretString": json.dumps({"OPENAI_API_KEY": "sk-from-secret"})}

    fake_boto3 = types.SimpleNamespace(client=lambda service: FakeSecretsClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_SECRET_ARN", "arn:test:openai")
    monkeypatch.setattr(chunker, "_OPENAI_API_KEY_CACHE", None)

    assert _openai_api_key() == "sk-from-secret"
