#!/usr/bin/env python3
"""Authorize against Gmail and print a mailbox inventory or export/delete.

This script uses only the Python standard library so it can run without
additional package installs. It performs a local OAuth "installed app" flow,
saves the refresh/access token cache, then calls the Gmail REST API.

Usage:
  python scripts/gmail/evhstaff_gmail_inventory.py \
    --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json \
    --token-file /path/to/evhstaff_gmail_token.json \
    --query 'in:inbox newer_than:30d'

  # Export messages matching a query into a zip archive of raw .eml files
  python scripts/gmail/evhstaff_gmail_inventory.py \
    --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json \
    --token-file /path/to/evhstaff_gmail_token.json \
    --query 'older_than:3y' \
    --export-zip /tmp/evh-mail-older-than-3y.zip

  # Export and permanently delete every message matching the query
  python scripts/gmail/evhstaff_gmail_inventory.py \
    --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json \
    --token-file /path/to/evhstaff_gmail_token.json \
    --query 'older_than:3y' \
    --export-zip \
    --delete-after-export

  # Permanently delete every message matching the query without exporting again
  python scripts/gmail/evhstaff_gmail_inventory.py \
    --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json \
    --token-file /path/to/evhstaff_gmail_token.json \
    --query 'older_than:3y' \
    --delete-only

  # Archive every read message older than three months by removing Inbox
  python scripts/gmail/evhstaff_gmail_inventory.py \
    --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json \
    --token-file /path/to/evhstaff_gmail_token.json \
    --query 'older_than:3m is:read' \
    --archive-read-old

  # Mark unread mail older than three months as read and remove Inbox
  python scripts/gmail/evhstaff_gmail_inventory.py \
    --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json \
    --token-file /path/to/evhstaff_gmail_token.json \
    --query 'in:inbox older_than:3m is:unread' \
    --mark-read-and-archive-unread-old

  # Build a sender-to-label routing map for mail newer than three months
  python scripts/gmail/evhstaff_gmail_inventory.py \
    --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json \
    --token-file /path/to/evhstaff_gmail_token.json \
    --query 'newer_than:3m' \
    --sender-routing-map
"""

from __future__ import annotations

import argparse
import base64
import collections
import email.message
import json
import os
import secrets
import tempfile
import threading
import time
import zipfile
import tempfile as _tempfile
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import email.utils
import re


SCOPES = [
    "https://mail.google.com/",
]

EMAIL_CATEGORY_CHOICES = [
    "Vendor",
    "Spam",
    "Staff",
    "Utilities",
    "Government",
    "Finance",
    "Insurance",
    "Client",
    "Laboratory",
    "Payroll",
    "Legal",
    "Technology",
    "Marketing",
    "Scheduling",
    "Other",
]

EMAIL_CATEGORY_ALIASES = {
    "Vendor": {"Vendor", "Vendors"},
    "Spam": {"Spam"},
    "Staff": {"Staff", "Employees"},
    "Utilities": {"Utilities"},
    "Government": {"Government"},
    "Finance": {"Banking", "Finance"},
    "Insurance": {"Insurance"},
    "Client": {"Client", "Clients"},
    "Laboratory": {"Laboratory", "Lab", "Labs"},
    "Payroll": {"Payroll"},
    "Legal": {"Legal"},
    "Technology": {"Technology", "Tech", "Admin"},
    "Marketing": {"Marketing"},
    "Scheduling": {"Scheduling", "Operations"},
    "Other": {"Other"},
}

EMAIL_CATEGORY_NORMALIZED = {
    alias.lower(): canonical
    for canonical, aliases in EMAIL_CATEGORY_ALIASES.items()
    for alias in aliases
}

KNOWN_STAFF_EMAILS = {
    "pacyna89@gmail.com",
    "felis.domesticus@yahoo.com",
    "katiebrown336@yahoo.com",
    "cbcdvm@gmail.com",
    "avaeiland@gmail.com",
    "kimmense@gmail.com",
    "tinaelyse12@hotmail.com",
    "elsadana52@gmail.com",
    "johnsoncolby685@gmail.com",
    "tbeans63@aol.com",
    "paws4aminute@myyahoo.com",
    "melisam1980@gmail.com",
    "trublu22@hotmail.com",
    "lisapotts828@gmail.com",
    "cpringle2299@gmail.com",
    "darlin_deb68@yahoo.com",
    "kristinshearer@yahoo.com",
    "drjenniferstenger@gmail.com",
    "tiffany_taylor4321@yahoo.com",
    "ralexw573@gmail.com",
    "ndubbs09@gmail.com",
}

EXPECTED_MAILBOX_EMAIL = "evhstaff@gmail.com"


@dataclass
class Token:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float
    scope: str
    token_type: str = "Bearer"

    @classmethod
    def from_file(cls, path: Path) -> "Token":
        data = json.loads(path.read_text())
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=float(data.get("expires_at", 0)),
            scope=data.get("scope", ""),
            token_type=data.get("token_type", "Bearer"),
        )

    def dump(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "token_type": self.token_type,
        }

    def expired(self) -> bool:
        return time.time() >= self.expires_at - 60


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "EVHGmailOAuth/1.0"

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        self.server.oauth_result = params  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>Authorization complete</h1><p>You may close this tab.</p></body></html>"
        )

    def log_message(self, *_args):  # quiet
        return


def load_client_config(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text())
    if "installed" not in data:
        raise SystemExit("Expected a desktop app client secret JSON with an 'installed' key.")
    return data["installed"]


