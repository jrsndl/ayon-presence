from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Type

from ayon_server.addons import BaseServerAddon
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.logging import logger
from fastapi import Query

from .aggregation import last_summarizable_date
from .database import (
    close_stale_sessions,
    consolidate_day,
    create_schema,
    current_users,
    activity_log,
    missing_summary_dates,
    prune_events,
    record_event,
    summaries,
)
from .models import PresenceEvent
from .settings import DEFAULT_VALUES, PresenceSettings


class PresenceAddon(BaseServerAddon):
    settings_model: Type[PresenceSettings] = PresenceSettings
    frontend_scopes = {"dashboard": {}}

    def initialize(self) -> None:
        self._scheduler_task = None
        self.add_endpoint("events", self.post_event, method="POST")
        self.add_endpoint("users", self.get_users, method="GET")
        self.add_endpoint("activity", self.get_activity, method="GET")
        self.add_endpoint("summaries", self.get_summaries, method="GET")

    async def get_default_settings(self) -> PresenceSettings:
        return PresenceSettings(**DEFAULT_VALUES)

    async def setup(self) -> None:
        await create_schema()
        if await self.is_production():
            self._scheduler_task = asyncio.create_task(
                self._scheduler(), name="presence-summary-scheduler"
            )

    async def post_event(self, event: PresenceEvent, user: CurrentUser) -> dict:
        settings = await self.get_studio_settings()
        if not settings.enabled:
            return {"success": False, "reason": "disabled"}
        received_at = await record_event(
            user.name, event, settings.active_idle_threshold_seconds
        )
        return {"success": True, "server_time": received_at}

    async def get_users(self, user: CurrentUser) -> dict:
        del user
        settings = await self.get_studio_settings()
        return {
            "users": await current_users(),
            "disconnect_timeout_seconds": settings.disconnect_timeout_seconds,
            "active_idle_threshold_seconds": settings.active_idle_threshold_seconds,
        }

    async def get_summaries(
        self,
        user: CurrentUser,
        date_from: date = Query(..., alias="from"),
        date_to: date = Query(..., alias="to"),
    ) -> dict:
        if not user.is_manager:
            raise ForbiddenException("Daily activity summaries require manager access")
        if date_to < date_from or (date_to - date_from).days > 366:
            return {"summaries": [], "error": "Invalid date range"}
        return {"summaries": await summaries(date_from, date_to)}

    async def get_activity(
        self,
        user: CurrentUser,
        date_from: date = Query(..., alias="from"),
        date_to: date = Query(..., alias="to"),
        user_name: str | None = None,
    ) -> dict:
        requested_user = user_name or user.name
        if requested_user != user.name and not user.is_manager:
            raise ForbiddenException("Users may only view their own activity log")
        if date_to < date_from or (date_to - date_from).days > 366:
            return {"activity": [], "error": "Invalid date range"}
        settings = await self.get_studio_settings()
        return {
            "activity": await activity_log(
                requested_user, date_from, date_to, settings.timezone
            )
        }

    async def _scheduler(self) -> None:
        while True:
            try:
                settings = await self.get_studio_settings()
                if settings.enabled:
                    await close_stale_sessions(settings.disconnect_timeout_seconds)
                    target = last_summarizable_date(
                        datetime.now(timezone.utc),
                        settings.timezone,
                        settings.daily_summary_run_time,
                    )
                    if target is not None:
                        for missing_date in await missing_summary_dates(
                            target, settings.timezone
                        ):
                            await consolidate_day(missing_date, settings.timezone)
                        await prune_events(settings.raw_event_retention_days)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Presence scheduler failed")
            await asyncio.sleep(60)
