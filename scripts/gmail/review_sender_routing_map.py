#!/usr/bin/env python3
"""Interactively review a saved Gmail sender-routing artifact.

This script no longer fetches Gmail live. It loads a saved routing-map JSON
artifact, walks the `needs_user_choice` records, and asks for a category for
each unresolved entry.

The intended input is the JSON artifact produced by
`scripts/gmail/evhstaff_gmail_inventory.py --sender-routing-map`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import termios
import tty
from pathlib import Path
from typing import Any


CATEGORY_CHOICES = {
    "1": "Vendors",
    "2": "Clients",
    "3": "Employees",
    "4": "Government",
    "5": "Utilities",
    "6": "Operations",
    "7": "Admin",
    "8": "Spam",
}


def print_menu() -> None:
    print("Category options:")
    for key, label in CATEGORY_CHOICES.items():
        print(f"  {key} {label}")
    print()


def read_single_key(prompt: str) -> str:
    if not sys.stdin.isatty():
        return input(prompt).strip().lower()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        print(prompt, end="", flush=True)
        ch = sys.stdin.read(1)
        print(ch)
        return ch.strip().lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def load_artifact(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Expected a JSON object routing artifact.")
    if "needs_user_choice" not in data:
        raise SystemExit("Artifact is missing 'needs_user_choice'.")
    return data


def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Cache file must contain a JSON object.")
    cache: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str):
            cache[key.lower()] = value
    return cache


def save_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(cache.items())), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sender_cache_keys(name: str, email_addr: str) -> list[str]:
    keys: list[str] = []
    if email_addr:
        keys.append(f"email:{email_addr.lower()}")
        if "@" in email_addr:
            keys.append(f"domain:{email_addr.split('@', 1)[1].lower()}")
    if name:
        keys.append(f"name:{name.lower()}")
    return keys


def review_sender_routing(
    input_path: Path,
    output_path: Path | None = None,
    cache_path: Path | None = None,
) -> int:
    artifact = load_artifact(input_path)
    choices = artifact.get("needs_user_choice", [])
    if not isinstance(choices, list):
        raise SystemExit("'needs_user_choice' must be a list.")

    reviewed = 0
    accepted: list[dict[str, Any]] = []
    cache = load_cache(cache_path) if cache_path is not None else {}

    for idx, item in enumerate(choices, start=1):
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        email_addr = str(item.get("email", "")).strip()
        labels = item.get("label", "")
        subject = str(item.get("subject", "")).strip()
        suggestion = str(item.get("suggestion", "needs_user_choice")).strip()
        cached_category = None
        for key in sender_cache_keys(name, email_addr):
            cached_category = cache.get(key)
            if cached_category:
                break

        label_display = str(labels).strip() or "(none)"
        headline = label_display
        if name or email_addr:
            sender_bits = " ".join(bit for bit in [name, f"<{email_addr}>" if email_addr else ""] if bit).strip()
            headline = f"{sender_bits} | {label_display}"

        if cached_category:
            record: dict[str, Any] = {
                "name": name,
                "email": email_addr,
                "labels": labels,
                "subject": subject,
                "suggestion": suggestion,
                "chosen_category": cached_category,
                "source": "cache",
            }
            accepted.append(record)
            reviewed += 1
            print(f"cached: {headline} -> {cached_category}")
            continue

        while True:
            print("\033[2J\033[H", end="")
            print_menu()
            print(f"({idx}/{len(choices)}) {headline}")
            print(f"  labels: {label_display}")
            print(f"  subject: {subject or '(none)'}")
            print(f"  suggestion: {suggestion}")
            choice = read_single_key("Category [1-7, s=skip, q=quit]: ")
            if choice == "q":
                break
            if choice == "s":
                reviewed += 1
                break

            category = CATEGORY_CHOICES.get(choice)
            if not category:
                print("Please enter 1-7, s, or q.")
                continue

            record: dict[str, Any] = {
                "name": name,
                "email": email_addr,
                "labels": labels,
                "subject": subject,
                "suggestion": suggestion,
                "chosen_category": category,
            }
            accepted.append(record)
            for key in sender_cache_keys(name, email_addr):
                cache[key] = category
            reviewed += 1
            print(json.dumps(record, indent=2))
            break
        if choice == "q":
            break

    if output_path is not None:
        output_path.write_text(
            "\n".join(json.dumps(record) for record in accepted) + ("\n" if accepted else ""),
            encoding="utf-8",
        )
    if cache_path is not None:
        save_cache(cache_path, cache)

    summary = {
        "input": str(input_path),
        "choices_total": len(choices),
        "reviewed_count": reviewed,
        "accepted_count": len(accepted),
        "output": str(output_path) if output_path else None,
        "cache": str(cache_path) if cache_path else None,
    }
    print(json.dumps(summary, indent=2))
    return reviewed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="/tmp/evh_gmail_sender_routing_map.clean.json",
        help="Saved sender-routing-map JSON artifact to review",
    )
    parser.add_argument(
        "--output",
        help="Optional JSONL file for accepted category choices",
    )
    parser.add_argument(
        "--cache",
        default="/tmp/evh_gmail_sender_category_cache.json",
        help="Persistent sender/category cache JSON file",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input artifact not found: {input_path}")

    output_path = Path(args.output) if args.output else None
    cache_path = Path(args.cache) if args.cache else None
    review_sender_routing(input_path, output_path=output_path, cache_path=cache_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
