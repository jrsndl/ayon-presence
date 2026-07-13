from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ayon_server.settings import BaseSettingsModel, SettingsField
from pydantic import validator


class PresenceSettings(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")
    heartbeat_interval_seconds: int = SettingsField(
        300, title="Heartbeat interval (seconds)", ge=60, le=3600
    )
    active_idle_threshold_seconds: int = SettingsField(
        300, title="Idle threshold (seconds)", ge=60, le=86400
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
        600, title="Disconnect timeout (seconds)", ge=120, le=86400
    )
    daily_summary_run_time: str = SettingsField(
        "04:00",
        title="Daily summary run time",
        description="Local time to process the previous calendar day (HH:MM).",
        regex=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    timezone: str = SettingsField(
        "Europe/Prague",
        title="Reporting timezone",
        description="IANA timezone used for calendar-day boundaries.",
    )
    raw_event_retention_days: int = SettingsField(
        30, title="Raw event retention (days)", ge=1, le=3650
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
    "raw_event_retention_days": 30,
}
