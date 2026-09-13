from __future__ import annotations

import json

from scripts import instinct_batch_flow as flow


class DummySQS:
    def __init__(self):
        self.sent = []

    def send_message(self, QueueUrl, MessageBody):
        self.sent.append((QueueUrl, MessageBody))
        return {"MessageId": f"m{len(self.sent)}"}


def test_parse_message_defaults():
    msg = flow.parse_message({})
    assert msg.stage == ""
    assert msg.patient_limit is None
    assert msg.document_limit is None


def test_enqueue_work(monkeypatch):
    dummy = DummySQS()
    monkeypatch.setenv("EVH_IMPORT_QUEUE_URL", "https://sqs.example/queue")
    monkeypatch.setattr(flow, "boto3", type("B", (), {"client": lambda self, name: dummy})())
    ids = flow.enqueue_work([flow.BatchMessage(stage="clients"), flow.BatchMessage(stage="patients")])
    assert ids == ["m1", "m2"]
    assert len(dummy.sent) == 2


def test_worker_handler_returns_partial_failures(monkeypatch):
    class DummyConn:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False

    class DummyClient:
        pass

    monkeypatch.setattr(flow, "connect_db", lambda: DummyConn())
    monkeypatch.setattr(flow, "InstinctApiSyncClient", lambda *args, **kwargs: DummyClient())
    monkeypatch.setattr(flow, "_process_message", lambda client, conn, msg: {"stage": msg.stage})
    event = {"Records": [{"messageId": "1", "body": json.dumps({"stage": "clients"})}]}
    result = flow.worker_lambda_handler(event)
    assert result["batchItemFailures"] == []
    assert result["results"][0]["status"] == "ok"
