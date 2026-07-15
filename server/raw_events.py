"""Helpers for serializing paginated raw PresenceEvent records."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def serialize_raw_events_page(
    rows: Sequence[Mapping[str, Any]],
    page_size: int,
) -> dict[str, Any]:
    has_more = len(rows) > page_size
    events = []
    for row in rows[:page_size]:
        payload = row["payload"] or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        events.append({
            "id": row["id"],
            "user_name": row["user_name"],
            "received_at": row["received_at"],
            **payload,
        })
    return {
        "events": events,
        "next_cursor": events[-1]["id"] if has_more and events else None,
    }
