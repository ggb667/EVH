from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import boto3
except ImportError:  # pragma: no cover - local test fallback
    boto3 = None

from scripts.gmail.daily_email_summary import (
    DEFAULT_DAILY_SUMMARY_RECIPIENT,
    DEFAULT_OPENAI_MODEL,
    EXPECTED_MAILBOX_EMAIL,
    build_dry_run_result,
    build_email_message,
    build_summary_prompt,
    checkpoint_parameter_for_mailbox,
    extract_response_text,
    load_messages,
    load_sent_messages,
    load_client_config,
    parse_summary_result,
    render_markdown,
    reconcile_summary_result,
    SentItem,
    refresh_token,
    Token,
    verify_expected_mailbox,
    _openai_responses_completion,
)
from scripts.gmail.evhstaff_gmail_inventory import gmail_send_message

SECRETS_CLIENT = boto3.client("secretsmanager") if boto3 and hasattr(boto3, "client") else None
PARAMETER_CLIENT = boto3.client("ssm") if boto3 and hasattr(boto3, "client") else None


def load_oauth_secret(secret_arn: str) -> dict:
    if SECRETS_CLIENT is None:
        raise RuntimeError("boto3 secretsmanager client is unavailable.")
    response = SECRETS_CLIENT.get_secret_value(SecretId=secret_arn)
    secret_string = response.get("SecretString", "")
    if not secret_string:
        raise RuntimeError("Secrets Manager returned an empty secret string.")
    secret = json.loads(secret_string)
    if not isinstance(secret, dict):
        raise RuntimeError("OAuth secret must be a JSON object.")
    return secret


def load_accounts() -> list[dict]:
    raw = os.environ.get("DAILY_SUMMARY_ACCOUNTS_JSON", "")
    if not raw.strip():
        return []
    accounts = json.loads(raw)
    if not isinstance(accounts, list):
        raise RuntimeError("DAILY_SUMMARY_ACCOUNTS_JSON must be a JSON array.")
    result = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        mailbox_email = str(account.get("mailbox_email", "")).strip().lower()
        if not mailbox_email:
            continue
        result.append(account)
    return result


def sanitize_mailbox_key(mailbox_email: str) -> str:
    return mailbox_email.strip().lower().replace("@", "_").replace(".", "_")


def mailbox_checkpoint_parameter(mailbox_email: str) -> str:
    return f"/evh/daily-summary/{sanitize_mailbox_key(mailbox_email)}/last_successful_run"


def find_account(mailbox_email: str, accounts: list[dict]) -> dict:
    mailbox_email = mailbox_email.strip().lower()
    for account in accounts:
        if str(account.get("mailbox_email", "")).strip().lower() == mailbox_email:
            return account
    return {}


def load_checkpoint(parameter_name: str) -> str | None:
    if PARAMETER_CLIENT is None:
        return None
    try:
        response = PARAMETER_CLIENT.get_parameter(Name=parameter_name)
    except Exception:
        return None
    value = response.get("Parameter", {}).get("Value", "")
    return value if isinstance(value, str) and value.strip() else None


def save_checkpoint(parameter_name: str) -> None:
    if PARAMETER_CLIENT is None:
        return
    PARAMETER_CLIENT.put_parameter(
        Name=parameter_name,
        Value=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        Type="String",
        Overwrite=True,
    )


def apply_checkpoint(query: str, checkpoint_value: str | None) -> str:
    if not checkpoint_value:
        return query
    date_part = checkpoint_value[:10]
    query = query.strip()
    prefix = f"after:{date_part.replace('-', '/')}"
    return f"{prefix} {query}".strip() if query else prefix


def resolve_target_accounts(accounts: list[dict], requested_mailbox: str) -> list[dict]:
    requested_mailbox = requested_mailbox.strip().lower()
    if not accounts:
        return []
    if not requested_mailbox:
        return accounts
    return [
        account
        for account in accounts
        if str(account.get("mailbox_email", "")).strip().lower() == requested_mailbox
    ]


