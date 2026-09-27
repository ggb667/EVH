"""Isolated PDF/OCR worker for Lambda; communicates only over stdio pipes."""
import json
import sys
from pathlib import Path

# Executing this file by absolute path makes Python place ``scripts/`` rather
# than the package root on sys.path.  Add the deployment root explicitly so
# the worker imports reliably even when Lambda's inherited cwd/PYTHONPATH is
# not available to the child process.
package_root = Path(__file__).resolve().parent.parent
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))

from scripts.instinct_pdf_chunker import (
    NoTextLayerError,
    _extract_pdf_text_pages_impl,
    _ocr_pdf_text_pages_impl,
)


def main() -> int:
    kind, pdf_input = sys.argv[1], sys.argv[2]
    try:
        if kind == "extract":
            pages, page_count = _extract_pdf_text_pages_impl(pdf_input)
            result = {"pages": pages, "page_count": page_count}
        elif kind == "ocr":
            pages, page_count, tool = _ocr_pdf_text_pages_impl(pdf_input)
            result = {"pages": pages, "page_count": page_count, "tool": tool}
        else:
            raise ValueError(f"unknown child kind: {kind}")
        print(json.dumps(["ok", result]), flush=True)
    except NoTextLayerError as exc:
        print(json.dumps(["no_text", {"page_count": exc.page_count}]), flush=True)
    except Exception as exc:
        print(json.dumps(["err", {"error_type": type(exc).__name__, "error": str(exc)}]), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
