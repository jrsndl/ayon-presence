from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, root_validator


EventType = Literal[
    "session_start",
    "active",
    "idle",
    "heartbeat",
    "session_end",
    "task_start",
    "task_heartbeat",
    "task_stop",
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

    @root_validator
    def validate_task_context(cls, values):
        if str(values.get("event_type", "")).startswith("task_"):
            required = ("project_name", "folder_path", "task_name")
            if any(not values.get(key) for key in required):
                raise ValueError("Task events require project, folder and task")
        return values
