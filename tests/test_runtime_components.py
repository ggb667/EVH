"""Explicit runtime dependency coverage for every deployed extraction path."""
import re
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
OCR_TOOLS = ("tesseract", "pdftoppm", "pdftocairo", "gs", "pdftotext")


def test_local_extraction_runtime_tools_are_complete():
    missing = [tool for tool in OCR_TOOLS if shutil.which(tool) is None]
    assert not missing, f"missing OCR runtime tools: {missing}"


def test_package_contains_python_and_ocr_runtime_contract(tmp_path):
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
        missing_tools = [tool for tool in OCR_TOOLS if f"bin/{tool}" not in names]
        assert not missing_tools, f"package missing OCR executables: {missing_tools}"
        for tool in OCR_TOOLS:
            mode = package.getinfo(f"bin/{tool}").external_attr >> 16
            assert mode & stat.S_IXUSR, f"bin/{tool} is not executable"
        assert "share/tessdata/eng.traineddata" in names
        assert "OCR_RUNTIME_MANIFEST.txt" in names
        assert "Amazon Linux 2023 x86_64" in package.read("OCR_RUNTIME_MANIFEST.txt").decode()
        forbidden = {
            "lib/libc.so.6",
            "lib/ld-linux-x86-64.so.2",
            "lib/libpthread.so.0",
            "lib/libm.so.6",
            "lib/libdl.so.2",
            "lib/librt.so.1",
        }
        assert not forbidden.intersection(names), "package must use Lambda's glibc core"
        elf_names = sorted(
            name for name in names if name.startswith(("bin/", "lib/")) and not name.endswith("/")
        )
        for name in elf_names:
            target = tmp_path / Path(name).name
            target.write_bytes(package.read(name))
            info = subprocess.run(
                ["readelf", "--version-info", str(target)],
                text=True,
                capture_output=True,
                check=False,
            ).stdout
            assert "GLIBC_ABI_DT_RELR" not in info, f"{name} requires unsupported RELR ABI"
            versions = [
                tuple(map(int, value.split(".")))
                for value in re.findall(r"GLIBC_(\d+\.\d+)", info)
            ]
            assert not versions or max(versions) <= (2, 35), (
                f"{name} requires GLIBC_{'.'.join(map(str, max(versions)))}"
            )
