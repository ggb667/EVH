from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def iter_clients_from_index(accounts: Iterable[dict[str, Any]], start_client_index: int = 0):
    for client_index, account in enumerate(accounts):
        if client_index < start_client_index:
            continue
        yield client_index, account
