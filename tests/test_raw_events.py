from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


SPEC = spec_from_file_location("presence_raw_events", Path("server/raw_events.py"))
raw_events = module_from_spec(SPEC)
sys.modules[SPEC.name] = raw_events
assert SPEC.loader is not None
SPEC.loader.exec_module(raw_events)


def row(event_id, payload):
    return {
        "id": event_id,
        "user_name": "alice",
        "received_at": datetime(2026, 7, 15, tzinfo=timezone.utc),
        "payload": payload,
    }


def test_raw_event_page_merges_model_payload_and_returns_cursor():
    result = raw_events.serialize_raw_events_page(
        [
            row(9, {"event_type": "heartbeat", "machine_name": "WS-01"}),
            row(8, '{"event_type":"active","machine_name":"WS-01"}'),
            row(7, {"event_type": "idle", "machine_name": "WS-01"}),
        ],
        page_size=2,
    )

    assert [item["id"] for item in result["events"]] == [9, 8]
    assert result["events"][0]["event_type"] == "heartbeat"
    assert result["events"][1]["event_type"] == "active"
    assert result["next_cursor"] == 8


def test_raw_event_final_page_has_no_cursor():
    result = raw_events.serialize_raw_events_page(
        [row(4, {"event_type": "session_end"})], page_size=2
    )

    assert result["next_cursor"] is None
