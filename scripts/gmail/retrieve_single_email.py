#!/usr/bin/env python3
"""Retrieve and print the first Gmail message for a sender.

Prints subject, from, date, and plain-text body (or HTML-stripped fallback).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import re
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

try:
    from scripts.gmail.evhstaff_gmail_inventory import (
        Token,
        gmail_get_message_full,
        gmail_get_message_raw,
        iter_message_ids,
        load_client_config,
        refresh_token,
    )
except ImportError:  # pragma: no cover
    from evhstaff_gmail_inventory import (  # type: ignore
        Token,
        gmail_get_message_full,
        gmail_get_message_raw,
        iter_message_ids,
        load_client_config,
        refresh_token,
    )


def decode_header(value: str) -> str:
    try:
        from email.header import decode_header, make_header
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def html_to_text(html: str) -> list[str]:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"\\s+", " ", html)
    return [p.strip() for p in html.split(" ") if p.strip()]


def header_lookup(message: dict[str, Any], *names: str) -> str:
    payload = message.get("payload", {})
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    wanted = {n.lower() for n in names}
    if not isinstance(headers, list):
        return ""
    for header in headers:
        if not isinstance(header, dict):
            continue
        if str(header.get("name", "")).lower() in wanted:
            value = str(header.get("value", "")).strip()
            if value:
                return value
    return ""


def body_from_full(message: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = str(part.get("mimeType", "")).lower()
        body = part.get("body", {})
        if not isinstance(body, dict):
            body = {}
        data = body.get("data")
        if isinstance(data, str) and data:
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
            if mime.startswith("text/plain") or not mime:
                lines.extend(raw.splitlines())
                return
            if mime.startswith("text/html"):
                lines.extend(html_to_text(raw))
                return
        parts = part.get("parts", [])
        if isinstance(parts, list):
            for child in parts:
                if isinstance(child, dict):
                    walk(child)
                    if lines:
                        return

    payload = message.get("payload", {})
    if isinstance(payload, dict):
        walk(payload)
    return [ln.rstrip() for ln in lines if ln.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secrets", default="/home/ggb66/dev/evhstaff_gmail_google_client_credentials.json")
    parser.add_argument("--token-file", default="/home/ggb66/dev/evhstaff_gmail_token.json")
    parser.add_argument("--sender", required=True, help="Sender email address to search for")
    parser.add_argument("--sender-name", default="", help="Optional sender name to help match Gmail")
    parser.add_argument("--max-lines", type=int, default=30)
    parser.add_argument("--log-file", default="/tmp/evh_single_email.log", help="Write the loaded message to this log file")
    args = parser.parse_args()

    client = load_client_config(Path(args.client_secrets))
    token_path = Path(args.token_file)
    if not token_path.exists():
        raise SystemExit(f"Token file not found: {token_path}")
    token = Token.from_file(token_path)
    if token.expired():
        token = refresh_token(client, token)
        token_path.write_text(token.to_json(indent=2) + "\n", encoding="utf-8")

    queries = [
        f"from:{args.sender}",
        f'from:"{args.sender}"',
        f"from:{args.sender.split('@', 1)[0]}",
    ]
    if args.sender_name:
        queries.extend([f'from:"{args.sender_name}"', f"from:{args.sender_name}"])

    with contextlib.redirect_stdout(sys.stderr), contextlib.redirect_stderr(sys.stderr):
        for query in dict.fromkeys(queries):
            hit = next(iter_message_ids(token, query, 1, client=client), None)
            if hit is None:
                continue
            message_id = str(hit.get("id", "")).strip()
            if not message_id:
                continue
            try:
                full = gmail_get_message_full(token, message_id, client=client)
            except Exception:
                full = {}
            try:
                raw = gmail_get_message_raw(token, message_id, client=client)
            except Exception:
                raw = {}

            subject = decode_header(header_lookup(full, "Subject") or header_lookup(raw, "Subject"))
            from_header = decode_header(header_lookup(full, "From", "Sender", "Reply-To") or header_lookup(raw, "From", "Sender", "Reply-To"))
            date = header_lookup(full, "Date") or header_lookup(raw, "Date")
            snippet = str(full.get("snippet") or raw.get("snippet") or "").strip()
            body_lines = body_from_full(full)
            if not body_lines and isinstance(raw.get("raw"), str) and raw["raw"]:
                eml_bytes = base64.urlsafe_b64decode(raw["raw"].encode("utf-8"))
                parsed = BytesParser(policy=policy.default).parsebytes(eml_bytes)
                subject = subject or decode_header(str(parsed.get("Subject", "")).strip())
                from_header = from_header or decode_header(str(parsed.get("From", "")).strip())
                if parsed.is_multipart():
                    for part in parsed.walk():
                        mime = part.get_content_type().lower()
                        if mime == "text/plain":
                            try:
                                content = part.get_content()
                            except Exception:
                                content = ""
                            if isinstance(content, str) and content.strip():
                                body_lines = [ln.rstrip() for ln in content.splitlines() if ln.strip()]
                                break
                        elif mime == "text/html" and not body_lines:
                            try:
                                content = part.get_content()
                            except Exception:
                                content = ""
                            if isinstance(content, str) and content.strip():
                                body_lines = html_to_text(content)
                                break
                else:
                    try:
                        content = parsed.get_content()
                    except Exception:
                        content = ""
                    if isinstance(content, str) and content.strip():
                        body_lines = [ln.rstrip() for ln in content.splitlines() if ln.strip()]

            output_lines = [
                f"Message-ID: {message_id}",
                f"From: {from_header or args.sender}",
                f"Subject: {subject or '(No Subject)'}",
            ]
            if date:
                output_lines.append(f"Date: {date}")
            if snippet:
                output_lines.append(f"Snippet: {snippet}")
            output_lines.append("")
            if body_lines:
                output_lines.extend(body_lines[: args.max_lines])
            else:
                output_lines.append("(No Text)")

            log_path = Path(args.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

            for line in output_lines:
                print(line)
            return 0

    raise SystemExit(f"No Gmail message found for {args.sender}")


if __name__ == "__main__":
    raise SystemExit(main())
