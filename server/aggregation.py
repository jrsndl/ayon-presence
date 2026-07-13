"""Pure interval aggregation helpers shared by the scheduler and tests."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ActivityInterval:
    user_name: str
    machine_name: str
    started_at: datetime
    ended_at: datetime


def utc_day_bounds(
    activity_date: date, timezone_name: str
) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    local_start = datetime.combine(activity_date, time.min, tzinfo=zone)
    local_end = datetime.combine(
        activity_date + timedelta(days=1), time.min, tzinfo=zone
    )
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def merge_ranges(
    ranges: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    merged: list[list[datetime]] = []
    for start, end in sorted(ranges, key=lambda item: item[0]):
        if start >= end:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(item[0], item[1]) for item in merged]


def summarize_day(
    activity_date: date,
    timezone_name: str,
    intervals: Iterable[ActivityInterval],
) -> dict[str, dict]:
    period_start, period_end = utc_day_bounds(activity_date, timezone_name)
    by_user: dict[str, list[ActivityInterval]] = defaultdict(list)
    for interval in intervals:
        start = max(interval.started_at, period_start)
        end = min(interval.ended_at, period_end)
        if start < end:
            by_user[interval.user_name].append(
                ActivityInterval(interval.user_name, interval.machine_name, start, end)
            )

    summaries: dict[str, dict] = {}
    for user_name, user_intervals in by_user.items():
        ranges = [(item.started_at, item.ended_at) for item in user_intervals]
        merged = merge_ranges(ranges)
        machine_groups: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
        for item in user_intervals:
            machine_groups[item.machine_name].append((item.started_at, item.ended_at))
        machines = []
        for machine_name, machine_ranges in sorted(machine_groups.items()):
            machine_merged = merge_ranges(machine_ranges)
            machines.append(
                {
                    "name": machine_name,
                    "earliest_activity": machine_merged[0][0].isoformat(),
                    "latest_activity": machine_merged[-1][1].isoformat(),
                    "active_seconds": int(
                        sum(
                            (end - start).total_seconds()
                            for start, end in machine_merged
                        )
                    ),
                }
            )
        summaries[user_name] = {
            "user_name": user_name,
            "activity_date": activity_date,
            "period_start": period_start,
            "period_end": period_end,
            "machines": machines,
            "earliest_activity": merged[0][0],
            "latest_activity": merged[-1][1],
            "total_active_seconds": int(
                sum((end - start).total_seconds() for start, end in merged)
            ),
        }
    return summaries


def last_summarizable_date(
    now: datetime, timezone_name: str, run_time: str
) -> Optional[date]:
    zone = ZoneInfo(timezone_name)
    local_now = now.astimezone(zone)
    hour, minute = (int(value) for value in run_time.split(":", 1))
    if local_now.time() < time(hour, minute):
        return local_now.date() - timedelta(days=2)
    return local_now.date() - timedelta(days=1)
