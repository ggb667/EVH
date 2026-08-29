from __future__ import annotations

from pathlib import Path

from scripts import instinct_sync_runner as runner


def test_runner_requires_a_feed():
    parser = runner.build_parser()
    try:
        runner.run(["--base-url", "https://partner.instinctvet.com", "--token", "t"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected SystemExit")


def test_runner_can_parse_accounts_only(monkeypatch, capsys):
    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def iter_accounts(self, params, limit=100):
            yield {"id": "acct-1", "pimsCode": "9758", "primaryContact": {"nameFirst": "N", "nameLast": "D"}}

        def iter_appointments(self, params, limit=100):
            yield from ()

    monkeypatch.setattr(runner, "InstinctPartnerClient", DummyClient)
    code = runner.run(["--base-url", "x", "--token", "t", "--accounts", "--max-records", "1"])
    out = capsys.readouterr().out

    assert code == 0
    assert '"feed": "accounts"' in out
    assert '"watermark_in": null' in out
    assert '"source_hash"' in out


def test_runner_persists_state_file(monkeypatch, tmp_path, capsys):
    state_file = tmp_path / "state.json"

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def iter_accounts(self, params, limit=100):
            yield {"id": "acct-1", "pimsCode": "9758", "primaryContact": {"nameFirst": "N", "nameLast": "D"}}

        def iter_appointments(self, params, limit=100):
            yield from ()

    monkeypatch.setattr(runner, "InstinctPartnerClient", DummyClient)
    code = runner.run(
        [
            "--base-url",
            "x",
            "--token",
            "t",
            "--accounts",
            "--state-file",
            str(state_file),
            "--updated-since",
            "2026-04-20T00:00:00Z",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert state_file.exists()
    assert '"watermark_in": "2026-04-20T00:00:00Z"' in out


def test_runner_writes_export_json(monkeypatch, tmp_path):
    export_file = tmp_path / "export.json"

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def iter_accounts(self, params, limit=100):
            yield {"id": "acct-1", "pimsCode": "9758", "primaryContact": {"nameFirst": "N", "nameLast": "D"}}

        def iter_appointments(self, params, limit=100):
            yield {"id": 42, "status": "canceled", "appointmentTypeId": 7}

        def fetch_appointment_type(self, appointment_type_id):
            return {"id": appointment_type_id, "name": "Checkup"}

    monkeypatch.setattr(runner, "InstinctPartnerClient", DummyClient)
    code = runner.run(
        [
            "--base-url",
            "x",
            "--token",
            "t",
            "--accounts",
            "--appointments",
            "--export-json",
            str(export_file),
            "--fetch-types",
            "--max-records",
            "1",
        ]
    )

    assert code == 0
    payload = export_file.read_text()
    assert '"source_system": "instinct"' in payload
    assert '"conflict_status": "needs_review"' in payload
