"""Restart the Instinct PDF family sampler until it completes."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Loop the Instinct PDF family sampler until it finishes.")
    parser.add_argument("--patient-limit", type=int, default=200)
    parser.add_argument("--max-docs-per-patient", type=int, default=0)
    parser.add_argument("--seed", type=int, default=11525)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--heartbeat", type=Path, required=True)
    parser.add_argument("--pdf-timeout", type=int, default=45)
    parser.add_argument("--sleep-seconds", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_cmd = [
        sys.executable,
        "scripts/instinct_pdf_family_sampler.py",
        "--patient-limit",
        str(args.patient_limit),
        "--max-docs-per-patient",
        str(args.max_docs_per_patient),
        "--seed",
        str(args.seed),
        "--checkpoint",
        str(args.checkpoint),
        "--output",
        str(args.output),
        "--heartbeat",
        str(args.heartbeat),
        "--pdf-timeout",
        str(args.pdf_timeout),
    ]

    while True:
        proc = subprocess.run(base_cmd, text=True)
        if proc.returncode == 0:
            return 0
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
