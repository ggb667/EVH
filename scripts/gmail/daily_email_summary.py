#!/usr/bin/env python3
"""Build a daily communication summary from unread EVH Gmail messages.

This version uses ChatGPT to summarize and categorize unread messages instead
of keyword heuristics. It:
- authenticates to the EVH mailbox
- reads unread inbox messages
- extracts message text with the existing aggressive Gmail parsing helpers
- sends the batch to ChatGPT for structured summarization
- writes a Markdown summary and a JSON artifact
"""

from __future__ import annotations

import argparse
import base64
import email.message
import json
import os
import html
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.gmail.evhstaff_gmail_inventory import (
        Token,
        _header_lookup,
        extract_message_classification_text,
        extract_sender_info,
        gmail_get_profile,
        iter_message_full,
        load_client_config,
        gmail_send_message,
        refresh_token,
    )
except ImportError:  # pragma: no cover - direct script execution path
    from evhstaff_gmail_inventory import (  # type: ignore
        Token,
        _header_lookup,
        extract_message_classification_text,
        extract_sender_info,
        gmail_get_profile,
        iter_message_full,
        load_client_config,
        gmail_send_message,
        refresh_token,
    )


EXPECTED_MAILBOX_EMAIL = "evhstaff@gmail.com"
DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"
DEFAULT_DAILY_SUMMARY_RECIPIENT = "evhstaff+daily_summary@gmail.com"


@dataclass
class MailItem:
    message_id: str
    sender_name: str
    sender_email: str
    subject: str
    body_text: str
    labels: list[str]
    unread: bool


@dataclass
class SentItem:
    message_id: str
    recipients: str
    subject: str


def verify_expected_mailbox(token: Token, client: dict[str, Any]) -> str:
    profile = gmail_get_profile(token, client=client)
    mailbox_email = str(profile.get("emailAddress", "")).strip().lower()
    if mailbox_email != EXPECTED_MAILBOX_EMAIL:
        raise SystemExit(
            f"Authenticated Gmail mailbox is {mailbox_email!r}, expected {EXPECTED_MAILBOX_EMAIL!r}."
        )
    print(f"=== Authenticated Gmail mailbox: {mailbox_email} ===")
    return mailbox_email


