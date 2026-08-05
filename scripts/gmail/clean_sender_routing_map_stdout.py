#!/usr/bin/env python3
"""Extract the final JSON artifact from a sender-routing-map stdout capture.

This helper is for mixed stdout captures that include:
- OAuth prompts
- progress dots
- per-message live lines
- and finally the pretty-printed JSON artifact

It scans for the last balanced JSON object in the file and writes it to the
requested output path. If no complete JSON object is present, it exits non-zero
so the caller knows the capture was still partial.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def extract_last_json_object(text: str) -> str | None:
    start = None
    depth = 0
    in_string = False
    escaped = False
    last_complete: tuple[int, int] | None = None

    for idx, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = idx
                depth = 1
                in_string = False
                escaped = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                last_complete = (start, idx + 1)
                start = None

    if last_complete is None:
        return None
    begin, end = last_complete
    return text[begin:end]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Mixed stdout capture to clean")
    parser.add_argument("output", help="Path to write the cleaned JSON")
    args = parser.parse_args()

    source = Path(args.input)
    target = Path(args.output)
    text = source.read_text(encoding="utf-8", errors="replace")
    json_blob = extract_last_json_object(text)
    if json_blob is None:
        raise SystemExit(f"no complete JSON object found in {source}")

    parsed = json.loads(json_blob)
    target.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote cleaned JSON to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
