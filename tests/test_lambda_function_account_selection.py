import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lambda_function import resolve_target_accounts


def test_resolve_target_accounts_filters_requested_mailbox():
    accounts = [
        {"mailbox_email": "evhstaff@gmail.com"},
        {"mailbox_email": "cbcdvm@gmail.com"},
        {"mailbox_email": "ggb667@gmail.com"},
    ]

    filtered = resolve_target_accounts(accounts, "ggb667@gmail.com")

    assert filtered == [{"mailbox_email": "ggb667@gmail.com"}]


def test_resolve_target_accounts_returns_all_when_unfiltered():
    accounts = [
        {"mailbox_email": "evhstaff@gmail.com"},
        {"mailbox_email": "ggb667@gmail.com"},
    ]

    filtered = resolve_target_accounts(accounts, "")

    assert filtered == accounts