def oauth_authorize(client: Dict[str, Any], token_file: Path) -> Token:
    base_redirect_uri = client["redirect_uris"][0]
    parsed = urllib.parse.urlparse(base_redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("This helper expects a localhost redirect URI.")

    # Installed-app OAuth on localhost may use an arbitrary free loopback port.
    # The credentials JSON commonly records http://localhost without a port, so
    # we bind an ephemeral port and use that exact redirect URI for the flow.
    with HTTPServer((parsed.hostname, 0), OAuthCallbackHandler) as probe:
        port = probe.server_address[1]
    redirect_uri = f"http://{parsed.hostname}:{port}"

    state = secrets.token_urlsafe(16)
    server = HTTPServer((parsed.hostname, port), OAuthCallbackHandler)
    server.oauth_result = None  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    print("Open this authorization URL if your browser did not open automatically:\n")
    print(auth_url)
    webbrowser.open(auth_url, new=1, autoraise=True)

    try:
        while server.oauth_result is None:
            time.sleep(0.2)
        result = server.oauth_result  # type: ignore[attr-defined]
        if result.get("state", [None])[0] != state:
            raise SystemExit("OAuth state mismatch.")
        if "error" in result:
            raise SystemExit(f"OAuth error: {result['error'][0]}")
        code = result.get("code", [None])[0]
        if not code:
            raise SystemExit("No authorization code received.")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    token = exchange_code_for_token(client, code, redirect_uri)
    token_file.write_text(json.dumps(token.dump(), indent=2, sort_keys=True))
    return token


def exchange_code_for_token(client: Dict[str, Any], code: str, redirect_uri: str) -> Token:
    payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return Token(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=time.time() + int(data.get("expires_in", 3600)),
        scope=data.get("scope", " ".join(SCOPES)),
        token_type=data.get("token_type", "Bearer"),
    )


def refresh_token(client: Dict[str, Any], token: Token) -> Token:
    if not token.refresh_token:
        raise SystemExit("Token expired and no refresh token is available; re-run auth.")
    payload = urllib.parse.urlencode(
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": token.refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    token.access_token = data["access_token"]
    token.expires_at = time.time() + int(data.get("expires_in", 3600))
    return token


def gmail_get(
    path: str,
    token: Token,
    params: Optional[Dict[str, str]] = None,
    client: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = "https://gmail.googleapis.com/gmail/v1" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token.access_token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and client is not None:
            token = refresh_token(client, token)
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token.access_token}"})
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        raise


def gmail_exact_count_messages(token: Token, query: str) -> int:
    count = 0
    for _ in iter_message_ids(token, query, 10**9):
        count += 1
        print(".", end="", flush=True)
    if count:
        print()
    return count


def _progress_label(label: str) -> None:
    print(f"{label}: ", end="", flush=True)


def _progress_dot() -> None:
    print(".", end="", flush=True)


def _progress_done() -> None:
    print()


def _phase(message: str) -> None:
    print(message, flush=True)


def gmail_list_labels(token: Token, client: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    data = gmail_get("/users/me/labels", token, client=client)
    out: Dict[str, str] = {}
    for label in data.get("labels", []):
        if isinstance(label, dict):
            label_id = label.get("id")
            name = label.get("name")
            if isinstance(label_id, str) and isinstance(name, str):
                out[label_id] = name
    return out


def gmail_get_raw(path: str, token: Token, params: Optional[Dict[str, str]] = None, client: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return gmail_get(path, token, params=params, client=client)


def gmail_get_profile(token: Token, client: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return gmail_get("/users/me/profile", token, client=client)


def verify_expected_mailbox(token: Token, client: Optional[Dict[str, Any]] = None) -> str:
    profile = gmail_get_profile(token, client=client)
    mailbox_email = str(profile.get("emailAddress", "")).strip().lower()
    if not mailbox_email:
        raise SystemExit("Could not determine authenticated Gmail mailbox.")
    if mailbox_email != EXPECTED_MAILBOX_EMAIL:
        raise SystemExit(
            f"Authenticated Gmail mailbox is {mailbox_email!r}, expected {EXPECTED_MAILBOX_EMAIL!r}. "
            "Use the evhstaff token file and reauthorize the correct account."
        )
    return mailbox_email


def iter_message_ids(token: Token, query: str, max_results: int, client: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
    page_token = None
    remaining = max_results
    page = 0
    while remaining > 0:
        page += 1
        params = {"q": query, "maxResults": str(min(100, remaining))}
        if page_token:
            params["pageToken"] = page_token
        _phase(f"[gmail] fetching message-id page {page} (remaining cap={remaining})")
        data = gmail_get("/users/me/messages", token, params=params, client=client)
        for msg in data.get("messages", []):
            yield msg
            remaining -= 1
            if remaining <= 0:
                return
        page_token = data.get("nextPageToken")
        if not page_token:
            return


def iter_message_records(token: Token, query: str, max_results: int, client: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
    page_token = None
    remaining = max_results
    page = 0
    while remaining > 0:
        page += 1
        params = {"q": query, "maxResults": str(min(100, remaining))}
        if page_token:
            params["pageToken"] = page_token
        _phase(f"[gmail] fetching message-record page {page} (remaining cap={remaining})")
        data = gmail_get("/users/me/messages", token, params=params, client=client)
        for msg in data.get("messages", []):
            yield msg
            remaining -= 1
            if remaining <= 0:
                return
        page_token = data.get("nextPageToken")
        if not page_token:
            return


def iter_message_full(token: Token, query: str, max_results: int, client: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
    _phase(f"[gmail] iterating full messages for query={query!r}")
    for msg in iter_message_ids(token, query, max_results, client=client):
        yield gmail_get(f"/users/me/messages/{msg['id']}", token, params={"format": "full"}, client=client)


def iter_message_metadata(token: Token, query: str, max_results: int, client: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
    _phase(f"[gmail] iterating metadata messages for query={query!r}")
    for msg in iter_message_ids(token, query, max_results, client=client):
        print(".", end="", flush=True)
        yield gmail_get(
            f"/users/me/messages/{msg['id']}",
            token,
            params={
                "format": "metadata",
                "metadataHeaders": "From",
            },
            client=client,
        )


def gmail_get_message_full(token: Token, message_id: str, client: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return gmail_get(f"/users/me/messages/{message_id}", token, params={"format": "full"}, client=client)


def parse_from_header(value: str) -> tuple[str, str]:
    name, email_addr = email.utils.parseaddr(value)
    return (name or email_addr or value).strip(), (email_addr or value).strip()


def _header_lookup(message: Dict[str, Any], *names: str) -> str:
    payload = message.get("payload", {})
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    if not isinstance(headers, list):
        return ""
    wanted = {name.lower() for name in names}
    for header in headers:
        if not isinstance(header, dict):
            continue
        header_name = str(header.get("name", "")).lower()
        if header_name in wanted:
            value = str(header.get("value", "")).strip()
            if value:
                return value
    return ""


def extract_sender_info(message: Dict[str, Any], token: Token) -> tuple[str, str, str, str]:
    from_header = _header_lookup(message, "From", "Sender", "Reply-To")
    subject = _header_lookup(message, "Subject")
    display_name, email_addr = parse_from_header(from_header)
    if not _looks_like_email(email_addr):
        raw_from, raw_name, raw_email, raw_subject = extract_sender_info_from_raw(token, str(message.get("id", "")))
        if _looks_like_email(raw_email):
            from_header = raw_from or from_header
            display_name = raw_name or display_name
            email_addr = raw_email or email_addr
            subject = raw_subject or subject
    return from_header, display_name, email_addr, subject


def extract_sender_info_from_raw(token: Token, message_id: str) -> tuple[str, str, str, str]:
    raw_message = gmail_get_message_raw(token, message_id)
    raw_b64 = raw_message.get("raw")
    if not isinstance(raw_b64, str) or not raw_b64:
        return "", "", "", ""
    eml_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
    from email.parser import BytesParser
    from email.policy import default

    parsed = BytesParser(policy=default).parsebytes(eml_bytes)
    from_header = str(parsed.get("From", "")).strip()
    subject = str(parsed.get("Subject", "")).strip()
    display_name, email_addr = parse_from_header(from_header)
    return from_header, display_name, email_addr, subject


def gmail_get_message_raw(token: Token, message_id: str, client: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return gmail_get(f"/users/me/messages/{message_id}", token, params={"format": "raw"}, client=client)


def gmail_send_message(token: Token, raw_message_b64url: str) -> Dict[str, Any]:
    req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw_message_b64url}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gmail send failed: HTTP {exc.code}\n{body}") from exc


def extract_message_classification_text(message: Dict[str, Any], token: Token, max_lines: int = 24) -> str:
    message_id = str(message.get("id", "")).strip()
    lines: list[str] = []

    def append_lines(text: str) -> None:
        for line in text.splitlines():
            line = line.rstrip()
            if line.strip():
                lines.append(line)
            if len(lines) >= max_lines:
                return

    if message_id:
        try:
            raw_message = gmail_get_message_raw(token, message_id)
            raw_b64 = raw_message.get("raw")
            if isinstance(raw_b64, str) and raw_b64:
                eml_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
                from email import policy
                from email.parser import BytesParser

                parsed = BytesParser(policy=policy.default).parsebytes(eml_bytes)
                subject = _decode_header(str(parsed.get("Subject", "")).strip())
                from_header = _decode_header(str(parsed.get("From", "")).strip())
                if subject:
                    lines.append(f"Subject: {subject}")
                if from_header:
                    lines.append(f"From: {from_header}")

                body_added = False
                if parsed.is_multipart():
                    for part in parsed.walk():
                        mime = part.get_content_type().lower()
                        if mime == "text/plain":
                            try:
                                content = part.get_content()
                            except Exception:
                                content = ""
                            if isinstance(content, str) and content.strip():
                                append_lines(content)
                                body_added = True
                                break
                    if not body_added:
                        for part in parsed.walk():
                            mime = part.get_content_type().lower()
                            if mime == "text/html":
                                try:
                                    content = part.get_content()
                                except Exception:
                                    content = ""
                                if isinstance(content, str) and content.strip():
                                    append_lines(_plain_text_from_html(content))
                                    body_added = True
                                    break
                else:
                    try:
                        content = parsed.get_content()
                    except Exception:
                        content = ""
                    if isinstance(content, str) and content.strip():
                        append_lines(content)
                        body_added = True

                if not body_added:
                    snippet = str(message.get("snippet", "")).strip()
                    if snippet:
                        append_lines(snippet)
        except Exception:
            snippet = str(message.get("snippet", "")).strip()
            if snippet:
                append_lines(snippet)
    else:
        snippet = str(message.get("snippet", "")).strip()
        if snippet:
            append_lines(snippet)

    return "\n".join(lines[:max_lines]).strip()


def gmail_delete_message(token: Token, message_id: str) -> None:
    req = urllib.request.Request(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        method="DELETE",
        headers={"Authorization": f"Bearer {token.access_token}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Delete failed for {message_id}: HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Delete failed for {message_id}: HTTP {exc.code}\n{body}") from exc


def gmail_archive_message(token: Token, message_id: str) -> None:
    req = urllib.request.Request(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
        method="POST",
        data=json.dumps({"removeLabelIds": ["INBOX"]}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Archive failed for {message_id}: HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Archive failed for {message_id}: HTTP {exc.code}\n{body}") from exc


def gmail_mark_read_and_archive(token: Token, message_id: str) -> None:
    req = urllib.request.Request(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
        method="POST",
        data=json.dumps({"removeLabelIds": ["INBOX", "UNREAD"]}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Mark-read/archive failed for {message_id}: HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Mark-read/archive failed for {message_id}: HTTP {exc.code}\n{body}") from exc


def export_messages_to_zip(token: Token, query: str, max_results: int, export_zip: Path) -> int:
    export_zip.parent.mkdir(parents=True, exist_ok=True)
    exported = 0
    _phase(f"[gmail] exporting messages for query={query!r} to {export_zip}")
    with tempfile.TemporaryDirectory(prefix="evh-gmail-export-") as tmpdir:
        tmp_path = Path(tmpdir)
        with zipfile.ZipFile(export_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for msg in iter_message_records(token, query, max_results):
                msg_id = msg["id"]
                raw_message = gmail_get_message_raw(token, msg_id)
                raw_b64 = raw_message.get("raw")
                if not isinstance(raw_b64, str) or not raw_b64:
                    continue
                eml_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
                eml_name = f"{msg_id}.eml"
                eml_path = tmp_path / eml_name
                eml_path.write_bytes(eml_bytes)
                zf.write(eml_path, arcname=eml_name)
                exported += 1
                print(".", end="", flush=True)
        if exported:
            _progress_done()
    return exported


def default_export_zip_path(query: str) -> Path:
    safe_query = "".join(ch if ch.isalnum() else "-" for ch in query).strip("-")
    safe_query = safe_query[:48] or "gmail-export"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path.home() / f"{safe_query}-{stamp}.zip"


def delete_messages(token: Token, client: Dict[str, Any], query: str, max_results: int) -> int:
    deleted = 0
    _phase(f"[gmail] deleting messages for query={query!r}")
    for msg in iter_message_records(token, query, max_results):
        try:
            gmail_delete_message(token, msg["id"])
        except RuntimeError as exc:
            if "HTTP 401" not in str(exc):
                raise
            token = refresh_token(client, token)
            gmail_delete_message(token, msg["id"])
        deleted += 1
        _progress_dot()
    if deleted:
        _progress_done()
    return deleted


def archive_messages(token: Token, client: Dict[str, Any], query: str, max_results: int) -> int:
    archived = 0
    _phase(f"[gmail] archiving messages for query={query!r}")
    for msg in iter_message_records(token, query, max_results):
        try:
            gmail_archive_message(token, msg["id"])
        except RuntimeError as exc:
            if "HTTP 401" not in str(exc):
                raise
            token = refresh_token(client, token)
            gmail_archive_message(token, msg["id"])
        archived += 1
        _progress_dot()
    if archived:
        _progress_done()
    return archived


def mark_read_and_archive_messages(token: Token, client: Dict[str, Any], query: str, max_results: int) -> int:
    processed = 0
    _phase(f"[gmail] marking read and archiving messages for query={query!r}")
    for msg in iter_message_records(token, query, max_results):
        try:
            gmail_mark_read_and_archive(token, msg["id"])
        except RuntimeError as exc:
            if "HTTP 401" not in str(exc):
                raise
            token = refresh_token(client, token)
            gmail_mark_read_and_archive(token, msg["id"])
        processed += 1
        _progress_dot()
    if processed:
        _progress_done()
    return processed


def report_label_overlap(token: Token, query: str, max_results: int) -> None:
    from collections import Counter

    label_names = gmail_list_labels(token)
    label_counter: Counter[str] = Counter()
    pair_counter: Counter[tuple[str, str]] = Counter()
    total_messages = 0

    for msg in iter_message_full(token, query, max_results):
        labels = sorted(set(label_id for label_id in msg.get("labelIds", []) if label_id != "INBOX"))
        if not labels:
            continue
        total_messages += 1
        label_counter.update(labels)
        for i, left in enumerate(labels):
            for right in labels[i + 1 :]:
                pair_counter[(left, right)] += 1
        print(".", end="", flush=True)

    if total_messages:
        _progress_done()

    print(json.dumps(
        {
            "query": query,
            "messages_with_labels": total_messages,
            "label_counts_top": [
                {"label_id": label_id, "label_name": label_names.get(label_id, label_id), "count": count}
                for label_id, count in label_counter.most_common(50)
            ],
            "label_pairs_top": [
                {
                    "left_id": a,
                    "left_name": label_names.get(a, a),
                    "right_id": b,
                    "right_name": label_names.get(b, b),
                    "count": c,
                }
                for (a, b), c in pair_counter.most_common(50)
            ],
        },
        indent=2,
    ))


def classify_sender(name: str, email_addr: str, labels: list[str]) -> Optional[str]:
    text = f"{name} {email_addr}".lower()
    label_blob = " ".join(labels).lower()
    email_lower = email_addr.lower()

    def hit(*needles: str) -> bool:
        return any(re.search(rf"(?<!\\w){re.escape(needle)}(?!\\w)", text) for needle in needles)

    domain = email_addr.split("@", 1)[1].lower() if "@" in email_addr else ""

    if email_lower == EXPECTED_MAILBOX_EMAIL:
        return "Staff"
    if email_lower in KNOWN_STAFF_EMAILS:
        return "Staff"

    # Strong, conservative rules first.
    if domain.endswith(".gov") or hit("irs", "dmv", "medicaid", "medicare"):
        return "Government"
    if hit("unsubscribe", "junk", "phishing", "scam"):
        return "Spam"
    if any(
        needle in text
        for needle in (
            "ziprecruiter",
            "monster",
            "linkedin job",
            "job alert",
            "job alerts",
            "talent acquisition",
            "recruiting",
            "recruiter",
            "staffing",
            "career",
            "careers",
            "hiring",
            "employment",
            "candidate",
        )
    ) or any(part in domain for part in ("ziprecruiter.com", "monster.com", "linkedin.com", "icims.com", "indeed.com", "glassdoor.com")):
        return "Spam"
    if any(
        needle in text
        for needle in (
            "rocket mortgage",
            "mortgage",
            "loan servicing",
            "servicing",
            "escrow",
            "payment due",
            "late fee",
            "statement available",
            "e-statement",
        )
    ) or any(part in domain for part in ("rocketmortgage.com", "rocketmortgage", "quickenloans.com")):
        return "Spam"
    if domain in {"comcast.net", "xfinity.com", "verizon.com", "att.com", "spectrum.com", "duke-energy.com", "dukeenergy.com"} or hit("utility", "electric", "water", "gas", "internet", "power"):
        return "Utilities"
    if hit("payroll", "w2", "w-2", "benefits", "onboarding", "hr") or domain.endswith("adp.com"):
        return "Payroll" if hit("payroll", "w2", "w-2") else "Staff"
    if hit("patient", "appointment", "booking", "inquiry", "support ticket") or "client" in label_blob:
        return "Client"
    if hit("invoice", "receipt", "vendor", "supplier", "purchase order", "order confirmation", "billing") or domain.startswith("no-reply"):
        return "Vendor"
    if hit("schedule", "reminder", "appointment reminder", "dispatch", "delivery", "workflow") or "scheduling" in label_blob:
        return "Scheduling"
    if hit("legal", "attorney", "contract", "compliance") or "legal" in label_blob:
        return "Legal"
    if hit("bank", "credit union", "wire", "routing number", "account statement", "account balance") or any(part in domain for part in ("bank", "creditunion", "synovus", "wellsfargo", "chase", "paypal", "synchrony")):
        return "Finance"
    if hit("insurance", "claim", "coverage", "policy") or "insurance" in label_blob:
        return "Insurance"
    if hit("laboratory", "lab", "pathology", "diagnostic", "specimen", "test result"):
        return "Laboratory"
    if hit("marketing", "newsletter", "campaign", "promotion", "advertising", "promo"):
        return "Marketing"
    if hit("software", "platform", "technology", "system", "it support") or "technology" in label_blob:
        return "Technology"

    # Slightly broader but still cautious fallbacks.
    if "staff" in label_blob or hit("employee", "employee portal", "timeclock"):
        return "Staff"
    if "vendor" in label_blob or "supplier" in label_blob:
        return "Vendor"
    if "government" in label_blob:
        return "Government"
    if "utilities" in label_blob:
        return "Utilities"
    if "banking" in label_blob:
        return "Finance"
    if "insurance" in label_blob:
        return "Insurance"
    if "marketing" in label_blob:
        return "Marketing"
    if "other" in label_blob:
        return "Other"

    # Do not guess on weak signals like generic "account", "admin", or "system".
    # Return None so the model can make the call.
    return None


def _looks_like_email(value: str) -> bool:
    return bool(value and "@" in value and "." in value.split("@")[-1])


def _format_unhandled_line(record: dict[str, Any]) -> str:
    parts = [
        f"message_id={record.get('message_id', '')}",
        f"reason={record.get('reason', '')}",
        f"from_header={record.get('from_header', '')}",
        f"name={record.get('name', '')}",
        f"email={record.get('email', '')}",
        f"label={record.get('label', '')}",
        f"subject={record.get('subject', '')}",
    ]
    return " | ".join(parts)


def _format_seconds(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def _load_sender_category_cache(path: Optional[Path]) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Sender category cache must contain a JSON object.")
    cache: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str):
            cache[key.lower()] = value
    return cache


def _save_sender_category_cache(path: Optional[Path], cache: dict[str, str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(cache.items())), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                out.append(item)
    return out


def _sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda item: (item.get("name", "").lower(), item.get("email", "").lower(), item.get("label", "").lower()),
    )


def _build_routing_payload(
    *,
    query: str,
    processed_count: int,
    categories: list[str],
    category_paths: dict[str, Path],
    needs_human_path: Path,
    unhandled_path: Path,
    llm_base_url: Optional[str],
    llm_model: Optional[str],
    llm_reason: str,
    llm_confidence: Optional[float],
    openai_model: Optional[str],
    openai_reasoning_effort: Optional[str],
    openai_text_verbosity: Optional[str],
) -> list[str]:
    lines: list[str] = []
    display_categories = {"Finance": "Banking"}
    for category in categories:
        display_category = display_categories.get(category, category)
        for item in _sorted_entries(_read_jsonl(category_paths[category])):
            name = str(item.get("name", "")).strip()
            email = str(item.get("email", "")).strip()
            if name and email:
                lines.append(f"{name} <{email}> -> {display_category}")
    for item in _sorted_entries(_read_jsonl(needs_human_path)):
        name = str(item.get("name", "")).strip()
        email = str(item.get("email", "")).strip()
        if name and email:
            lines.append(f"{name} <{email}> -> needs_human_intervention")
    for item in _sorted_entries(_read_jsonl(unhandled_path)):
        name = str(item.get("name", "")).strip()
        email = str(item.get("email", "")).strip()
        if name and email:
            lines.append(f"{name} <{email}> -> unhandled")
    return lines


def _read_top_sender_keys(path: Path) -> Optional[set[tuple[str, str]]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        email_addr = item.get("email")
        if isinstance(name, str) and isinstance(email_addr, str):
            out.add((name, email_addr))
    return out if out else set()


def _write_top_sender_keys(path: Path, keys: set[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [{"name": name, "email": email} for name, email in sorted(keys)]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_sender_counts(path: Path) -> Optional[collections.Counter[tuple[str, str]]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        email_addr = item.get("email")
        count = item.get("count")
        if isinstance(name, str) and isinstance(email_addr, str) and isinstance(count, int):
            counts[(name, email_addr)] = count
    return counts


def _write_sender_counts(path: Path, counts: collections.Counter[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"name": name, "email": email, "count": count}
        for (name, email), count in sorted(counts.items(), key=lambda item: (-item[1], item[0][0].lower(), item[0][1].lower()))
    ]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sender_cache_keys(name: str, email_addr: str) -> list[str]:
    keys: list[str] = []
    if email_addr:
        keys.append(f"email:{email_addr.lower()}")
        if "@" in email_addr:
            keys.append(f"domain:{email_addr.split('@', 1)[1].lower()}")
    if name:
        keys.append(f"name:{name.lower()}")
    return keys


def _llm_classify_sender(
    base_url: str,
    model: str,
    name: str,
    email_addr: str,
    subject: str,
    content_text: str,
    labels: list[str],
) -> tuple[Optional[str], Optional[float], str]:
    categories = EMAIL_CATEGORY_CHOICES
    prompt = {
        "mailbox_context": "This is a veterinary hospital email mailbox.",
        "sender_name": name,
        "sender_email": email_addr,
        "subject": subject,
        "content_text": content_text,
        "labels": labels,
        "categories": categories,
        "instructions": (
            "Choose exactly one category from categories. "
            "Treat job postings, generic recruiting, unrelated marketing, and non-business/non-animal mail as Spam. "
            "Staff is internal employee/human-resources mail. Client is pet-owner and patient-related mail. "
            "Vendor is supplier and business service outreach. Scheduling is workflow, appointments, dispatch, and reminders. "
            "Respond with JSON only: {\"category\":\"...\",\"confidence\":0-1,\"reason\":\"...\"}."
        ),
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify email messages for a veterinary hospital into one of fifteen categories. "
                    "Return only JSON. Use Spam for job postings, generic recruiting, unrelated marketing, "
                    "and non-business/non-animal mail. Normalize old labels to the closest canonical category."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
        "temperature": 0,
        "max_tokens": 256,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"].get("content", "")
    if not content:
        raise RuntimeError("LLM returned empty content")
    parsed = json.loads(content)
    category = parsed.get("category")
    confidence = parsed.get("confidence")
    reason = str(parsed.get("reason", "")).strip()
    category = EMAIL_CATEGORY_NORMALIZED.get(str(category).strip().lower(), category)
    if category not in categories:
        raise RuntimeError(f"LLM returned invalid category: {category!r}")
    conf_val = float(confidence) if confidence is not None else None
    return category, conf_val, reason


def _openai_classify_sender(
    api_key: str,
    model: str,
    name: str,
    email_addr: str,
    subject: str,
    content_text: str,
    labels: list[str],
    reasoning_effort: Optional[str] = None,
    text_verbosity: Optional[str] = None,
    base_url: str = "https://api.openai.com/v1",
) -> tuple[str, Optional[float], str]:
    categories = EMAIL_CATEGORY_CHOICES
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify email messages for a veterinary hospital into one of fifteen categories. "
                    "Return only JSON. Use Spam for job postings, generic recruiting, unrelated marketing, "
                    "and non-business/non-animal mail. Normalize old labels to the closest canonical category."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "mailbox_context": "This is a veterinary hospital email mailbox.",
                        "sender_name": name,
                        "sender_email": email_addr,
                        "subject": subject,
                        "content_text": content_text,
                        "labels": labels,
                        "categories": categories,
                        "instructions": "Choose exactly one category from categories. Respond with JSON only: {\"category\":\"...\",\"confidence\":0-1,\"reason\":\"...\"}.",
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": 96,
        "response_format": {"type": "json_object"},
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if text_verbosity:
        payload["text"] = {"verbosity": text_verbosity}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"].get("content", "")
    parsed = json.loads(content)
    category = parsed.get("category")
    category = EMAIL_CATEGORY_NORMALIZED.get(str(category).strip().lower(), category)
    if category not in categories:
        raise RuntimeError(f"OpenAI returned invalid category: {category!r}")
    confidence = parsed.get("confidence")
    reason = str(parsed.get("reason", "")).strip()
    conf_val = float(confidence) if confidence is not None else None
    return category, conf_val, reason


def report_sender_routing_map(
    token: Token,
    client: Dict[str, Any],
    query: str,
    max_results: int,
    exact_count: Optional[int] = None,
    json_output: Optional[Path] = None,
    unhandled_output: Optional[Path] = None,
    fail_on_unhandled: bool = False,
    llm_base_url: Optional[str] = None,
    llm_model: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_model: Optional[str] = None,
    openai_reasoning_effort: Optional[str] = None,
    openai_text_verbosity: Optional[str] = None,
    top_senders_path: Optional[Path] = None,
    sender_category_cache_path: Optional[Path] = None,
) -> None:
    _phase(f"[routing] starting sender routing map for query={query!r}")
    label_names = gmail_list_labels(token)
    categories = EMAIL_CATEGORY_CHOICES
    seen: set[tuple[str, str, str]] = set()
    sender_seen: dict[str, str] = {}
    processed_count = 0
    unhandled_count = 0
    started_at = time.time()
    json_snapshot_path = json_output
    unhandled_fh = unhandled_output.open("a", encoding="utf-8") if unhandled_output is not None else None
    sender_category_cache = _load_sender_category_cache(sender_category_cache_path)
    sender_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    scratch_dir = Path(tempfile.mkdtemp(prefix="evh-gmail-routing-"))
    category_paths = {category: scratch_dir / f"{category.lower()}.jsonl" for category in categories}
    needs_human_path = scratch_dir / "needs_human_intervention.jsonl"
    unhandled_path = scratch_dir / "unhandled.jsonl"
    
    def write_snapshot(llm_reason: str = "", llm_confidence: Optional[float] = None) -> None:
        if json_snapshot_path is None:
            return
        payload = _build_routing_payload(
            query=query,
            processed_count=processed_count,
            categories=categories,
            category_paths=category_paths,
            needs_human_path=needs_human_path,
            unhandled_path=unhandled_path,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_reason=llm_reason,
            llm_confidence=llm_confidence,
            openai_model=openai_model,
            openai_reasoning_effort=openai_reasoning_effort,
            openai_text_verbosity=openai_text_verbosity,
        )
        snapshot_text = json.dumps(payload, indent=2) + "\n"
        tmp_fd, tmp_name = _tempfile.mkstemp(prefix=json_snapshot_path.name + ".", dir=str(json_snapshot_path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(snapshot_text)
            os.replace(tmp_name, json_snapshot_path)
        finally:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError:
                pass

    top_sender_keys: set[tuple[str, str]] = set()
    if top_senders_path is not None:
        cached_top = _read_top_sender_keys(top_senders_path)
        if cached_top:
            top_sender_keys = cached_top
            _phase(f"[routing] loaded top sender list from {top_senders_path}")
        else:
            _phase(f"[routing] no top sender checkpoint found at {top_senders_path}; recounting")
    if not top_sender_keys:
        for msg in iter_message_metadata(token, query, max_results, client=client):
            label_ids = [label_id for label_id in msg.get("labelIds", []) if label_id not in {"INBOX", "UNREAD"}]
            labels = [label_names.get(label_id, label_id) for label_id in label_ids]
            if not labels:
                continue
            from_header, display_name, email_addr, _subject = extract_sender_info(msg, token)
            if _looks_like_email(email_addr):
                sender_counts[(display_name, email_addr)] += 1

        top_sender_keys = set(sender_counts.keys())
        if top_senders_path is not None:
            _phase(f"[routing] wrote top sender list to {top_senders_path}")
        _phase(f"[routing] distinct sender email keys: {len(sender_counts)}; sender classification window: {len(top_sender_keys)}")
    if sender_counts:
        print()
    write_snapshot()

    try:
        classifiers_enabled = ["local"]
        if openai_api_key and openai_model:
            classifiers_enabled.append("openai")
        _phase(f"[routing] classifiers enabled: {', '.join(classifiers_enabled)}")
        _phase(f"[routing] streaming classification pass for query={query!r}")
        for msg in iter_message_full(token, query, max_results, client=client):
            label_ids = [label_id for label_id in msg.get("labelIds", []) if label_id not in {"INBOX", "UNREAD"}]
            labels = [label_names.get(label_id, label_id) for label_id in label_ids]
            if not labels:
                continue
            from_header, display_name, email_addr, subject = extract_sender_info(msg, token)
            sender_key = email_addr.lower()
            if sender_key in sender_seen:
                cached_live_category = sender_seen[sender_key]
                processed_count += 1
                live_category = cached_live_category
                elapsed = max(time.time() - started_at, 0.001)
                eta = None
                if exact_count is not None and exact_count > 0 and processed_count > 0:
                    eta_seconds = max((exact_count - processed_count) * (elapsed / processed_count), 0.0)
                    eta = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
                if exact_count is not None and exact_count > 0:
                    eta_part = f" ETA {eta}" if eta else ""
                    print(f"({processed_count}/{exact_count}) {processed_count}. {display_name} <{email_addr}> -> {live_category}{eta_part}")
                else:
                    print(f"{processed_count}. {display_name} <{email_addr}> -> {live_category}")
                continue
            key = (display_name, email_addr, ", ".join(labels))
            if key in seen:
                continue
            seen.add(key)
            processed_count += 1

            if not _looks_like_email(email_addr):
                unhandled_count += 1
                reason = "missing_sender_header" if not from_header else "no_valid_email"
                record = {
                    "message_id": msg.get("id", ""),
                    "from_header": from_header,
                    "name": display_name,
                    "email": email_addr,
                    "label": ", ".join(labels),
                    "subject": subject,
                    "reason": reason,
                }
                if unhandled_fh is not None:
                    unhandled_fh.write(_format_unhandled_line(record) + "\n")
                    unhandled_fh.flush()
                with unhandled_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                elapsed = max(time.time() - started_at, 0.001)
                eta = None
                if exact_count is not None and exact_count > 0 and processed_count > 0:
                    eta_seconds = max((exact_count - processed_count) * (elapsed / processed_count), 0.0)
                    eta = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
                if exact_count is not None and exact_count > 0:
                    eta_part = f" ETA {eta}" if eta else ""
                    print(f"({processed_count}/{exact_count}) {processed_count}. Unhandled message {unhandled_count}: {display_name} <{email_addr}>{eta_part}")
                else:
                    print(f"{processed_count}. Unhandled message {unhandled_count}: {display_name} <{email_addr}>")
                continue

            content_text = extract_message_classification_text(msg, token)
            # Preserve the deterministic local rules engine, but never expose it as "heuristic"
            # in user-facing routing output.
            decision_source = "local"
            decision_started = time.time()
            cached_category = None
            for cache_key in _sender_cache_keys(display_name, email_addr):
                cached_category = sender_category_cache.get(cache_key)
                if cached_category:
                    break
            if cached_category:
                suggested = cached_category
                decision_source = "local"
            else:
                suggested = classify_sender(display_name, email_addr, labels)
            llm_confidence: Optional[float] = None
            llm_reason = ""
            sender_key = (display_name, email_addr)
            if openai_api_key and openai_model and suggested is None and sender_key in top_sender_keys:
                try:
                    openai_suggested, llm_confidence, llm_reason = _openai_classify_sender(
                        openai_api_key,
                        openai_model,
                        display_name,
                        email_addr,
                        subject,
                        content_text,
                        labels,
                        reasoning_effort=openai_reasoning_effort,
                        text_verbosity=openai_text_verbosity,
                    )
                    suggested = openai_suggested
                    decision_source = "openai"
                except Exception as exc:
                    llm_reason = f"openai_error:{exc}"
            if llm_base_url and llm_model and suggested is None and sender_key in top_sender_keys:
                try:
                    llm_suggested, llm_confidence, llm_reason = _llm_classify_sender(
                        llm_base_url,
                        llm_model,
                        display_name,
                        email_addr,
                        subject,
                        content_text,
                        labels,
                    )
                    suggested = llm_suggested
                    decision_source = "qwen"
                except Exception as exc:
                    llm_reason = f"llm_error:{exc}"
            decision_seconds = max(time.time() - decision_started, 0.0)
            entry = {
                "message_id": msg.get("id", ""),
                "name": display_name,
                "email": email_addr,
                "label": ", ".join(labels),
                "subject": subject,
                "content_text": content_text,
                "decision_source": decision_source,
                "decision_seconds": round(decision_seconds, 3),
            }
            if suggested is None:
                live_category = "needs_human_intervention"
                with needs_human_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            else:
                live_category = suggested
                sender_seen[sender_key] = live_category
                sender_seen[sender_key] = live_category
                for cache_key in _sender_cache_keys(display_name, email_addr):
                    sender_category_cache[cache_key] = suggested
                _save_sender_category_cache(sender_category_cache_path, sender_category_cache)
                with category_paths[suggested].open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            elapsed = max(time.time() - started_at, 0.001)
            eta = None
            if exact_count is not None and exact_count > 0 and processed_count > 0:
                eta_seconds = max((exact_count - processed_count) * (elapsed / processed_count), 0.0)
                eta = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
            if exact_count is not None and exact_count > 0:
                eta_part = f" ETA {eta}" if eta else ""
                print(f"({processed_count}/{exact_count}) {processed_count}. {display_name} <{email_addr}> -> {live_category}{eta_part}")
            else:
                print(f"{processed_count}. {display_name} <{email_addr}> -> {live_category}")

            write_snapshot(llm_reason=llm_reason, llm_confidence=llm_confidence)
    finally:
        if unhandled_fh is not None:
            unhandled_fh.close()

    if processed_count:
        print()

    payload = _build_routing_payload(
        query=query,
        processed_count=processed_count,
        categories=categories,
        category_paths=category_paths,
        needs_human_path=needs_human_path,
        unhandled_path=unhandled_path,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_reason="",
        llm_confidence=None,
        openai_model=openai_model,
        openai_reasoning_effort=openai_reasoning_effort,
        openai_text_verbosity=openai_text_verbosity,
    )
    rendered = "\n".join(payload)
    print(rendered)
    if json_output is not None:
        json_output.write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    if unhandled_output is not None:
        unhandled_records = _read_jsonl(unhandled_path)
        unhandled_output.write_text("\n".join(_format_unhandled_line(record) for record in unhandled_records) + ("\n" if unhandled_records else ""), encoding="utf-8")
    unhandled_records = _read_jsonl(unhandled_path)
    if fail_on_unhandled and unhandled_records:
        print(json.dumps({"query": query, "unhandled_count": len(unhandled_records)}, indent=2))
        raise SystemExit(f"Unhandleable sender records found: {len(unhandled_records)}")


def summarize_messages(token: Token, query: str, max_results: int) -> None:
    ids = list(iter_message_ids(token, query, max_results))
    print(json.dumps({"query": query, "count": len(ids), "message_ids": ids}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secrets", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--query", default="in:inbox")
    parser.add_argument("--max-results", type=int, default=0, help="0 means no limit")
    parser.add_argument("--export-zip", nargs="?", const="", default="", help="Optional ZIP path; omit value to use a timestamped default")
    parser.add_argument("--delete-after-export", action="store_true")
    parser.add_argument("--delete-only", action="store_true")
    parser.add_argument("--archive-read-old", action="store_true")
    parser.add_argument("--mark-read-and-archive-unread-old", action="store_true")
    parser.add_argument("--sender-routing-map", action="store_true")
    parser.add_argument("--sender-routing-map-json-output", help="Write the final sender-routing-map artifact to a clean JSON file")
    parser.add_argument("--sender-routing-map-unhandled-output", help="Write unhandleable sender records to JSON")
    parser.add_argument("--sender-routing-map-fail-on-unhandled", action="store_true", help="Exit non-zero if any sender records cannot be handled")
    parser.add_argument("--llm-classifier-base-url", help="OpenAI-compatible base URL for local LLM classification")
    parser.add_argument("--llm-classifier-model", default="qwen/qwen3.6-27b", help="Model id to send to the local LLM endpoint")
    parser.add_argument("--openai-classifier-model", default="gpt-5.6-mini", help="OpenAI model for fallback classification of needs_user_choice")
    parser.add_argument("--openai-api-key-env", default="OPENAI_API_KEY", help="Environment variable containing the OpenAI API key")
    parser.add_argument("--openai-reasoning-effort", default="none", help="Optional reasoning.effort value for OpenAI-compatible requests")
    parser.add_argument("--openai-text-verbosity", default="low", help="Optional text.verbosity value for OpenAI-compatible requests")
    parser.add_argument("--top-senders-path", default="/tmp/evh_gmail_top_senders.json", help="Persistent sender list checkpoint")
    parser.add_argument("--sender-category-cache", default="/tmp/evh_gmail_sender_category_cache.json", help="Persistent sender/category cache JSON file")
    parser.add_argument("--label-overlap", action="store_true")
    parser.add_argument("--exact-count", action="store_true")
    args = parser.parse_args()

    client_path = Path(args.client_secrets)
    token_path = Path(args.token_file)
    client = load_client_config(client_path)

    token: Optional[Token] = None
    if token_path.exists():
        token = Token.from_file(token_path)
        if token.expired():
            token = refresh_token(client, token)
            token_path.write_text(json.dumps(token.dump(), indent=2, sort_keys=True))

    if token is None:
        token = oauth_authorize(client, token_path)

    authenticated_mailbox = verify_expected_mailbox(token, client=client)
    print(f"=== Authenticated Gmail mailbox: {authenticated_mailbox} ===")

    max_results = args.max_results if args.max_results and args.max_results > 0 else 10**9

    if args.delete_only:
        exact_count = gmail_exact_count_messages(token, args.query)
        print(json.dumps({"query": args.query, "exact_count": exact_count}, indent=2))
        deleted = delete_messages(token, client, args.query, max_results)
        print(json.dumps(
            {
                "query": args.query,
                "deleted_count": deleted,
                "permanent_delete": True,
            },
            indent=2,
        ))
        return 0

    if args.archive_read_old:
        exact_count = gmail_exact_count_messages(token, args.query)
        print(json.dumps({"query": args.query, "exact_count": exact_count}, indent=2))
        archived = archive_messages(token, client, args.query, max_results)
        print(json.dumps(
            {
                "query": args.query,
                "archived_count": archived,
                "action": "removed_inbox_label",
            },
            indent=2,
        ))
        return 0

    if args.mark_read_and_archive_unread_old:
        exact_count = gmail_exact_count_messages(token, args.query)
        print(json.dumps({"query": args.query, "exact_count": exact_count}, indent=2))
        processed = mark_read_and_archive_messages(token, client, args.query, max_results)
        print(json.dumps(
            {
                "query": args.query,
                "processed_count": processed,
                "action": "mark_read_and_remove_inbox",
            },
            indent=2,
        ))
        return 0

    if args.sender_routing_map:
        json_output = Path(args.sender_routing_map_json_output) if args.sender_routing_map_json_output else None
        unhandled_output = Path(args.sender_routing_map_unhandled_output) if args.sender_routing_map_unhandled_output else None
        openai_api_key = os.environ.get(args.openai_api_key_env) if args.openai_classifier_model else None
        if args.openai_classifier_model and not openai_api_key:
            raise SystemExit(f"Missing OpenAI API key in ${args.openai_api_key_env}")
        report_sender_routing_map(
            token,
            client,
            args.query,
            max_results,
            json_output=json_output,
            unhandled_output=unhandled_output,
            fail_on_unhandled=args.sender_routing_map_fail_on_unhandled,
            llm_base_url=args.llm_classifier_base_url,
            llm_model=args.llm_classifier_model,
            openai_api_key=openai_api_key,
            openai_model=args.openai_classifier_model,
            openai_reasoning_effort=args.openai_reasoning_effort,
            openai_text_verbosity=args.openai_text_verbosity,
            top_senders_path=Path(args.top_senders_path) if args.top_senders_path else None,
            sender_category_cache_path=Path(args.sender_category_cache) if args.sender_category_cache else None,
        )
        return 0

    if args.label_overlap:
        exact_count = gmail_exact_count_messages(token, args.query)
        print(json.dumps({"query": args.query, "exact_count": exact_count}, indent=2))
        report_label_overlap(token, args.query, max_results)
        return 0

    if args.exact_count:
        print(json.dumps({"query": args.query, "exact_count": gmail_exact_count_messages(token, args.query)}, indent=2))
        return 0

    if args.export_zip is not None:
        exact_count = gmail_exact_count_messages(token, args.query)
        print(json.dumps({"query": args.query, "exact_count": exact_count}, indent=2))
        export_path = Path(args.export_zip) if args.export_zip else default_export_zip_path(args.query)
        exported = export_messages_to_zip(token, args.query, max_results, export_path)
        print(json.dumps(
            {
                "query": args.query,
                "export_zip": str(export_path),
                "count": exported,
            },
            indent=2,
        ))
        if args.delete_after_export:
            deleted = delete_messages(token, args.query, max_results)
            print(json.dumps(
                {
                    "query": args.query,
                    "deleted_count": deleted,
                    "permanent_delete": True,
                },
                indent=2,
            ))
    else:
        summarize_messages(token, args.query, max_results if max_results < 10**9 else 20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
