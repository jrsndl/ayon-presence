from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


EventType = Literal["session_start", "active", "idle", "heartbeat", "session_end"]


class PresenceEvent(BaseModel):
    event_type: EventType
    session_id: str = Field(min_length=1, max_length=128)
    machine_name: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="unknown", max_length=64)
    client_version: str = Field(default="unknown", max_length=64)
    client_time: Optional[datetime] = None
    last_input_at: Optional[datetime] = None
    idle_seconds: int = Field(default=0, ge=0, le=604800)
