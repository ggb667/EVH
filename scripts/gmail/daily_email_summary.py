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
from datetime import datetime, timezone
from urllib.parse import quote
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import boto3
except ImportError:  # pragma: no cover - local script fallback
    boto3 = None

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
DEFAULT_CHECKPOINT_PARAMETER = "/evh/daily-summary/evhstaff_gmail_com/last_successful_run"


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
    thread_id: str
    recipients: str
    subject: str
    body_text: str


def verify_expected_mailbox(
    token: Token,
    client: dict[str, Any],
    expected_mailbox: str = EXPECTED_MAILBOX_EMAIL,
) -> str:
    profile = gmail_get_profile(token, client=client)
    mailbox_email = str(profile.get("emailAddress", "")).strip().lower()
    expected_mailbox = expected_mailbox.strip().lower()
    if mailbox_email != expected_mailbox:
        raise SystemExit(
            f"Authenticated Gmail mailbox is {mailbox_email!r}, expected {expected_mailbox!r}."
        )
    print(f"=== Authenticated Gmail mailbox: {mailbox_email} ===")
    return mailbox_email


def _openai_responses_completion(
    api_key: str,
    model: str,
    input_items: list[dict[str, Any]],
    *,
    reasoning_effort: str = "none",
    text_verbosity: str = "low",
    base_url: str = "https://api.openai.com/v1",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": input_items,
        "max_output_tokens": 8000,
        "reasoning": {"effort": reasoning_effort},
        "text": {"verbosity": text_verbosity},
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
                thread_id=str(msg.get("threadId", "")),
                recipients=to_header or "(no recipients found)",
                subject=subject,
                body_text=extract_message_classification_text(msg, token, max_lines=12),
            )
        )
    return items


def _parse_iso_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_last_successful_run(parameter_name: str) -> datetime | None:
    if boto3 is None:
        print("[checkpoint] boto3 unavailable; skipping Parameter Store lookup")
        return None
    client = boto3.client("ssm")
    try:
        response = client.get_parameter(Name=parameter_name)
    except Exception as exc:
        print(f"[checkpoint] failed to load {parameter_name!r}: {exc!r}")
        return None
    parameter = response.get("Parameter", {})
    value = parameter.get("Value", "")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_iso_timestamp(value)
    except Exception:
        return None


def store_last_successful_run(parameter_name: str, timestamp: datetime) -> None:
    if boto3 is None:
        return
    client = boto3.client("ssm")
    client.put_parameter(
        Name=parameter_name,
        Value=timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        Type="String",
        Overwrite=True,
    )


def build_query_since_checkpoint(checkpoint: datetime | None) -> str:
    if checkpoint is None:
        return "newer_than:1d"
    checkpoint_date = checkpoint.astimezone(timezone.utc).strftime("%Y/%m/%d")
    return f"after:{checkpoint_date}"


def build_query_last_24h() -> str:
    return "newer_than:1d"


def build_query_between_checkpoint_and_24h_ago(checkpoint: datetime | None) -> str:
    if checkpoint is None:
        return "newer_than:1d"
    checkpoint_date = checkpoint.astimezone(timezone.utc).strftime("%Y/%m/%d")
    return f"after:{checkpoint_date} older_than:1d"


def sanitize_mailbox_key(mailbox_email: str) -> str:
    return mailbox_email.strip().lower().replace("@", "_").replace(".", "_")


def checkpoint_parameter_for_mailbox(mailbox_email: str) -> str:
    return f"/evh/daily-summary/{sanitize_mailbox_key(mailbox_email)}/last_successful_run"


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
        "You are helping a veterinary hospital staff member triage all email from the requested time window. "
        "Return only valid JSON. Keep the JSON compact and complete. "
        "Group messages into client_communications, records, appointments, refills, pet_questions, and other. "
        "Include every supplied message exactly once, using its exact message_id; do not omit read, promotional, newsletter, or low-priority messages. "
        "Unread messages are highest priority and should be surfaced first in the summary and follow-up notes; read messages remain below follow-up notes. "
        "Prefer concise, actionable summaries. Keep each message summary to one short sentence. "
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


def chunk_mail_items(items: list[MailItem], chunk_size: int) -> list[list[MailItem]]:
    if chunk_size <= 0:
        return [items]
    return [items[index:index + chunk_size] for index in range(0, len(items), chunk_size)]


