from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


def _extract_collection(payload: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


@dataclass(frozen=True)
class PageResult:
    items: list[Any]
    next_cursor: Optional[str]


class InstinctPartnerClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        import requests

        resp = requests.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            params=params or {},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _page(self, path: str, params: dict[str, Any], collection_keys: tuple[str, ...]) -> PageResult:
        data = self._get(path, params)
        items = _extract_collection(data, collection_keys)
        metadata = data.get("metadata") if isinstance(data, dict) else None
        next_cursor = metadata.get("after") if isinstance(metadata, dict) else None
        return PageResult(items=items, next_cursor=next_cursor)

    def iter_accounts(self, params: Optional[dict[str, Any]] = None, *, limit: int = 100):
        after = None
        while True:
            query = {"limit": limit}
            if params:
                query.update(params)
            if after:
                query["pageCursor"] = after
                query["pageDirection"] = "after"
            page = self._page("/v1/accounts", query, ("accounts", "data", "items", "results"))
            for item in page.items:
                yield item
            if not page.next_cursor:
                break
            after = page.next_cursor

    def iter_appointments(self, params: Optional[dict[str, Any]] = None, *, limit: int = 100):
        after = None
        while True:
            query = {"limit": limit}
            if params:
                query.update(params)
            if after:
                query["pageCursor"] = after
                query["pageDirection"] = "after"
            page = self._page("/v1/appointments", query, ("appointments", "data", "items", "results"))
            for item in page.items:
                yield item
            if not page.next_cursor:
                break
            after = page.next_cursor

    def fetch_appointment(self, appointment_id: int) -> Any:
        return self._get(f"/v1/appointments/{appointment_id}")

    def fetch_appointment_type(self, appointment_type_id: int) -> Any:
        return self._get(f"/v1/appointment-types/{appointment_type_id}")

    def update_appointment(self, appointment_id: int, payload: dict[str, Any]) -> Any:
        import requests

        resp = requests.patch(
            f"{self.base_url}/v1/appointments/{appointment_id}",
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def cancel_appointment(self, appointment_id: int) -> Any:
        import requests

        resp = requests.post(
            f"{self.base_url}/v1/appointments/{appointment_id}/cancellation",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
