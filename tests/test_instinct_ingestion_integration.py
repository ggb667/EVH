"""Local integration coverage for the real document extraction utilities.

The test uses the checked-in text-layer PDF and derives an image-only PDF plus a
DOCX fixture locally. It exercises every configured text-layer extractor and
OCR path without touching Postgres or AWS.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.instinct_pdf_chunker import (
    PatientPdfSource,
    _ocr_pdf_text_pages_impl,
    _extract_with_pymupdf,
    _extract_word_text_pages,
    _read_pdf_text_from_path,
    extract_pdf_text_pages,
    ocr_pdf_text_pages,
    safe_extract_pdf_text_pages,
)

ROOT = Path(__file__).parents[1]
TEXT_PDF = ROOT / "rd-first.pdf"


@pytest.fixture
def sample_documents(tmp_path: Path) -> dict[str, Path]:
    if not TEXT_PDF.exists():
        pytest.skip("checked-in sample PDF is unavailable")
    if not shutil.which("pdftoppm") or not shutil.which("convert"):
        pytest.skip("pdftoppm and ImageMagick are required")

    text_pdf = tmp_path / "text-sample.pdf"
    writer = PdfWriter()
    source_pages = PdfReader(str(TEXT_PDF)).pages
    for page in source_pages[:3]:
        writer.add_page(page)
    with text_pdf.open("wb") as handle:
        writer.write(handle)

    image_root = tmp_path / "ocr-page"
    subprocess.run(
        ["pdftoppm", "-png", str(text_pdf), str(image_root)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    image_pdf = tmp_path / "ocr-sample.pdf"
    subprocess.run(["convert", *map(str, sorted(tmp_path.glob("ocr-page-*.png"))), str(image_pdf)], check=True)

    docx = tmp_path / "sample.docx"
    generated = tmp_path / "sample.docx"
    document_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>
<w:p><w:r><w:t>DOC integration fixture</w:t></w:r></w:p>
<w:p><w:r><w:t>Patient has a documented visit.</w:t></w:r></w:p>
</w:body></w:document>"""
    content_types = """<?xml version='1.0' encoding='UTF-8'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>"""
    with zipfile.ZipFile(generated, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", """<?xml version='1.0' encoding='UTF-8'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/></Relationships>""")
        archive.writestr("word/_rels/document.xml.rels", "<?xml version='1.0' encoding='UTF-8'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'></Relationships>")
        archive.writestr("word/document.xml", document_xml)
    return {"text_pdf": text_pdf, "ocr_pdf": image_pdf, "docx": docx}


def test_text_layer_extractors_and_largest_output(sample_documents):
    path = sample_documents["text_pdf"]
    pdftotext_pages, _ = safe_extract_pdf_text_pages(path, timeout_s=120)
    pypdf_pages, _ = extract_pdf_text_pages(path, timeout_s=120)
    pymupdf_pages, _ = _extract_with_pymupdf(path)
    assert sum(map(len, pdftotext_pages)) > 0
    assert sum(map(len, pypdf_pages)) > 0
    assert sum(map(len, pymupdf_pages)) > 0
    assert len(pdftotext_pages) >= 3
    pages, page_count, winner = _read_pdf_text_from_path(path)
    assert page_count > 0
    assert winner in {"pdftotext", "pypdf", "pymupdf"}
    assert len("".join(pages)) == max(map(lambda p: sum(map(len, p[0])), ((pdftotext_pages, "pdftotext"), (pypdf_pages, "pypdf"), (pymupdf_pages, "pymupdf"))))


def test_ocr_extractor_on_image_only_pdf(sample_documents, capsys):
    pages, page_count, method = _ocr_pdf_text_pages_impl(str(sample_documents["ocr_pdf"]), timeout_s=180)
    assert page_count >= 3
    assert len(pages) >= 3
    assert sum(map(len, pages)) > 0
    assert method
    captured = capsys.readouterr().out
    assert "pdftoppm=1" in captured
    assert "pdftocairo=1" in captured
    assert "gs=1" in captured
    assert "tesseract=3" in captured


def test_doc_extractor(sample_documents, monkeypatch):
    monkeypatch.setattr("scripts.instinct_pdf_chunker._detect_word_parser", lambda: ("libreoffice", shutil.which("libreoffice")))
    pages, page_count, parser = _extract_word_text_pages(
        PatientPdfSource(patient_id="test", patient_name="Test", pdf_path=sample_documents["docx"])
    )
    assert page_count >= 1
    assert "DOC integration fixture" in "\n".join(pages)
    assert parser
