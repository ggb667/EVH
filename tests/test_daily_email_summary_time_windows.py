from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.gmail.daily_email_summary import (
    build_query_between_checkpoint_and_24h_ago,
    build_query_last_24h,
    build_query_since_checkpoint,
)


def test_query_since_checkpoint_uses_checkpoint_date() -> None:
    checkpoint = datetime(2026, 7, 24, 11, 30, 11, 767000, tzinfo=timezone.utc)

    assert build_query_since_checkpoint(checkpoint) == "after:2026/07/24"


def test_query_last_24h_uses_only_last_day() -> None:
    assert build_query_last_24h() == "newer_than:1d"


def test_query_between_checkpoint_and_24h_ago_uses_checkpoint_and_older_than() -> None:
    checkpoint = datetime(2026, 7, 24, 11, 30, 11, 767000, tzinfo=timezone.utc)

    assert build_query_between_checkpoint_and_24h_ago(checkpoint) == "after:2026/07/24 older_than:1d"


def test_query_between_checkpoint_and_24h_ago_falls_back_when_checkpoint_missing() -> None:
    assert build_query_between_checkpoint_and_24h_ago(None) == "newer_than:1d"
