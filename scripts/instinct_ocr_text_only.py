#!/home/ggb66/dev/EVH/pony/worktrees/rd/.venv/bin/python
"""OCR deferred Instinct PDFs and print page text only."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.instinct_reprocess_deferred_ocr import _extract_pages_for_reprocess, _file_result_line


def _print(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)


def process_single_file(pdf_path: Path) -> bool:
    pdf_path = pdf_path.expanduser()
    if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
        print(_file_result_line(pdf_id=pdf_path.stem, filename=pdf_path.name, status="missing"), flush=True)
        return False

    pdf_id = pdf_path.stem
    filename = pdf_path.name
    started = time.perf_counter()
    print(_file_result_line(pdf_id=pdf_id, filename=filename, status="ocr_start"), flush=True)
    pages, page_count, page_kind, attempted_ocr = _extract_pages_for_reprocess(pdf_path)
    if attempted_ocr:
        print(_file_result_line(pdf_id=pdf_id, filename=filename, status="ocr_attempted", detail=page_kind), flush=True)
    print(f"--- {pdf_id} {filename} page_count={page_count} kind={page_kind} ---", flush=True)
    for idx, page in enumerate(pages, start=1):
        print(f"[page {idx}] {page}", flush=True)
    elapsed = time.perf_counter() - started
    print(_file_result_line(pdf_id=pdf_id, filename=filename, status="complete", detail=f"pages={page_count} kind={page_kind} elapsed_s={elapsed:.2f}"), flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCR the first N deferred Instinct PDFs and print text only.")
    parser.add_argument("--deferred-pdf-dir", default=str(DATA_ROOT / "instinct-pdfs-deferred"))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    deferred_pdf_dir = Path(args.deferred_pdf_dir).expanduser()
    deferred_pdf_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(path for path in deferred_pdf_dir.glob("*.pdf") if path.is_file() and path.stat().st_size > 0)
    if args.limit:
        pdf_paths = pdf_paths[: args.limit]

    _print("start", files=len(pdf_paths), deferred_pdf_dir=str(deferred_pdf_dir))
    ok = 0
    failed = 0
    for pdf_path in pdf_paths:
        try:
            if process_single_file(pdf_path):
                ok += 1
            else:
                failed += 1
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            failed += 1
            print(_file_result_line(pdf_id=pdf_path.stem, filename=pdf_path.name, status="failed", detail=type(exc).__name__), flush=True)
            _print("failure", pdf_id=pdf_path.stem, filename=pdf_path.name, error_type=type(exc).__name__, error=str(exc))

    _print("done", ocred_count=ok, failed_count=failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
