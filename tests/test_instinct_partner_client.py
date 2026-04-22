from __future__ import annotations

from scripts.instinct_partner_client import InstinctPartnerClient


def test_iter_accounts_pages_through_after_cursor(monkeypatch):
    client = InstinctPartnerClient("https://partner.instinctvet.com", "token")
    calls: list[dict[str, object]] = []
    responses = iter(
        [
            {"data": [{"id": "a1"}], "metadata": {"after": "c1"}},
            {"data": [{"id": "a2"}], "metadata": {"after": None}},
        ]
    )

    def fake_get(self, path, params=None):
        assert path == "/v1/accounts"
        calls.append(dict(params or {}))
        return next(responses)

    monkeypatch.setattr(InstinctPartnerClient, "_get", fake_get)

    assert list(client.iter_accounts({"updatedSince": "2026-01-01"})) == [{"id": "a1"}, {"id": "a2"}]
    assert calls == [
        {"limit": 100, "updatedSince": "2026-01-01"},
        {"limit": 100, "updatedSince": "2026-01-01", "pageCursor": "c1", "pageDirection": "after"},
    ]


def test_iter_appointments_pages_through_after_cursor(monkeypatch):
    client = InstinctPartnerClient("https://partner.instinctvet.com", "token")
    calls: list[dict[str, object]] = []
    responses = iter(
        [
            {"data": [{"id": 1}], "metadata": {"after": "c1"}},
            {"data": [{"id": 2}], "metadata": {"after": None}},
        ]
    )

    def fake_get(self, path, params=None):
        assert path == "/v1/appointments"
        calls.append(dict(params or {}))
        return next(responses)

    monkeypatch.setattr(InstinctPartnerClient, "_get", fake_get)

    assert list(client.iter_appointments({"updatedSince": "2026-01-01"})) == [{"id": 1}, {"id": 2}]
    assert calls == [
        {"limit": 100, "updatedSince": "2026-01-01"},
        {"limit": 100, "updatedSince": "2026-01-01", "pageCursor": "c1", "pageDirection": "after"},
    ]
