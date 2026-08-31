import json
from pathlib import Path

from scripts.import_new_or_changed_pdfs import (
    PdfRecord,
    PdfSource,
    SignatureProbe,
    load_pdf_sources,
    should_download,
)


def test_load_pdf_sources_filters_to_required_fields(tmp_path: Path):
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "client_id": "c-1",
                    "patient_id": "p-1",
                    "pdf_id": "pdf-1",
                    "url": "https://example.test/a.pdf",
                    "etag": '"abc"',
                    "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                    "content_length": 123,
                }
            ]
        ),
        encoding="utf-8",
    )

    sources = load_pdf_sources(manifest_path)

    assert sources == [
        PdfSource(
            client_id="c-1",
            patient_id="p-1",
            pdf_id="pdf-1",
            url="https://example.test/a.pdf",
            filename=None,
            etag='"abc"',
            last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
            content_length=123,
        )
    ]


def test_should_download_skips_when_signature_matches():
    source = PdfSource(
        client_id="c-1",
        patient_id="p-1",
        pdf_id="pdf-1",
        url="https://example.test/a.pdf",
    )
    probe = SignatureProbe(
        etag='"abc"',
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
        content_length=123,
        content_type="application/pdf",
    )
    existing = PdfRecord(
        pdf_id="pdf-1",
        url="https://example.test/a.pdf",
        filename="a.pdf",
        signature='etag="abc"|last_modified=Wed, 01 Jan 2025 00:00:00 GMT|content_length=123',
        etag='"abc"',
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
        content_length=123,
        sha256="deadbeef",
        local_path="/tmp/a.pdf",
        updated_at="2025-01-01 00:00:00",
    )

    assert should_download(source, probe, existing) is False


def test_should_download_fetches_when_no_record_exists():
    source = PdfSource(
        client_id="c-1",
        patient_id="p-1",
        pdf_id="pdf-1",
        url="https://example.test/a.pdf",
    )
    probe = SignatureProbe(etag=None, last_modified=None, content_length=None, content_type=None)

    assert should_download(source, probe, None) is True
