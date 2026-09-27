"""Explicit runtime dependency coverage for every deployed extraction path."""
import shutil
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
OCR_TOOLS = ("tesseract", "pdftoppm", "pdftocairo", "gs")


def test_local_extraction_runtime_tools_are_complete():
    missing = [tool for tool in OCR_TOOLS if shutil.which(tool) is None]
    assert not missing, f"missing OCR runtime tools: {missing}"


def test_package_contains_python_and_ocr_runtime_contract():
    zip_path = ROOT / "deploy/evh_instinct_rag_import_delta.zip"
    if not zip_path.exists():
        pytest.skip("deployment package has not been built")
    with zipfile.ZipFile(zip_path) as package:
        names = set(package.namelist())
    required_python = {
        "scripts/instinct_pdf_chunker.py",
        "scripts/rag_import_delta_lambda.py",
        "pymupdf/__init__.py",
    }
    missing_python = sorted(required_python - names)
    assert not missing_python, f"package missing Python components: {missing_python}"
    missing_tools = [tool for tool in OCR_TOOLS if not any(
        name == f"bin/{tool}" or name.endswith(f"/{tool}") for name in names
    )]
    assert not missing_tools, f"package missing OCR executables: {missing_tools}"
