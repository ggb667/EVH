"""Explicit, no-DB deployed extraction harness. Never used by normal ingest."""
from __future__ import annotations

import json
import queue
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

import pymupdf

from scripts.instinct_pdf_chunker import (
    PatientPdfSource,
    _extract_word_text_pages,
    _extract_pdf_text_pages_impl,
    _extract_with_pymupdf,
    _ocr_pdf_text_pages_impl,
    _pdftotext_extract_worker,
)


def _extract_with_pdftotext(pdf_path: Path, *, timeout_s: int = 120) -> tuple[list[str], int]:
    result_queue: queue.Queue = queue.Queue()
    _pdftotext_extract_worker(str(pdf_path), timeout_s, result_queue)
    status, payload = result_queue.get_nowait()
    if status == "ok":
        pages = [str(page).strip() for page in payload.get("pages", [])]
        return pages, int(payload.get("page_count") or len(pages))
    if status == "no_text":
        raise RuntimeError(f"pdftotext produced no text: {payload}")
    raise RuntimeError(f"pdftotext failed: {payload}")


def run(event: dict) -> dict:
    if event.get("rd_validation_harness") != "8-path-v1":
        raise PermissionError("explicit rd_validation_harness=8-path-v1 required")
    packaged_fixture = Path(__file__).resolve().parent.parent / "rd-first.pdf"
    if not packaged_fixture.exists():
        raise FileNotFoundError("rd-first.pdf fixture missing from Lambda package")
    results = []
    with tempfile.TemporaryDirectory(prefix="rd-8-path-") as temp:
        root = Path(temp)
        fixture = root / "rd-first.pdf"
        shutil.copy2(packaged_fixture, fixture)
        image_pdf = root / "image-only.pdf"
        docx = root / "fixture.docx"
        with zipfile.ZipFile(docx, "w") as archive:
            archive.writestr("word/document.xml", "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>Real DOCX harness fixture.</w:t></w:r></w:p></w:body></w:document>")
        src = pymupdf.open(str(fixture)); out = pymupdf.open()
        for page in src:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            target = out.new_page(width=pix.width, height=pix.height)
            target.insert_image(target.rect, stream=pix.tobytes("png"))
        out.save(str(image_pdf)); out.close(); src.close()
        doc_source = PatientPdfSource(pdf_id=0, patient_id=0, patient_name="harness", pdf_path=docx)
        cases = [
            ("DOC", lambda: _extract_word_text_pages(doc_source)),
            ("PDF_TEXT_pdftotext", lambda: _extract_with_pdftotext(fixture, timeout_s=120)),
            ("PDF_TEXT_pypdf", lambda: _extract_pdf_text_pages_impl(str(fixture))),
            ("PDF_TEXT_pymupdf", lambda: _extract_with_pymupdf(fixture)),
        ]
        for name, fn in cases:
            started = time.perf_counter()
            try:
                value = fn(); pages = value[0]
                results.append({"path": name, "status": "success", "pages": len(pages), "chars": sum(map(len, pages)), "seconds": round(time.perf_counter()-started, 3)})
            except Exception as exc:
                results.append({"path": name, "status": "failure", "error_type": type(exc).__name__, "error": str(exc), "seconds": round(time.perf_counter()-started, 3)})
        for renderer in ("pdftoppm", "pdftocairo", "gs"):
            started = time.perf_counter()
            try:
                pages, count, used = _ocr_pdf_text_pages_impl(str(image_pdf), timeout_s=120, only_renderer=renderer)
                results.append({"path": f"OCR_{renderer}", "status": "success", "renderer": used, "pages": count, "chars": sum(map(len, pages)), "seconds": round(time.perf_counter()-started, 3)})
            except Exception as exc:
                results.append({"path": f"OCR_{renderer}", "status": "failure", "error_type": type(exc).__name__, "error": str(exc), "seconds": round(time.perf_counter()-started, 3)})
    failures = [row for row in results if row.get("status") != "success"]
    return {"status": "ok" if not failures else "failed", "harness": "8-path-v1", "success_count": len(results) - len(failures), "failure_count": len(failures), "results": results}