def _run_for_account(account: dict, event: dict[str, Any]) -> dict[str, Any]:
    mailbox_email = str(account.get("mailbox_email", "")).strip().lower()
    if not mailbox_email:
        return {"mailbox_email": "", "status": "skipped", "reason": "missing mailbox email"}

    secret_arn = str(account.get("oauth_secret_arn", "")).strip()
    if not secret_arn:
        raise RuntimeError(f"No OAuth secret ARN configured for mailbox {mailbox_email!r}.")
    oauth = load_oauth_secret(secret_arn)

    to_addr = str(account.get("daily_summary_to", DEFAULT_DAILY_SUMMARY_RECIPIENT)).strip() or DEFAULT_DAILY_SUMMARY_RECIPIENT
    checkpoint_param = str(
        account.get("checkpoint_parameter")
        or os.environ.get("DAILY_SUMMARY_CHECKPOINT_PARAMETER")
        or checkpoint_parameter_for_mailbox(mailbox_email)
    )

    client_json = {
        "installed": {
            "client_id": oauth["client_id"],
            "client_secret": oauth["client_secret"],
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "redirect_uris": ["http://localhost"],
        }
    }
    client_path = Path("/tmp/gmail_client.json")
    client_path.write_text(json.dumps(client_json), encoding="utf-8")
    client = load_client_config(client_path)

    token = Token(
        access_token="",
        refresh_token=oauth["refresh_token"],
        token_type="Bearer",
        expires_at=0,
        scope="https://mail.google.com/",
    )
    print(f"[oauth] mailbox={mailbox_email} token_source=secret_only cache_ignored=True")
    token = refresh_token(client, token)

    verify_expected_mailbox(token, client, mailbox_email)

    checkpoint_value = load_checkpoint(checkpoint_param)
    query = apply_checkpoint(os.environ.get("DAILY_SUMMARY_QUERY", "newer_than:1d"), checkpoint_value)
    sent_query = apply_checkpoint(os.environ.get("DAILY_SUMMARY_SENT_QUERY", "in:sent newer_than:1d"), checkpoint_value)
    max_results = int(os.environ.get("DAILY_SUMMARY_MAX_RESULTS", "30"))
    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    send_email = os.environ.get("DAILY_SUMMARY_SEND_EMAIL", "true").lower() in ("1", "true", "yes", "y")

    items = load_messages(token, query, max_results)
    sent_items = [
        {
            "message_id": item.message_id,
            "thread_id": item.thread_id,
            "recipients": item.recipients,
            "subject": item.subject,
            "body_text": item.body_text,
        }
        for item in load_sent_messages(token, sent_query, max_results)
    ]

    if not items:
        rendered = "# Communication Summary\n\nNo messages matched the query.\n"
        return {"mailbox_email": mailbox_email, "status": "no_messages", "count": 0, "summary": rendered}

    if event.get("dry_run", False):
        result = build_dry_run_result(items, query)
    else:
        api_key = os.environ["OPENAI_API_KEY"]
        messages = build_summary_prompt(items, query)
        response = _openai_responses_completion(api_key, model, messages)
        content = extract_response_text(response)
        if not content:
            raise RuntimeError("OpenAI returned empty content.")
        result = parse_summary_result(content)

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
    result = reconcile_summary_result(result, items, sent_records)
    result["sent_today"] = sent_items
    rendered = render_markdown(result, query, len(items))

    Path(f"/tmp/evh_daily_email_summary_{sanitize_mailbox_key(mailbox_email)}.md").write_text(rendered, encoding="utf-8")
    Path(f"/tmp/evh_daily_email_summary_{sanitize_mailbox_key(mailbox_email)}.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sent_result = None
    if send_email and not event.get("dry_run", False):
        raw_message = build_email_message("Daily Communication Summary", rendered, from_addr=mailbox_email, to_addrs=[to_addr])
        sent_result = gmail_send_message(token, raw_message)

    if not event.get("dry_run", False):
        save_checkpoint(checkpoint_param)

    return {"mailbox_email": mailbox_email, "status": "ok", "sent_email": bool(sent_result), "sent_result": sent_result, "query": query, "count": len(items)}


def lambda_handler(event, context):
    accounts = load_accounts()
    requested_mailbox = (
        str(event.get("mailbox_email", "")).strip().lower()
        or os.environ.get("TARGET_MAILBOX_EMAIL", "").strip().lower()
        or os.environ.get("EXPECTED_MAILBOX_EMAIL", "").strip().lower()
    )

    target_accounts = resolve_target_accounts(accounts, requested_mailbox) if accounts else []
    if accounts and requested_mailbox and not target_accounts:
        raise RuntimeError(f"No account configured for mailbox {requested_mailbox!r}.")
    if not accounts:
        target_accounts = [
            {
                "mailbox_email": requested_mailbox or EXPECTED_MAILBOX_EMAIL,
                "daily_summary_to": os.environ.get("DAILY_SUMMARY_TO", DEFAULT_DAILY_SUMMARY_RECIPIENT),
                "checkpoint_parameter": os.environ.get("DAILY_SUMMARY_CHECKPOINT_PARAMETER")
                or mailbox_checkpoint_parameter(requested_mailbox or EXPECTED_MAILBOX_EMAIL),
                "oauth_secret_arn": os.environ.get("GMAIL_OAUTH_SECRET_ARN", ""),
            }
        ]

    results: list[dict[str, object]] = []
    for account in target_accounts:
        mailbox_email = str(account.get("mailbox_email", "")).strip().lower()
        if not mailbox_email:
            continue
        results.append(_run_for_account(account, event))

    return {"statusCode": 200, "body": json.dumps({"message": "Daily summary completed.", "results": results})}


if __name__ == "__main__":
    raise SystemExit(lambda_handler({}, None))