def _openai_responses_completion(
    api_key: str,
    model: str,
    input_items: list[dict[str, Any]],
    *,
    base_url: str = "https://api.openai.com/v1",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": input_items,
        "max_output_tokens": 4000,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_messages(token: Token, query: str, max_results: int) -> list[MailItem]:
    items: list[MailItem] = []
    for msg in iter_message_full(token, query, max_results):
        labels = [str(v) for v in msg.get("labelIds", []) if isinstance(v, str)]
        unread = "UNREAD" in labels
        from_header, sender_name, sender_email, subject = extract_sender_info(msg, token)
        body_text = extract_message_classification_text(msg, token, max_lines=40)
        items.append(
            MailItem(
                message_id=str(msg.get("id", "")),
                sender_name=sender_name or from_header or sender_email,
                sender_email=sender_email,
                subject=subject,
                body_text=body_text,
                labels=labels,
                unread=unread,
            )
        )
    return items


def load_sent_messages(token: Token, query: str, max_results: int) -> list[SentItem]:
    items: list[SentItem] = []
    for msg in iter_message_full(token, query, max_results):
        to_header = _header_lookup(msg, "To")
        subject = _header_lookup(msg, "Subject")
        items.append(
            SentItem(
                message_id=str(msg.get("id", "")),
                recipients=to_header or "(no recipients found)",
                subject=subject,
            )
        )
    return items


def build_summary_prompt(items: list[MailItem], query: str) -> list[dict[str, Any]]:
    compact_items = [
        {
            "message_id": item.message_id,
            "sender_name": item.sender_name,
            "sender_email": item.sender_email,
            "subject": item.subject,
            "labels": item.labels,
            "unread": item.unread,
            "body_text": item.body_text,
        }
        for item in items
    ]
    system = (
        "You are helping a veterinary hospital staff member triage unread email. "
        "Return only valid JSON. Keep the JSON compact and complete. "
        "Group messages into client_communications, records, appointments, refills, pet_questions, and other. "
        "Client communications are the highest priority and should be surfaced first in the summary and follow-up notes. "
        "Prefer concise, actionable summaries. "
        "If a message contains more than one request type, include it in the most important bucket and mention the overlap. "
        "Do not invent facts."
    )
    user = {
        "task": "Create a communication summary for staff.",
        "query": query,
        "messages": compact_items,
        "required_json_shape": {
            "summary": "string",
            "counts": {
                "client_communications": 0,
                "records": 0,
                "appointments": 0,
                "refills": 0,
                "pet_questions": 0,
                "other": 0,
            },
            "client_communications": [
                {
                    "message_id": "string",
                    "sender": "string",
                    "email": "string",
                    "subject": "string",
                    "summary": "string",
                    "unread": "boolean",
                }
            ],
            "records": [
                {
                    "message_id": "string",
                    "sender": "string",
                    "email": "string",
                    "subject": "string",
                    "summary": "string",
                    "unread": "boolean",
                }
            ],
            "appointments": [],
            "refills": [],
            "pet_questions": [],
            "other": [],
            "follow_up_notes": ["string"],
        },
        "style": (
            "Make the summary suitable to email to staff as a Communication Summary. "
            "Keep it brief but useful."
        ),
    }
    return [
        {"role": "system", "content": [{"type": "input_text", "text": system}]},
        {"role": "user", "content": [{"type": "input_text", "text": json.dumps(user, ensure_ascii=False)}]},
    ]


def parse_summary_result(content: str) -> dict[str, Any]:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise SystemExit("ChatGPT returned non-object JSON.")
    return parsed


def extract_response_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    output = response.get("output", [])
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            contents = item.get("content", [])
            if not isinstance(contents, list):
                continue
            for part in contents:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        joined = "".join(parts).strip()
        if joined:
            return joined
    return ""


def render_markdown(result: dict[str, Any], query: str, count: int) -> str:
    summary = str(result.get("summary", "")).strip()
    counts = result.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}

    def records_for(key: str) -> list[dict[str, Any]]:
        value = result.get(key, [])
        return value if isinstance(value, list) else []

    lines: list[str] = []
    lines.append("# Communication Summary")
    lines.append(f"- Query: `{query}`")
    lines.append(f"- Unread Reviewed: {count}")
    lines.append(f"- Total Emails: {count}")
    lines.append(
        "- Counts: "
        + ", ".join(
            f"{name}={int(counts.get(name, 0) or 0)}"
            for name in ("client_communications", "records", "appointments", "refills", "pet_questions", "other")
        )
    )
    lines.append("")
    if summary:
        lines.append(summary)
        lines.append("")

    for key, title in (
        ("client_communications", "Client Communications"),
        ("records", "Records"),
        ("appointments", "Appointments"),
        ("refills", "Refills"),
        ("pet_questions", "Questions about pets"),
        ("other", "Other"),
    ):
        rows = records_for(key)
        lines.append(f"## {title} ({len(rows)})")
        if not rows:
            lines.append("")
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            message_id = str(row.get("message_id", "")).strip()
            sender = str(row.get("sender", "")).strip()
            email = str(row.get("email", "")).strip()
            subject = str(row.get("subject", "")).strip()
            text = str(row.get("summary", "")).strip()
            unread = bool(row.get("unread", False))
            head = f"- {sender}"
            if unread:
                head += " **[UNREAD]**"
            if email:
                head += f" <{email}>"
            if subject and message_id:
                gmail_url = f"https://mail.google.com/mail/u/0/#all/{message_id}"
                head += f" — [{subject}]({gmail_url})"
            elif subject:
                head += f" — {subject}"
            lines.append(head)
            if text:
                lines.append(f"  - {text}")
        lines.append("")

    follow_up = result.get("follow_up_notes", [])
    if isinstance(follow_up, list) and follow_up:
        lines.append("## Follow-up notes")
        for note in follow_up:
            note = str(note).strip()
            if note:
                lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_dry_run_result(items: list[MailItem], query: str) -> dict[str, Any]:
    buckets = {
        "client_communications": [],
        "records": [],
        "appointments": [],
        "refills": [],
        "pet_questions": [],
        "other": [],
    }
    for item in items:
        buckets["other"].append(
            {
                "message_id": item.message_id,
                "sender": item.sender_name,
                "email": item.sender_email,
                "subject": item.subject,
                "summary": "Dry-run placeholder: no OpenAI request was made.",
                "unread": item.unread,
            }
        )
    return {
        "summary": f"Dry-run validation for {len(items)} unread messages matching {query!r}. No OpenAI request was made.",
        "counts": {
            "client_communications": 0,
            "records": 0,
            "appointments": 0,
            "refills": 0,
            "pet_questions": 0,
            "other": len(items),
        },
        **buckets,
        "follow_up_notes": [
            "Dry-run mode validated message loading and artifact writing only.",
            "Run again without --dry-run to produce the AI-generated summary.",
        ],
        "sent_today": [],
    }


