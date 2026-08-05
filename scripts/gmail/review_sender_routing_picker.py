#!/usr/bin/env python3
"""Interactive sender-routing picker with keyboard navigation and preview.

This consumes the extracted routing rows produced from a FileRunOutput-style
export, e.g.:

    Name <email@example.com> -> Category [classified_as=...]

Behavior:
- Up/Down move through category choices
- Left/Right move to previous/next entry
- 0-9 / A-F jump to a category choice
- Enter confirms the highlighted category
- Space toggles a compact 5-line preview for the current sender
- If a preview source is supplied, an auto-preview appears after 6 seconds of
  inactivity
- Screen is cleared on navigation to keep the UI tidy

Optional preview sources:
- JSON object mapping email -> multiline text
- JSONL with objects that include `email` and `text`
- Plain text file where each record is separated by a blank line and starts
  with a line containing `email: <address>`

The script writes a plain-text review file by default and a cache file keyed by
email/domain/name.
"""

from __future__ import annotations

import argparse
import curses
import contextlib
import json
import re
import sys
import time
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import scripts.gmail.evhstaff_gmail_inventory as gmail_inventory
    from scripts.gmail.evhstaff_gmail_inventory import (
        Token,
        extract_sender_info,
        gmail_get_message_full,
        gmail_get_message_raw,
        iter_message_ids,
        load_client_config,
    )
except ImportError:  # pragma: no cover - direct script execution path
    import evhstaff_gmail_inventory as gmail_inventory  # type: ignore
    from evhstaff_gmail_inventory import (  # type: ignore
        Token,
        extract_sender_info,
        gmail_get_message_full,
        gmail_get_message_raw,
        iter_message_ids,
        load_client_config,
    )


CATEGORY_CHOICES = [
    "Client",
    "Finance",
    "Government",
    "Insurance",
    "Laboratory",
    "Legal",
    "Marketing",
    "Other",
    "Uncategorized",
    "Payroll",
    "Scheduling",
    "Spam",
    "Staff",
    "Technology",
    "Utilities",
    "Vendor",
]

HEX_KEYS = "0123456789ABCDEF"


@dataclass(frozen=True)
class Entry:
    name: str
    email: str
    category: str
    meta: str
    raw: str


def strip_data_suffix(line: str) -> str:
    return line[:-7] if line.endswith(" [data]") else line


def parse_entry(line: str) -> Entry | None:
    line = strip_data_suffix(line.strip())
    m = re.match(r"^(.*?)\s*<([^<>]+)>\s*->\s*([^\[]+)\s*(\[.*\])?$", line)
    if not m:
        return None
    return Entry(
        name=m.group(1).strip(),
        email=m.group(2).strip().lower(),
        category=m.group(3).strip(),
        meta=(m.group(4) or "").strip(),
        raw=line,
    )


