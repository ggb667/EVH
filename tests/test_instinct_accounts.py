from __future__ import annotations

from scripts.instinct_accounts import normalize_account


def test_normalize_account_picks_primary_phone_and_display_name():
    account = normalize_account(
        {
            "id": "acct-1",
            "pimsCode": "9758",
            "pimsId": None,
            "primaryContact": {
                "nameFirst": "Nathan",
                "nameMiddle": None,
                "nameLast": "Deschenes",
                "communicationDetails": [
                    {"type": "email", "value": "nathan@example.com"},
                    {"type": "mobile", "value": "(555) 010-1212"},
                ],
            },
            "updatedAt": "2026-04-20T12:00:00Z",
        }
    )

    assert account.display_name == "Nathan Deschenes"
    assert account.primary_phone == "5550101212"
    assert account.pims_id is None