def build_email_message(
    subject: str,
    body_text: str,
    *,
    from_addr: str,
    to_addrs: list[str],
    cc_addrs: list[str] | None = None,
) -> str:
    msg = email.message.EmailMessage()
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["From"] = from_addr
    msg["Subject"] = subject
    msg.set_content(body_text)
    html_body = markdown_to_html(body_text)
    msg.add_alternative(html_body, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")
    return raw


def markdown_to_html(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = ["<html><body>"]
    in_list = False
    for line in lines:
        if not line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
            continue
        if line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
            continue
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline_markdown_to_html(line[2:].strip())}</li>")
            continue
        if line.startswith("  - "):
            out.append(f"<p style='margin-left: 1.5em;'>{inline_markdown_to_html(line[4:].strip())}</p>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append(f"<p>{inline_markdown_to_html(line.strip())}</p>")
    if in_list:
        out.append("</ul>")
    out.append("</body></html>")
    return "\n".join(out)


def inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda m: f"<a href=\"{html.escape(m.group(2), quote=True)}\">{html.escape(m.group(1))}</a>",
        escaped,
    )
    escaped = escaped.replace("**", "")
    return escaped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secrets", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--query", default="newer_than:1d")
    parser.add_argument("--sent-query", default="in:sent newer_than:1d")
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--output-md", default="/tmp/evh_daily_email_summary.md")
    parser.add_argument("--output-json", default="/tmp/evh_daily_email_summary.json")
    parser.add_argument("--dry-run", action="store_true", help="Skip OpenAI and write a local validation summary")
    parser.add_argument("--send-email", action="store_true", help="Send the rendered summary as an email")
    parser.add_argument(
        "--send-to",
        action="append",
        default=[DEFAULT_DAILY_SUMMARY_RECIPIENT],
        help="Recipient address; repeat for multiple recipients",
    )
    parser.add_argument("--send-cc", action="append", default=[], help="CC recipient address; repeat for multiple recipients")
    parser.add_argument("--email-subject", default="Daily Communication Summary")
    parser.add_argument("--openai-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--openai-reasoning-effort", default="none")
    parser.add_argument("--openai-text-verbosity", default="low")
    args = parser.parse_args()

    client = load_client_config(Path(args.client_secrets))
    token_path = Path(args.token_file)
    token = Token.from_file(token_path)
    if token.expired():
        token = refresh_token(client, token)
        token_path.write_text(json.dumps(token.dump(), indent=2, sort_keys=True))

    verify_expected_mailbox(token, client)

    items = load_messages(token, args.query, args.max_results)
    sent_items = [
        {
            "message_id": item.message_id,
            "recipients": item.recipients,
            "subject": item.subject,
        }
        for item in load_sent_messages(token, args.sent_query, args.max_results)
    ]
    if not items:
        rendered = "# Communication Summary\n\nNo unread messages matched the query.\n"
        Path(args.output_md).write_text(rendered, encoding="utf-8")
        Path(args.output_json).write_text(json.dumps({"summary": "No unread messages matched the query.", "count": 0}, indent=2) + "\n", encoding="utf-8")
        print(rendered, end="")
        return 0

    if args.dry_run:
        result = build_dry_run_result(items, args.query)
    else:
        api_key = os.environ.get(args.openai_api_key_env)
        if not api_key:
            raise SystemExit(f"Missing OpenAI API key in ${args.openai_api_key_env}")

        messages = build_summary_prompt(items, args.query)
        response = _openai_responses_completion(
            api_key,
            args.openai_model,
            messages,
        )
        content = extract_response_text(response)
        if not content:
            raise SystemExit("OpenAI returned empty content.")
        result = parse_summary_result(content)
    result["sent_today"] = sent_items
    rendered = render_markdown(result, args.query, len(items))

    Path(args.output_md).write_text(rendered, encoding="utf-8")
    Path(args.output_json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.send_email:
        raw_message = build_email_message(
            args.email_subject,
            rendered,
            from_addr=EXPECTED_MAILBOX_EMAIL,
            to_addrs=args.send_to,
            cc_addrs=args.send_cc or None,
        )
        sent = gmail_send_message(token, raw_message)
        print(
            f"=== Sent summary email: id={sent.get('id', '')} threadId={sent.get('threadId', '')} to={', '.join(args.send_to)} ==="
        )

    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
