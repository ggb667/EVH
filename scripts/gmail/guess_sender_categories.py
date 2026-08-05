#!/usr/bin/env python3
"""Guess better sender categories from email previews.

This companion script reuses the routing picker preview logic to inspect email
subjects/body snippets, then proposes a likely category for each sender row.

Input format: the same sender-routing rows consumed by
`scripts/gmail/review_sender_routing_picker.py`, e.g.

    Name <email@example.com> -> Category [optional metadata]

Output defaults to JSONL on stdout and can be written to a file.

Classification order:
1. OpenAI API classification when `OPENAI_API_KEY` is available and
   `--openai-model` is provided
2. Existing category/cached category is treated only as a hint for the model,
   not as a final answer
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.gmail.review_sender_routing_picker import (
        CATEGORY_CHOICES,
        Entry,
        fetch_sender_preview_lines,
        load_cache,
        load_entries,
        load_preview_cache,
        load_preview_source,
        save_preview_cache,
        sender_cache_keys,
    )
except ImportError:  # pragma: no cover - direct execution path
    from review_sender_routing_picker import (  # type: ignore
        CATEGORY_CHOICES,
        Entry,
        fetch_sender_preview_lines,
        load_cache,
        load_entries,
        load_preview_cache,
        load_preview_source,
        save_preview_cache,
        sender_cache_keys,
    )

try:
    from scripts.gmail.evhstaff_gmail_inventory import Token, load_client_config
except ImportError:  # pragma: no cover
    from evhstaff_gmail_inventory import Token, load_client_config  # type: ignore


@dataclass
class Guess:
    name: str
    email: str
    current_category: str
    guessed_category: str
    confidence: float
    reason: str
    source: str
    subject: str
    preview: list[str]


def _render_plain(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records:
        name = str(record.get("name", "")).strip()
        email = str(record.get("email", "")).strip()
        category = str(record.get("guessed_category", "")).strip()
        if name and email and category:
            lines.append(f"{name} <{email}> -> {category}")
    return "\n".join(lines) + ("\n" if lines else "")


def _normalize_category(value: str) -> str:
    value = value.strip()
    if value in CATEGORY_CHOICES:
        return value
    lowered = value.lower()
    for choice in CATEGORY_CHOICES:
        if choice.lower() == lowered:
            return choice
    return value


def _openai_guess(api_key: str, model: str, entry: Entry, preview_lines: list[str]) -> tuple[str, float, str]:
    import urllib.request

    categories = CATEGORY_CHOICES
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You read veterinary-hospital email previews and choose the best category from a fixed list. "
                            "Judge from the message content, attachment names, and the collection of messages from the same sender address, "
                            "not from the sender address alone. "
                            "Use Spam for job postings, generic recruiting, unrelated marketing, and non-business/non-animal mail."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "sender_name": entry.name,
                                "sender_email": entry.email,
                                "current_category": entry.category,
                                "subject": _subject_from_preview(preview_lines),
                                "preview_lines": preview_lines,
                                "attachments": _attachment_lines(preview_lines),
                                "categories": categories,
                                "instructions": (
                                    "Choose exactly one category from categories and respond with JSON only: "
                                    "{\"category\":\"...\",\"confidence\":0-1,\"reason\":\"...\"}."
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
        ],
        "max_output_tokens": 200,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = ""
    if isinstance(data, dict):
        if isinstance(data.get("output_text"), str) and data["output_text"]:
            content = data["output_text"]
        else:
            for item in data.get("output", []):
                if not isinstance(item, dict):
                    continue
                for part in item.get("content", []):
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        content = part["text"]
                        break
                if content:
                    break
    if not content:
        raise RuntimeError("OpenAI returned empty content")
    parsed = json.loads(content)
    category = _normalize_category(str(parsed.get("category", "")).strip())
    if category not in categories:
        raise RuntimeError(f"OpenAI returned invalid category: {category!r}")
    confidence = float(parsed.get("confidence") or 0.0)
    reason = str(parsed.get("reason", "")).strip() or "OpenAI classification."
    return category, confidence, reason


def _find_cached_category(cache: dict[str, str], entry: Entry) -> str:
    for key in sender_cache_keys(entry.name, entry.email):
        cached_category = cache.get(key)
        if cached_category:
            return cached_category
    return ""


def _subject_from_preview(preview_lines: list[str]) -> str:
    for line in preview_lines:
        if line.startswith("Subject:"):
            return line.partition(":")[2].strip()
    return ""


def _attachment_lines(preview_lines: list[str]) -> list[str]:
    return [line.partition(":")[2].strip() for line in preview_lines if line.startswith("Attachments:")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Sender routing rows file")
    parser.add_argument("--output", help="Optional JSONL output path")
    parser.add_argument("--cache", default="/tmp/evh_gmail_sender_category_cache.json")
    parser.add_argument("--preview-source", help="Optional local preview source file")
    parser.add_argument("--preview-cache", default="/tmp/evh_gmail_sender_preview_cache.json")
    parser.add_argument("--gmail-client-secrets", default="/home/ggb66/dev/evhstaff_gmail_google_client_credentials.json")
    parser.add_argument("--gmail-token-file", default="/home/ggb66/dev/evhstaff_gmail_token.json")
    parser.add_argument("--max-lines", type=int, default=10)
    parser.add_argument("--openai-model", help="Optional OpenAI model for LLM classification")
    parser.add_argument("--openai-api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    entries = load_entries(input_path)
    if not entries:
        raise SystemExit("No sender entries found.")

    if not args.openai_api_key or not args.openai_model:
        raise SystemExit("OpenAI classification requires both --openai-model and OPENAI_API_KEY.")

    cache = load_cache(Path(args.cache) if args.cache else None)
    preview_path = Path(args.preview_source) if args.preview_source else None
    preview_map = load_preview_source(preview_path)
    preview_cache_path = Path(args.preview_cache) if args.preview_cache else None
    preview_cache = load_preview_cache(preview_cache_path)

    preview_token = None
    preview_client = None
    if preview_path is None:
        client_path = Path(args.gmail_client_secrets)
        token_path = Path(args.gmail_token_file)
        if client_path.exists() and token_path.exists():
            preview_client = load_client_config(client_path)
            preview_token = Token.from_file(token_path)

    output_path = Path(args.output) if args.output else None
    output_records: list[dict[str, Any]] = []

    for entry in entries:
        preview_lines = preview_map.get(entry.email.lower(), [])
        if not preview_lines and preview_token is not None and preview_client is not None:
            preview_lines = fetch_sender_preview_lines(
                preview_token,
                preview_client,
                entry.email,
                entry.name,
                cache=preview_cache,
                max_lines=args.max_lines,
            )

        cached_category = _find_cached_category(cache, entry)
        guessed_category, confidence, reason = _openai_guess(args.openai_api_key, args.openai_model, entry, preview_lines)
        source = "openai"
        if cached_category:
            reason = f"Previous category hint was {cached_category!r}; {reason}"

        subject = _subject_from_preview(preview_lines)
        record = Guess(
            name=entry.name,
            email=entry.email,
            current_category=entry.category,
            guessed_category=guessed_category,
            confidence=round(float(confidence), 2),
            reason=reason,
            source=source,
            subject=subject,
            preview=preview_lines[: args.max_lines],
        )
        output_records.append(asdict(record))
        print(json.dumps(asdict(record), ensure_ascii=False))

    if output_path is not None:
        if output_path.suffix.lower() == ".jsonl":
            output_text = "\n".join(json.dumps(record, ensure_ascii=False) for record in output_records) + ("\n" if output_records else "")
        else:
            output_text = _render_plain(output_records)
        output_path.write_text(output_text, encoding="utf-8")
    if preview_cache_path is not None:
        save_preview_cache(preview_cache_path, preview_cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
