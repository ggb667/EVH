from __future__ import annotations

from typing import Any

from scripts.instinct_batch_flow import worker_lambda_handler


def lambda_handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    return worker_lambda_handler(event, context)
