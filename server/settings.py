from __future__ import annotations

from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from ayon_server.settings import BaseSettingsModel, SettingsField
from pydantic import validator


def timezone_enum_resolver() -> list[str]:
    """Return installed IANA zones with the studio default first."""
    values = sorted(available_timezones())
    default = "Europe/Prague"
    if default in values:
        values.remove(default)
        values.insert(0, default)
    return values


def week_start_enum_resolver() -> list[dict[str, str]]:
    return [
        {"value": "monday", "label": "Monday"},
        {"value": "sunday", "label": "Sunday"},
    ]


class PresenceSettings(BaseSettingsModel):
    enabled: bool = SettingsField(
        True,
        title="Enabled",
        description=(
            "Enable Presence event ingestion, activity tracking, and reporting."
        ),
    )
    heartbeat_interval_seconds: int = SettingsField(
        300,
        title="Heartbeat interval (seconds)",
        description=(
            "How often tray clients report unchanged activity state. Shorter "
            "intervals update Presence sooner but create more server requests."
        ),
        ge=60,
        le=3600,
    )
    active_idle_threshold_seconds: int = SettingsField(
        300,
        title="Idle threshold (seconds)",
        description=(
            "Seconds without keyboard or mouse input before a tray session and "
            "its current task are considered idle."
        ),
        ge=60,
        le=86400,
    )
    task_tracking_enabled: bool = SettingsField(
        True,
        title="Track active time per AYON task",
        description=(
            "Record active intervals for the native AYON project/folder/task "
            "context selected by application launches and host task changes."
        ),
    )
    disconnect_timeout_seconds: int = SettingsField(
        600,
        title="Disconnect timeout (seconds)",
        description=(
            "How long the server waits without a heartbeat before closing a "
            "stale tray session and its open task interval."
        ),
        ge=120,
        le=86400,
    )
    daily_summary_run_time: str = SettingsField(
        "04:00",
        title="Daily summary run time",
        description=(
            "Local time, in the reporting timezone, when Presence processes "
            "the previous calendar day (HH:MM)."
        ),
        regex=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    timezone: str = SettingsField(
        "Europe/Prague",
        title="Reporting timezone",
        description=(
            "IANA timezone used for project date filters, calendar-day "
            "boundaries, and daily activity summaries."
        ),
        enum_resolver=timezone_enum_resolver,
    )
    raw_event_retention_days: int = SettingsField(
        90,
        title="Raw event retention (days)",
        description=(
            "Days to keep raw tray events in presence_events. Activity and "
            "task intervals and daily summaries are not removed by this limit."
        ),
        ge=1,
        le=3650,
    )
    raw_events_debug_enabled: bool = SettingsField(
        True,
        title="Enable raw events debug view",
        description=(
            "Show the manager-only Events debug tab and allow its paginated raw "
            "event API. Disable this when raw event inspection is not needed."
        ),
    )
    projects_default_date_range: Literal[
        "today",
        "yesterday",
        "this_week",
        "last_week",
        "this_month",
        "last_month",
        "this_year",
        "last_year",
        "custom",
    ] = SettingsField(
        "this_week",
        title="Projects default date range",
        description=(
            "Date-range preset selected when the Presence Projects tab is first "
            "opened. Custom starts with today's date until changed by the user."
        ),
    )
    projects_week_start: Literal["monday", "sunday"] = SettingsField(
        "monday",
        title="Projects calendar week start",
        description=(
            "First day of the week used by the Projects calendar and week presets."
        ),
        enum_resolver=week_start_enum_resolver,
    )

    @validator("timezone")
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value}") from exc
        return value


DEFAULT_VALUES: dict[str, Any] = {
    "enabled": True,
    "heartbeat_interval_seconds": 300,
    "active_idle_threshold_seconds": 300,
    "task_tracking_enabled": True,
    "disconnect_timeout_seconds": 600,
    "daily_summary_run_time": "04:00",
    "timezone": "Europe/Prague",
    "raw_event_retention_days": 90,
    "raw_events_debug_enabled": True,
    "projects_default_date_range": "this_week",
    "projects_week_start": "monday",
}
