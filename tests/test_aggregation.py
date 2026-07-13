from datetime import date, datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

SPEC = spec_from_file_location("presence_aggregation", Path("server/aggregation.py"))
aggregation = module_from_spec(SPEC)
sys.modules[SPEC.name] = aggregation
assert SPEC.loader is not None
SPEC.loader.exec_module(aggregation)
ActivityInterval = aggregation.ActivityInterval


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_overlapping_machines_are_not_double_counted():
    intervals = [
        ActivityInterval(
            "jirka", "WS-01", utc("2026-07-12T08:00:00"), utc("2026-07-12T09:00:00")
        ),
        ActivityInterval(
            "jirka", "LAPTOP", utc("2026-07-12T08:30:00"), utc("2026-07-12T09:30:00")
        ),
    ]
    result = aggregation.summarize_day(date(2026, 7, 12), "UTC", intervals)["jirka"]
    assert result["total_active_seconds"] == 90 * 60
    assert sum(item["active_seconds"] for item in result["machines"]) == 120 * 60


def test_interval_is_clipped_at_calendar_midnight():
    interval = ActivityInterval(
        "jirka", "WS-01", utc("2026-07-12T23:40:00"), utc("2026-07-13T00:25:00")
    )
    first = aggregation.summarize_day(date(2026, 7, 12), "UTC", [interval])["jirka"]
    second = aggregation.summarize_day(date(2026, 7, 13), "UTC", [interval])["jirka"]
    assert first["total_active_seconds"] == 20 * 60
    assert second["total_active_seconds"] == 25 * 60


def test_dst_calendar_day_has_real_timezone_bounds():
    start, end = aggregation.utc_day_bounds(date(2026, 3, 29), "Europe/Prague")
    assert int((end - start).total_seconds()) == 23 * 60 * 60


def test_run_time_does_not_change_calendar_boundary():
    before = aggregation.last_summarizable_date(
        utc("2026-07-13T01:00:00"), "Europe/Prague", "04:00"
    )
    after = aggregation.last_summarizable_date(
        utc("2026-07-13T03:00:00"), "Europe/Prague", "04:00"
    )
    assert before == date(2026, 7, 11)
    assert after == date(2026, 7, 12)
