"""Process-wide HTTP session for connection reuse."""

from __future__ import annotations

import requests


SESSION = requests.Session()


def get_session() -> requests.Session:
    return SESSION
