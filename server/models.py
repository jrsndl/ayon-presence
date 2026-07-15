from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, root_validator, validator


EventType = Literal[
    "session_start",
    "active",
    "idle",
    "heartbeat",
    "session_end",
    "task_start",
    "task_heartbeat",
    "task_stop",
    "foreground_change",
]


class PresenceEvent(BaseModel):
    event_type: EventType
    session_id: str = Field(min_length=1, max_length=128)
    machine_name: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="unknown", max_length=64)
    client_version: str = Field(default="unknown", max_length=64)
    client_time: Optional[datetime] = None
    last_input_at: Optional[datetime] = None
    idle_seconds: int = Field(default=0, ge=0, le=604800)
    project_name: Optional[str] = Field(default=None, max_length=255)
    folder_path: Optional[str] = Field(default=None, max_length=2048)
    task_name: Optional[str] = Field(default=None, max_length=255)
    task_started_at: Optional[datetime] = None
    dcc_name: Optional[str] = Field(default=None, max_length=255)
    dcc_version: Optional[str] = Field(default=None, max_length=128)
    workfile_name: Optional[str] = Field(default=None, max_length=1024)
    foreground_application: Optional[str] = Field(default=None, max_length=255)
    foreground_title: Optional[str] = Field(default=None, max_length=1024)
    tray_timezone: Optional[str] = Field(default=None, max_length=128)

    @validator("foreground_application", "foreground_title")
    def clean_foreground_text(cls, value):
        if value is None:
            return None
        value = " ".join(
            "".join(
                " "
                if ord(character) < 32 or 127 <= ord(character) <= 159
                else character
                for character in value
            ).split()
        )
        return value or None

    @root_validator
    def validate_task_context(cls, values):
        if str(values.get("event_type", "")).startswith("task_"):
            required = ("project_name", "folder_path", "task_name")
            if any(not values.get(key) for key in required):
                raise ValueError("Task events require project, folder and task")
        return values


TimeLogStatus = Literal[
    "not_submitted",
    "submitted",
    "approved",
    "disputed",
    "rejected",
]


class TimeLogCreate(BaseModel):
    project_name: Optional[str] = Field(default=None, max_length=255)
    folder_path: Optional[str] = Field(default=None, max_length=2048)
    folder_name: Optional[str] = Field(default=None, max_length=255)
    folder_label: Optional[str] = Field(default=None, max_length=255)
    folder_id: Optional[str] = Field(default=None, max_length=64)
    task_name: Optional[str] = Field(default=None, max_length=255)
    task_type: Optional[str] = Field(default=None, max_length=255)
    task_status: Optional[str] = Field(default=None, max_length=255)
    task_id: Optional[str] = Field(default=None, max_length=64)
    thumbnail_id: Optional[str] = Field(default=None, max_length=64)
    bid_hours: Optional[float] = Field(default=None, ge=0, le=1000000)
    started_at: datetime
    ended_at: Optional[datetime] = None

    @root_validator
    def validate_range(cls, values):
        started_at = values.get("started_at")
        ended_at = values.get("ended_at")
        if started_at and ended_at and ended_at <= started_at:
            raise ValueError("TimeLog end must be after its start")
        return values


class TimeLogUpdate(BaseModel):
    project_name: Optional[str] = Field(default=None, max_length=255)
    folder_path: Optional[str] = Field(default=None, max_length=2048)
    folder_name: Optional[str] = Field(default=None, max_length=255)
    folder_label: Optional[str] = Field(default=None, max_length=255)
    folder_id: Optional[str] = Field(default=None, max_length=64)
    task_name: Optional[str] = Field(default=None, max_length=255)
    task_type: Optional[str] = Field(default=None, max_length=255)
    task_status: Optional[str] = Field(default=None, max_length=255)
    task_id: Optional[str] = Field(default=None, max_length=64)
    thumbnail_id: Optional[str] = Field(default=None, max_length=64)
    bid_hours: Optional[float] = Field(default=None, ge=0, le=1000000)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class TimeLogSelection(BaseModel):
    ids: list[int] = Field(min_items=1, max_items=500)


class TimeLogReview(TimeLogSelection):
    status: Literal["approved", "disputed", "rejected"]
    note: Optional[str] = Field(default=None, max_length=2048)


class TimeLogPreferences(BaseModel):
    artist_timezone: str = Field(max_length=128)
    start_hour: str = Field(regex=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    assigned_tasks_only: bool = True

    @validator("artist_timezone")
    def validate_artist_timezone(cls, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value}") from exc
        return value