def summarize_mail_chunk(
    api_key: str,
    model: str,
    items: list[MailItem],
    query: str,
    *,
    reasoning_effort: str = "none",
    text_verbosity: str = "low",
) -> dict[str, Any]:
    messages = build_summary_prompt(items, query)
    response = _openai_responses_completion(
        api_key,
        model,
        messages,
        reasoning_effort=reasoning_effort,
        text_verbosity=text_verbosity,
    )
    content = extract_response_text(response)
    if not content:
        raise SystemExit("OpenAI returned empty content.")
    return parse_summary_result(content)


def merge_chunk_results(
    chunk_results: list[dict[str, Any]],
    items: list[MailItem],
    sent_items: list[SentItem],
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "summary": "",
        "follow_up_notes": [],
    }
    for key in CATEGORY_KEYS:
        merged[key] = []
    for result in chunk_results:
        for key in CATEGORY_KEYS:
            rows = result.get(key, [])
            if isinstance(rows, list):
                merged[key].extend(row for row in rows if isinstance(row, dict))
        notes = result.get("follow_up_notes", [])
        if isinstance(notes, list):
            merged["follow_up_notes"].extend(str(note).strip() for note in notes if str(note).strip())
    merged["counts"] = {key: len(merged[key]) for key in CATEGORY_KEYS}
    merged["summary"] = " | ".join(
        str(result.get("summary", "")).strip() for result in chunk_results if str(result.get("summary", "")).strip()
    )
    return reconcile_summary_result(merged, items, sent_items)


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


CATEGORY_KEYS = (
    "client_communications",
    "records",
    "appointments",
    "refills",
    "pet_questions",
    "other",
)
CATEGORY_TITLES = {
    "client_communications": "Client Communications",
    "records": "Records",
    "appointments": "Appointments",
    "refills": "Refills",
    "pet_questions": "Questions about pets",
    "other": "Other",
}


def _one_line(text: str, limit: int = 240) -> str:
    line = " ".join(str(text).split())
    if len(line) > limit:
        return line[: limit - 1].rstrip() + "…"
    return line