def load_entries(path: Path) -> list[Entry]:
    entries: list[Entry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = parse_entry(line)
        if entry is not None:
            entries.append(entry)
    return entries


def load_cache(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
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


def load_preview_source(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return {}
    if not path.exists():
        raise SystemExit(f"Preview source not found: {path}")

    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return {}

    # JSON object: email -> text
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    preview: dict[str, list[str]] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str):
                if isinstance(value, str):
                    preview[key.lower()] = value.splitlines()
                elif isinstance(value, list):
                    preview[key.lower()] = [str(v) for v in value]
        return preview

    if raw.lstrip().startswith("{"):
        raise SystemExit("Preview source looks like JSON but could not be parsed.")

    # JSONL or blank-line-separated text blocks.
    blocks = [b for b in re.split(r"\n\s*\n", raw) if b.strip()]
    for block in blocks:
        lines = block.splitlines()
        email = None
        body: list[str] = []
        for line in lines:
            m = re.match(r"^\s*email\s*:\s*(.+?)\s*$", line, re.I)
            if m and email is None:
                email = m.group(1).strip().lower()
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                body.append(line)
            else:
                if isinstance(obj, dict):
                    if email is None and isinstance(obj.get("email"), str):
                        email = obj["email"].strip().lower()
                    text = obj.get("text")
                    if isinstance(text, str):
                        body.extend(text.splitlines())
                    elif isinstance(text, list):
                        body.extend(str(v) for v in text)
        if email and body:
            preview[email] = body
    return preview


def load_preview_cache(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Preview cache file must contain a JSON object.")
    cache: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, list):
            cache[key.lower()] = [str(v) for v in value]
        elif isinstance(value, str):
            cache[key.lower()] = value.splitlines()
    return cache


def save_preview_cache(path: Path, cache: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(sorted(cache.items())), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def make_backup_copy(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(path.name + ".BAK")
    if not backup.exists():
        shutil.copy2(path, backup)
        return backup
    i = 1
    while True:
        candidate = path.with_name(f"{path.name}.BAK{i}")
        if not candidate.exists():
            shutil.copy2(path, candidate)
            return candidate
        i += 1


DEBUG_LOG_PATH = Path("/tmp/evh_gmail_picker_debug.log")


def _log_debug(message: str) -> None:
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")
    except Exception:
        pass


def _decode_header(value: str) -> str:
    try:
        from email.header import decode_header, make_header

        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_body_lines(message: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = str(part.get("mimeType", "")).lower()
        body = part.get("body", {})
        if not isinstance(body, dict):
            body = {}
        data = body.get("data")
        if isinstance(data, str) and data:
            import base64

            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
            if mime.startswith("text/plain") or not mime:
                lines.extend(raw.splitlines())
                return
        parts = part.get("parts", [])
        if isinstance(parts, list):
            for child in parts:
                if isinstance(child, dict):
                    walk(child)

    payload = message.get("payload", {})
    if isinstance(payload, dict):
        walk(payload)
    return [ln.rstrip() for ln in lines if ln.strip()]


def _plain_text_from_html(html: str) -> list[str]:
    # lightweight HTML cleanup for preview text only
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\\s+", " ", text)
    return [part.strip() for part in text.split(" ") if part.strip()]


def _attachment_names_from_message(message: Any) -> list[str]:
    names: list[str] = []
    try:
        for part in message.iter_attachments():
            filename = ""
            try:
                filename = str(part.get_filename() or "").strip()
            except Exception:
                filename = ""
            if not filename:
                disposition = str(part.get_content_disposition() or "").strip()
                if disposition.lower() == "attachment":
                    filename = "unnamed attachment"
            if filename:
                names.append(filename)
    except Exception:
        return []
    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped


def _sender_preview_key(name: str, email_addr: str) -> str:
    return f"{name.lower()}|{email_addr.lower()}"


def fetch_sender_preview_lines(
    token: "Token",
    client: dict[str, Any],
    sender_email: str,
    sender_name: str = "",
    cache: dict[str, list[str]] | None = None,
    max_lines: int = 10,
) -> list[str]:
    cache = cache if cache is not None else {}
    key = _sender_preview_key(sender_name, sender_email)
    if key in cache:
        return cache[key][:max_lines]

    queries: list[str] = []
    if sender_email:
        local_part, _, domain = sender_email.partition("@")
        queries.extend(
            [
                f"from:{sender_email}",
                f'from:"{sender_email}"',
                f"from:{local_part}",
            ]
        )
        if domain:
            queries.extend(
                [
                    f"from:{domain}",
                    f'from:"{domain}"',
                    f"deliveredto:{domain}",
                ]
            )
    if sender_name:
        queries.extend(
            [
                f'from:"{sender_name}"',
                f"from:{sender_name}",
            ]
        )
    queries = [q for q in dict.fromkeys(queries) if q.strip()]
    if not queries:
        _log_debug(f"preview: no queries for {sender_name} <{sender_email}>")
        return []

    _log_debug(f"preview: start sender={sender_name} <{sender_email}> queries={queries!r}")
    snippets: list[str] = []
    try:
        from email import policy
        from email.parser import BytesParser
        import base64

        orig_phase = getattr(gmail_inventory, "_phase", None)
        try:
            if orig_phase is not None:
                gmail_inventory._phase = lambda *args, **kwargs: None  # type: ignore[attr-defined]
            with contextlib.redirect_stdout(sys.stderr), contextlib.redirect_stderr(sys.stderr):
                for query in queries:
                    _log_debug(f"preview: query={query!r}")
                    hits = list(iter_message_ids(token, query, 5, client=client))
                    if not hits:
                        _log_debug(f"preview: no hit for query={query!r}")
                        continue
                    for msg in hits:
                        message_id = str(msg.get("id", "")).strip()
                        _log_debug(f"preview: hit query={query!r} message_id={message_id!r} raw_hit={msg!r}")
                        if not message_id:
                            continue
                        try:
                            raw_message = gmail_get_message_raw(token, message_id, client=client)
                        except Exception as exc:
                            _log_debug(f"preview: raw fetch failed message_id={message_id!r} error={exc!r}")
                            continue
                        raw_b64 = raw_message.get("raw")
                        if not isinstance(raw_b64, str) or not raw_b64:
                            _log_debug(f"preview: raw payload missing message_id={message_id!r} keys={list(raw_message.keys())!r}")
                            continue
                        eml_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
                        parsed = BytesParser(policy=policy.default).parsebytes(eml_bytes)
                        subject = _decode_header(str(parsed.get("Subject", "")).strip())
                        from_header = _decode_header(str(parsed.get("From", "")).strip())
                        attachment_names = _attachment_names_from_message(parsed)
                        _log_debug(
                            f"preview: parsed message_id={message_id!r} subject={subject!r} from={from_header!r} attachments={attachment_names!r}"
                        )
                        body_chunks: list[str] = []
                        if parsed.is_multipart():
                            for part in parsed.walk():
                                mime = part.get_content_type().lower()
                                if mime == "text/plain":
                                    try:
                                        content = part.get_content()
                                    except Exception:
                                        content = ""
                                    if isinstance(content, str) and content.strip():
                                        body_chunks.extend(content.splitlines())
                                        break
                            else:
                                for part in parsed.walk():
                                    mime = part.get_content_type().lower()
                                    if mime == "text/html":
                                        try:
                                            content = part.get_content()
                                        except Exception:
                                            content = ""
                                        if isinstance(content, str) and content.strip():
                                            body_chunks.extend(_plain_text_from_html(content))
                                            break
                        else:
                            try:
                                content = parsed.get_content()
                            except Exception:
                                content = ""
                            if isinstance(content, str) and content.strip():
                                body_chunks.extend(content.splitlines())

                        text_lines: list[str] = []
                        if subject:
                            text_lines.append(f"Subject: {subject}")
                        if from_header:
                            text_lines.append(f"From: {from_header}")
                        if attachment_names:
                            text_lines.append("Attachments: " + ", ".join(attachment_names))
                        body_limit = max(0, max_lines - len(text_lines))
                        for line in body_chunks[:body_limit]:
                            if line.strip():
                                text_lines.append(line.rstrip())
                        if not body_chunks:
                            try:
                                full_message = gmail_get_message_full(token, message_id, client=client)
                            except Exception:
                                full_message = {}
                            if isinstance(full_message, dict):
                                full_subject = _decode_header(_header_lookup(full_message, "Subject"))
                                full_from = _decode_header(_header_lookup(full_message, "From", "Sender", "Reply-To"))
                                full_body = _extract_body_lines(full_message)
                                if full_subject and not subject:
                                    text_lines.append(f"Subject: {full_subject}")
                                if full_from and not from_header:
                                    text_lines.append(f"From: {full_from}")
                                if full_body:
                                    body_chunks = full_body
                                    body_limit = max(0, max_lines - len(text_lines))
                                    for line in body_chunks[:body_limit]:
                                        if line.strip():
                                            text_lines.append(line.rstrip())
                            if not body_chunks:
                                text_lines.append("(No Text)")
                        if text_lines:
                            snippets.extend(text_lines)
                            if len(snippets) >= max_lines:
                                break
                    if len(snippets) >= max_lines:
                        break
        finally:
            if orig_phase is not None:
                gmail_inventory._phase = orig_phase  # type: ignore[attr-defined]
    except Exception:
        return []

    if not snippets:
        return []

    cleaned: list[str] = []
    for line in snippets:
        if line.strip():
            cleaned.append(line.rstrip())
        if len(cleaned) >= max_lines:
            break
    cache[key] = cleaned
    return cleaned


def clamp(n: int, low: int, high: int) -> int:
    return max(low, min(high, n))


def format_preview(lines: list[str], limit: int = 10) -> list[str]:
    out = [ln.rstrip() for ln in lines if ln.strip()]
    return out[:limit]


def draw_screen(
    stdscr: Any,
    entries: list[Entry],
    idx: int,
    cat_idx: int,
    preview_lines: list[str] | None,
    preview_subject: str,
    category: str | None,
    preview_hint: str,
    status_line: str,
) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    entry = entries[idx]
    subject_line = preview_subject or "Subject:"
    top_lines = [
        f"Entry {idx + 1}/{len(entries)}",
        f"{entry.name} <{entry.email}>",
        "",
        "Categories:",
        "",
    ]

    for i, cat in enumerate(CATEGORY_CHOICES):
        key = HEX_KEYS[i]
        marker = "▶" if i == cat_idx else " "
        label = f"{cat}{' *' if cat == category else ''}"
        top_lines.append(f" {marker} {key}  {label}")

    bottom_lines: list[str] = [
        "",
        "Keys: ↑↓ choose category  ←→ prev/next entry  Enter accept  0-9A-F jump+accept  q quit",
    ]
    if status_line:
        bottom_lines.append(status_line)
    if preview_lines is not None:
        bottom_lines.extend(["", subject_line, "", "Preview:"])
        bottom_lines.extend(preview_lines)

    y = 0
    for line in top_lines:
        if y >= h - 1:
            break
        stdscr.addnstr(y, 0, line, w - 1)
        y += 1

    for line in bottom_lines:
        if y >= h - 1:
            break
        stdscr.addnstr(y, 0, line, w - 1)
        y += 1

    stdscr.refresh()


def run_picker(
    stdscr: Any,
    entries: list[Entry],
    cache: dict[str, str],
    preview_map: dict[str, list[str]],
    preview_cache: dict[str, list[str]],
    preview_token: "Token | None",
    preview_client: dict[str, Any] | None,
    output_path: Path | None,
    cache_path: Path | None,
    preview_cache_path: Path | None,
    auto_preview_seconds: int,
) -> int:
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        curses.use_default_colors()
    except curses.error:
        pass
    stdscr.timeout(250)

    idx = 0
    cat_idx = 0
    selection_by_entry: dict[int, int] = {}
    preview_visible = False
    preview_lines: list[str] | None = None
    preview_subject = ""
    preview_hint = ""
    last_input_at = time.monotonic()
    preview_mode_status = ""

    def current_entry() -> Entry:
        return entries[idx]

    def current_cached_category() -> str | None:
        entry = current_entry()
        for key in sender_cache_keys(entry.name, entry.email):
            cached = cache.get(key)
            if cached:
                return cached
        return None

    def current_effective_category() -> str:
        cached = current_cached_category()
        if cached:
            return cached
        if idx in selection_by_entry:
            return CATEGORY_CHOICES[selection_by_entry[idx]]
        if current_entry().category in CATEGORY_CHOICES:
            return current_entry().category
        return CATEGORY_CHOICES[0]

    def effective_category_for_entry(entry_index: int, entry: Entry) -> str:
        if entry_index in selection_by_entry:
            return CATEGORY_CHOICES[selection_by_entry[entry_index]]
        for key in sender_cache_keys(entry.name, entry.email):
            cached = cache.get(key)
            if cached:
                return cached
        if entry.category in CATEGORY_CHOICES:
            return entry.category
        return "Uncategorized"

    def update_category_from_entry() -> None:
        nonlocal cat_idx
        if idx in selection_by_entry:
            cat_idx = selection_by_entry[idx]
            return
        cached = current_cached_category()
        if cached and cached in CATEGORY_CHOICES:
            cat_idx = CATEGORY_CHOICES.index(cached)
            return
        if current_entry().category in CATEGORY_CHOICES:
            cat_idx = CATEGORY_CHOICES.index(current_entry().category)
        else:
            cat_idx = 0

    def show_preview() -> None:
        nonlocal preview_visible, preview_lines, preview_subject, preview_hint
        entry = current_entry()
        lines = preview_map.get(entry.email.lower(), [])
        if not lines and preview_token is not None and preview_client is not None:
            lines = fetch_sender_preview_lines(
                preview_token,
                preview_client,
                entry.email,
                entry.name,
                cache=preview_cache,
                max_lines=10,
            )
        if lines:
            preview_lines = format_preview(lines, 10)
            preview_subject = ""
            if preview_lines and preview_lines[0].startswith("Subject:"):
                preview_subject = preview_lines[0]
                preview_lines = preview_lines[1:]
            preview_visible = True
        else:
            preview_subject = "Subject:"
            preview_lines = ["Subject:", "(No Text)"]
            preview_visible = True

    def clear_preview() -> None:
        nonlocal preview_visible, preview_lines, preview_hint
        preview_visible = False
        preview_lines = None
        preview_hint = ""

    def set_choice(new_idx: int) -> None:
        nonlocal cat_idx
        cat_idx = new_idx % len(CATEGORY_CHOICES)
        selection_by_entry[idx] = cat_idx

    def accept_current_and_advance() -> None:
        nonlocal idx
        entry = current_entry()
        chosen = CATEGORY_CHOICES[cat_idx]
        selection_by_entry[idx] = cat_idx
        for key in sender_cache_keys(entry.name, entry.email):
            cache[key] = chosen
        clear_preview()
        idx = (idx + 1) % len(entries)

    def choose_then_accept(new_idx: int) -> None:
        set_choice(new_idx)
        draw_screen(
            stdscr,
            entries,
            idx,
            cat_idx,
            preview_lines if preview_visible else None,
            preview_subject,
            CATEGORY_CHOICES[cat_idx],
            preview_hint,
            preview_mode_status,
        )
        stdscr.refresh()
        time.sleep(0.5)
        accept_current_and_advance()

    def set_uncategorized_and_stay() -> None:
        set_choice(CATEGORY_CHOICES.index("Uncategorized"))
        draw_screen(
            stdscr,
            entries,
            idx,
            cat_idx,
            preview_lines if preview_visible else None,
            preview_subject,
            CATEGORY_CHOICES[cat_idx],
            preview_hint,
            preview_mode_status,
        )
        stdscr.refresh()

    show_preview()

    while True:
        update_category_from_entry()
        selected = current_effective_category()

        draw_screen(
            stdscr,
            entries,
            idx,
            cat_idx,
            preview_lines if preview_visible else None,
            preview_subject,
            selected,
            preview_hint,
            preview_mode_status,
        )

        try:
            ch = stdscr.get_wch()
        except curses.error:
            ch = -1
        if ch == -1:
            if auto_preview_seconds > 0 and not preview_visible:
                if time.monotonic() - last_input_at >= auto_preview_seconds:
                    show_preview()
            continue

        last_input_at = time.monotonic()

        if isinstance(ch, str):
            if ch in ("q", "Q", "\x1b"):
                break
            if ch == " ":
                show_preview()
                continue
            if len(ch) == 1 and ch.upper() in HEX_KEYS:
                choose_then_accept(HEX_KEYS.index(ch.upper()))
                continue
            if ch in ("\r", "\n"):
                accept_current_and_advance()
                continue
            continue

        if ch in (ord("q"), ord("Q")):
            break
        if ch in (curses.KEY_LEFT, 260):
            idx = (idx - 1) % len(entries)
            clear_preview()
            continue
        if ch in (curses.KEY_RIGHT, 261):
            idx = (idx + 1) % len(entries)
            clear_preview()
            continue
        if ch in (curses.KEY_UP, 259):
            set_choice(cat_idx - 1)
            continue
        if ch in (curses.KEY_DOWN, 258):
            set_choice(cat_idx + 1)
            continue
        if ch in (curses.KEY_ENTER, 10, 13):
            accept_current_and_advance()
            continue
    if output_path is not None:
        final_lines = []
        for i, entry in enumerate(entries):
            chosen = effective_category_for_entry(i, entry)
            final_lines.append(f"{entry.name} <{entry.email}> -> {chosen}")
        output_path.write_text("\n".join(final_lines) + ("\n" if final_lines else ""), encoding="utf-8")
    if cache_path is not None:
        save_cache(cache_path, cache)
    if preview_cache_path is not None:
        save_preview_cache(preview_cache_path, preview_cache)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="/home/ggb66/dev/EVH/pony/worktrees/rarity/NamesEmailAddressesCategoriesSource.txt",
        help="Input sender routing rows",
    )
    parser.add_argument(
        "--output",
        default="/tmp/reviewed_email_categories.txt",
        help="Plain-text output of accepted selections (default: /tmp/reviewed_email_categories.txt)",
    )
    parser.add_argument(
        "--cache",
        default="/tmp/evh_gmail_sender_category_cache.json",
        help="Cache file keyed by email/domain/name",
    )
    parser.add_argument(
        "--preview-source",
        help="Optional mailbox preview source file or JSON map keyed by email",
    )
    parser.add_argument(
        "--gmail-client-secrets",
        default="/home/ggb66/dev/evhstaff_gmail_google_client_credentials.json",
        help="Google OAuth client secrets JSON for direct Gmail preview fetches",
    )
    parser.add_argument(
        "--gmail-token-file",
        default="/home/ggb66/dev/evhstaff_gmail_token.json",
        help="Google OAuth token cache for direct Gmail preview fetches",
    )
    parser.add_argument(
        "--preview-cache",
        default="/tmp/evh_gmail_sender_preview_cache.json",
        help="Persistent cache of five-line preview snippets keyed by sender",
    )
    parser.add_argument(
        "--auto-preview-seconds",
        type=int,
        default=6,
        help="Seconds of inactivity before auto-showing preview (0 disables)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    entries = load_entries(input_path)
    if not entries:
        raise SystemExit("No sender entries found.")

    cache_path = Path(args.cache) if args.cache else None
    output_path = Path(args.output) if args.output else None
    preview_path = Path(args.preview_source) if args.preview_source else None
    preview_cache_path = Path(args.preview_cache) if args.preview_cache else None

    cache = load_cache(cache_path)
    preview_map = load_preview_source(preview_path)
    preview_cache = load_preview_cache(preview_cache_path)

    preview_token = None
    preview_client = None
    if preview_path is None:
        client_path = Path(args.gmail_client_secrets)
        token_path = Path(args.gmail_token_file)
        if client_path.exists() and token_path.exists():
            preview_client = load_client_config(client_path)
            preview_token = Token.from_file(token_path)

    if input_path.resolve() == output_path.resolve():
        backup = make_backup_copy(input_path)
        if backup is not None:
            print(f"=== Input equals output; backup created at: {backup} ===")
        else:
            print("=== Input equals output; no existing file found to back up ===")

    print(f"=== Accepted review selections will be written to: {output_path} ===")
    if preview_path is None and preview_client is not None and preview_token is not None:
        print("=== Gmail preview fetch is enabled; Space will pull the first Gmail hit and cache Subject + 10-line snippets ===")
    elif preview_map:
        print("=== Local preview source loaded; Space will show cached snippets ===")
    else:
        print("=== Preview source unavailable; Space may show '(No Text)' ===")

    def _wrapped(stdscr: Any) -> int:
        return run_picker(
            stdscr,
            entries,
            cache,
            preview_map,
            preview_cache,
            preview_token,
            preview_client,
            output_path,
            cache_path,
            preview_cache_path,
            args.auto_preview_seconds,
        )
    try:
        result = curses.wrapper(_wrapped)
    finally:
        print(f"=== Review output location: {output_path} ===")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
