from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.instinct_batch_walk import iter_clients_from_index


def test_iter_clients_from_index_preserves_global_order():
    accounts = [{"id": f"client-{i:04d}"} for i in range(4000)]
    baseline = [account["id"] for _, account in iter_clients_from_index(accounts, 0)]
    shard_0 = [account["id"] for _, account in iter_clients_from_index(accounts, 0)][:1000]
    shard_1 = [account["id"] for _, account in iter_clients_from_index(accounts, 1000)][:1000]
    shard_2 = [account["id"] for _, account in iter_clients_from_index(accounts, 2000)][:1000]
    shard_3 = [account["id"] for _, account in iter_clients_from_index(accounts, 3000)][:1000]

    assert shard_0 + shard_1 + shard_2 + shard_3 == baseline
    assert len(set(shard_0 + shard_1 + shard_2 + shard_3)) == 4000