def reconcile_summary_result(result: dict[str, Any], items: list[MailItem], sent_items: list[SentItem]) -> dict[str, Any]:
    """Keep the model's categorization, but guarantee one rendered row per input message."""
    valid = {item.message_id: item for item in items}
    seen: set[str] = set()
    clean: dict[str, list[dict[str, Any]]] = {key: [] for key in CATEGORY_KEYS}

    for key in CATEGORY_KEYS:
        rows = result.get(key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            message_id = str(row.get("message_id", "")).strip()
            if message_id not in valid or message_id in seen:
                continue
            item = valid[message_id]
            normalized = dict(row)
            normalized.update(
                message_id=message_id,
                sender=str(row.get("sender") or item.sender_name),
                email=str(row.get("email") or item.sender_email),
                subject=str(row.get("subject") or item.subject),
                unread=item.unread,
            )
            clean[key].append(normalized)
            seen.add(message_id)

    for item in items:
        if item.message_id in seen:
            continue
        clean["other"].append(
            {
                "message_id": item.message_id,
                "sender": item.sender_name,
                "email": item.sender_email,
                "subject": item.subject,
                "summary": _one_line(item.body_text) or "No summary available.",
                "unread": item.unread,
            }
        )

    result.update(clean)
    result["counts"] = {key: len(clean[key]) for key in CATEGORY_KEYS}

    # Match sent replies by recipient and normalized subject, then expose a direct reply link.
    def subject_key(subject: str) -> str:
        return re.sub(r"^(?:(?:re|fwd|fw)\s*:\s*)+", "", subject.strip(), flags=re.I)

    for key in CATEGORY_KEYS:
        for row in clean[key]:
            email = str(row.get("email", "")).lower()
            subject = subject_key(str(row.get("subject", "")))
            matches = [
                sent for sent in sent_items
                if email and email in sent.recipients.lower()
                and subject and subject_key(sent.subject) == subject
            ]
            if not matches:
                continue
            reply = matches[-1]
            row["reply"] = {
                "message_id": reply.message_id,
                "summary": _one_line(reply.body_text) or "Reply sent; no body summary available.",
            }
    return result


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
    lines.append(f"- Messages Reviewed: {count}")
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

    def render_rows(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            message_id = str(row.get("message_id", "")).strip()
            sender = str(row.get("sender", "")).strip()
            email = str(row.get("email", "")).strip()
            subject = str(row.get("subject", "")).strip()
            text = str(row.get("summary", "")).strip()
            head = f"- {sender}"
            if bool(row.get("unread", False)):
                head += " **[UNREAD]**"
            if email:
                head += f" ({email})"
            if subject and message_id:
                mailto_url = f"mailto:{quote(email)}?subject={quote(subject)}" if email else ""
                if mailto_url:
                    head += f" — [{subject}]({mailto_url})"
                else:
                    head += f" — {subject}"
            elif subject:
                head += f" — {subject}"
            lines.append(head)
            if text:
                lines.append(f"    {text}")
            reply = row.get("reply")
            if isinstance(reply, dict) and reply.get("message_id"):
                reply_id = str(reply["message_id"])
                reply_summary = _one_line(str(reply.get("summary", "")))
                if email:
                    reply_subject = quote(f"Re: {subject}" if subject else "Re:")
                    reply_url = f"mailto:{quote(email)}?subject={reply_subject}"
                    lines.append(f"    Reply: [View reply]({reply_url}) — {reply_summary}")
                else:
                    lines.append(f"    Reply: {reply_summary}")

    def render_group(unread: bool, prefix: str = "") -> None:
        for key in CATEGORY_KEYS:
            rows = [row for row in records_for(key) if bool(row.get("unread", False)) is unread]
            if not rows:
                continue
            title = f"{prefix}{CATEGORY_TITLES[key]}" if prefix else CATEGORY_TITLES[key]
            lines.append(f"## {title} ({len(rows)})")
            render_rows(rows)
            lines.append("")

    render_group(True)

    follow_up = result.get("follow_up_notes", [])
    if isinstance(follow_up, list) and follow_up:
        lines.append("## Follow-up notes")
        for note in follow_up:
            note = str(note).strip()
            if note:
                lines.append(f"- {note}")
        lines.append("")

    read_count = sum(
        1 for key in CATEGORY_KEYS for row in records_for(key)
        if not bool(row.get("unread", False))
    )
    if read_count:
        lines.append(f"## Read messages ({read_count})")
        lines.append("")
    render_group(False, "Read — ")

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
    open_list_item = False

    def close_list_item() -> None:
        nonlocal open_list_item
        if open_list_item:
            out.append("</li>")
            open_list_item = False

    def close_list() -> None:
        nonlocal in_list
        close_list_item()
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        if not line.strip():
            close_list()
            continue
        if line.startswith("# "):
            close_list()
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
            continue
        if line.startswith("## "):
            close_list()
            out.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
            continue
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            close_list_item()
            out.append(f"<li>{inline_markdown_to_html(line[2:].strip())}")
            open_list_item = True
            continue
        if line.startswith("    ") and open_list_item:
            out.append(
                '<div style="margin-top: 0;">'
                f"{inline_markdown_to_html(line.strip())}"
                "</div>"
            )
            continue
        close_list()
        out.append(f"<p>{inline_markdown_to_html(line.strip())}</p>")
    close_list()
    out.append("</body></html>")
    return "\n".join(out)


def inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    links: list[str] = []

    def preserve_link(match: re.Match[str]) -> str:
        links.append(
            f'<a href="{html.escape(match.group(2), quote=True)}">'
            f"{html.escape(match.group(1))}</a>"
        )
        return f"\x00LINK{len(links) - 1}\x00"

    escaped = re.sub(
        r"\[([^\]]+)\]\(((?:https?://|mailto:)[^)]+)\)",
        preserve_link,
        escaped,
    )
    escaped = re.sub(
        r"(?<![\w@])([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)",
        lambda m: f'<a href="mailto:{html.escape(m.group(1), quote=True)}">{html.escape(m.group(1))}</a>',
        escaped,
    )
    for index, link in enumerate(links):
        escaped = escaped.replace(f"\x00LINK{index}\x00", link)
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
    parser.add_argument("--chunk-size", type=int, default=30, help="Number of messages per OpenAI chunk; 0 disables chunking")
    parser.add_argument("--checkpoint-parameter", default="")
    parser.add_argument("--mailbox-email", default=EXPECTED_MAILBOX_EMAIL)
    parser.add_argument("--use-checkpoint", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--time-window",
        choices=("checkpoint", "last24hours", "both"),
        default="checkpoint",
        help="checkpoint = since last success; last24hours = only the last day; both = overlap checkpoint with last day",
    )
    parser.add_argument(
        "--keep-current-checkpoint",
        action="store_true",
        help="Do not update the checkpoint after a successful run",
    )
    args = parser.parse_args()

    client = load_client_config(Path(args.client_secrets))
    token_path = Path(args.token_file)
    token = Token.from_file(token_path)
    if token.expired():
        token = refresh_token(client, token)
        token_path.write_text(json.dumps(token.dump(), indent=2, sort_keys=True))

    verify_expected_mailbox(token, client, expected_mailbox=args.mailbox_email)

    checkpoint_parameter = args.checkpoint_parameter or checkpoint_parameter_for_mailbox(args.mailbox_email)
    checkpoint = load_last_successful_run(checkpoint_parameter) if args.use_checkpoint else None
    checkpoint_query = build_query_since_checkpoint(checkpoint)
    last_24h_query = build_query_last_24h()
    sent_checkpoint_query = f"in:sent {checkpoint_query}".strip()
    sent_last_24h_query = "in:sent newer_than:1d"

    print(f"[checkpoint] mailbox_email={args.mailbox_email}")
    print(f"[checkpoint] parameter={checkpoint_parameter}")
    print(f"[checkpoint] loaded={checkpoint.isoformat() if checkpoint else None}")
    print(f"[checkpoint] base_query={args.query!r}")
    print(f"[checkpoint] checkpoint_query={checkpoint_query!r}")
    print(f"[checkpoint] last_24h_query={last_24h_query!r}")
    print(f"[checkpoint] sent_base_query={args.sent_query!r}")
    print(f"[checkpoint] sent_checkpoint_query={sent_checkpoint_query!r}")
    print(f"[checkpoint] sent_last_24h_query={sent_last_24h_query!r}")

    if args.time_window == "checkpoint":
        query = query = build_query_since_checkpoint(checkpoint)
        sent_query = sent_checkpoint_query
    elif args.time_window == "last24hours":
        query = build_query_last_24h()
        sent_query = sent_last_24h_query
    else:
        query = build_query_between_checkpoint_and_24h_ago(checkpoint)
        sent_query = f"in:sent {query}".strip()

    print(f"[checkpoint] time_window={args.time_window}")
    print(f"[checkpoint] final_query={query!r}")
    print(f"[checkpoint] final_sent_query={sent_query!r}")

    items = load_messages(token, query, args.max_results)
    sent_items = [
        {
            "message_id": item.message_id,
            "thread_id": item.thread_id,
            "recipients": item.recipients,
            "subject": item.subject,
            "body_text": item.body_text,
        }
        for item in load_sent_messages(token, sent_query, args.max_results)
    ]
    sent_records = [
        SentItem(
            message_id=str(item.get("message_id", "")),
            thread_id=str(item.get("thread_id", "")),
            recipients=str(item.get("recipients", "")),
            subject=str(item.get("subject", "")),
            body_text=str(item.get("body_text", "")),
        )
        for item in sent_items
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

        if args.chunk_size and len(items) > args.chunk_size:
            chunk_results: list[dict[str, Any]] = []
            for index, chunk in enumerate(chunk_mail_items(items, args.chunk_size), start=1):
                print(f"[openai] summarizing chunk {index}/{((len(items) - 1) // args.chunk_size) + 1} with {len(chunk)} messages")
                chunk_results.append(
                    summarize_mail_chunk(
                        api_key,
                        args.openai_model,
                        chunk,
                        args.query,
                        reasoning_effort=args.openai_reasoning_effort,
                        text_verbosity=args.openai_text_verbosity,
                    )
                )
            result = merge_chunk_results(chunk_results, items, sent_records)
        else:
            messages = build_summary_prompt(items, args.query)
            response = _openai_responses_completion(
                api_key,
                args.openai_model,
                messages,
                reasoning_effort=args.openai_reasoning_effort,
                text_verbosity=args.openai_text_verbosity,
            )
            content = extract_response_text(response)
            if not content:
                raise SystemExit("OpenAI returned empty content.")
            result = parse_summary_result(content)
    if "counts" not in result:
        result = reconcile_summary_result(result, items, sent_records)
    result["sent_today"] = sent_items
    rendered = render_markdown(result, args.query, len(items))

    Path(args.output_md).write_text(rendered, encoding="utf-8")
    Path(args.output_json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.send_email:
        raw_message = build_email_message(
            args.email_subject,
            rendered,
            from_addr=args.mailbox_email,
            to_addrs=args.send_to,
            cc_addrs=args.send_cc or None,
        )
        sent = gmail_send_message(token, raw_message)
        print(
            f"=== Sent summary email: id={sent.get('id', '')} threadId={sent.get('threadId', '')} to={', '.join(args.send_to)} ==="
        )

    if not args.dry_run and not args.keep_current_checkpoint:
        store_last_successful_run(checkpoint_parameter, datetime.now(timezone.utc))
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
