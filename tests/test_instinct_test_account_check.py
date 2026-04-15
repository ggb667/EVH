from __future__ import annotations

from scripts import instinct_test_account_check as check


class _FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def test_fetch_partner_token_uses_access_token_field(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["data"] = req.data.decode("utf-8")
        return _FakeResponse(200, '{"access_token":"abc123"}')

    monkeypatch.setattr(check.request, "urlopen", fake_urlopen)

    token = check._fetch_partner_token("https://partner.example/token", "cid", "secret")

    assert token == "abc123"
    assert "grant_type=client_credentials" in captured["data"]
    assert "client_id=cid" in captured["data"]
    assert "client_secret=secret" in captured["data"]


def test_fetch_partner_token_accepts_token_alias(monkeypatch):
    def fake_urlopen(req, timeout=30):
        return _FakeResponse(200, '{"token":"xyz789"}')

    monkeypatch.setattr(check.request, "urlopen", fake_urlopen)

    token = check._fetch_partner_token("https://partner.example/token", "cid", "secret")

    assert token == "xyz789"


def test_discover_account_defaults_uses_live_alert_and_reminder_ids(monkeypatch):
    class FakeClient:
        def fetch_alerts(self):
            return 200, {"alerts": [{"id": 333}, {"id": 444}]}

        def fetch_reminders(self):
            return 200, {"reminders": [{"id": 777}, {"id": 888}]}

    alert_id, reminder_ids = check._discover_account_defaults(FakeClient())

    assert alert_id == 333
    assert reminder_ids == (777, 888)
