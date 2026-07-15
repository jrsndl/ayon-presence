from __future__ import annotations

from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from ayon_server.settings import BaseSettingsModel, SettingsField
from pydantic import root_validator, validator


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


async def secrets_enum_resolver(project_name: str | None = None) -> list[str]:
    """Resolve AYON Secret names without exposing their values."""
    from ayon_server.settings.enum import secrets_enum

    return await secrets_enum(project_name)


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
    day_end_heartbeat_count: int = SettingsField(
        20,
        title="Day End quiet heartbeats",
        description=(
            "Number of heartbeat intervals without newer input after which the "
            "user's last active time is recorded as Day Ended. Later activity "
            "removes Day Ended until the user becomes inactive again."
        ),
        ge=1,
        le=288,
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
    foreground_application_enabled: bool = SettingsField(
        False,
        title="Report foreground application",
        description=(
            "Report the executable name of the foreground Windows application "
            "when it changes. Application names are stored as plaintext."
        ),
    )
    foreground_title_enabled: bool = SettingsField(
        False,
        title="Report foreground application title",
        description=(
            "Report the foreground window or browser-tab title when it changes. "
            "Titles may contain sensitive data and are encrypted before database "
            "storage using the selected AYON Secret."
        ),
    )
    foreground_title_max_length: int = SettingsField(
        32,
        title="Maximum foreground title length",
        description=(
            "Maximum number of title characters collected after control-character "
            "and whitespace cleanup."
        ),
        ge=1,
        le=512,
    )
    foreground_title_secret: str = SettingsField(
        "",
        title="Foreground title passphrase secret",
        description=(
            "AYON Secret containing the passphrase used to derive the title "
            "encryption key. For rotation, create and select a new secret instead "
            "of changing an existing secret value."
        ),
        enum_resolver=secrets_enum_resolver,
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
    timelog_enabled: bool = SettingsField(
        True,
        title="Enable Presence TimeLog",
        description=(
            "Show the artist TimeLog page and enable editable copies of automatic "
            "task records, manual timers, submission, and review workflows."
        ),
    )
    timelog_auto_submit_enabled: bool = SettingsField(
        False,
        title="Automatically submit TimeLogs",
        description=(
            "Submit complete stopped artist TimeLogs automatically after the "
            "configured number of hours without edits."
        ),
    )
    timelog_auto_submit_hours: int = SettingsField(
        24,
        title="TimeLog auto-submit delay (hours)",
        description=(
            "Hours a complete stopped TimeLog remains unedited before automatic "
            "submission when auto-submit is enabled."
        ),
        ge=1,
        le=720,
    )
    timelog_auto_approve_enabled: bool = SettingsField(
        False,
        title="Automatically approve TimeLogs",
        description=(
            "Approve submitted TimeLogs automatically when a manager or admin has "
            "not reviewed them within the configured number of days."
        ),
    )
    timelog_auto_approve_days: int = SettingsField(
        7,
        title="TimeLog auto-approval delay (days)",
        description=(
            "Days a submitted TimeLog waits for manager review before automatic "
            "approval when auto-approval is enabled."
        ),
        ge=1,
        le=365,
    )
    timelog_default_start_hour: str = SettingsField(
        "09:00",
        title="Default artist start hour",
        description=(
            "Start time used when an artist enters a duration into an empty "
            "Timesheet day and no earlier TimeLog determines the next free time."
        ),
        regex=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    timelog_assigned_tasks_only: bool = SettingsField(
        True,
        title="Default to assigned tasks only",
        description=(
            "Default artist preference for limiting the task picker to tasks "
            "assigned to the authenticated user. Artists may change this preference."
        ),
    )
    timelog_bid_attribute: str = SettingsField(
        "bidHours",
        title="Task bid-hours attribute",
        description=(
            "AYON task attribute name containing the studio bid in hours. The "
            "TimeLog views use it for bid comparisons and percentages."
        ),
        min_length=1,
        max_length=128,
    )

    @validator("timezone")
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value}") from exc
        return value

    @root_validator
    def require_foreground_title_secret(cls, values):
        if values.get("foreground_title_enabled") and not values.get(
            "foreground_title_secret"
        ):
            raise ValueError("Foreground title reporting requires an AYON Secret")
        return values


DEFAULT_VALUES: dict[str, Any] = {
    "enabled": True,
    "heartbeat_interval_seconds": 300,
    "day_end_heartbeat_count": 20,
    "active_idle_threshold_seconds": 300,
    "task_tracking_enabled": True,
    "foreground_application_enabled": False,
    "foreground_title_enabled": False,
    "foreground_title_max_length": 32,
    "foreground_title_secret": "",
    "disconnect_timeout_seconds": 600,
    "daily_summary_run_time": "04:00",
    "timezone": "Europe/Prague",
    "raw_event_retention_days": 90,
    "raw_events_debug_enabled": True,
    "projects_default_date_range": "this_week",
    "projects_week_start": "monday",
    "timelog_enabled": True,
    "timelog_auto_submit_enabled": False,
    "timelog_auto_submit_hours": 24,
    "timelog_auto_approve_enabled": False,
    "timelog_auto_approve_days": 7,
    "timelog_default_start_hour": "09:00",
    "timelog_assigned_tasks_only": True,
    "timelog_bid_attribute": "bidHours",
}
