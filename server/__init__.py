from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Type

from ayon_server.addons import BaseServerAddon
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.logging import logger
from fastapi import Query

from .aggregation import last_summarizable_date
from .database import (
    close_stale_sessions,
    consolidate_day,
    create_schema,
    dashboard_data,
    activity_log,
    missing_summary_dates,
    project_time_summary,
    raw_events_page,
    prune_events,
    record_event,
    summaries,
    task_activity_log,
)
from .models import (
    PresenceEvent,
    TimeLogCreate,
    TimeLogPreferences,
    TimeLogReview,
    TimeLogSelection,
    TimeLogUpdate,
)
from .settings import DEFAULT_VALUES, PresenceSettings
from .timelog import (
    advance_timelog_statuses,
    create_timelog,
    create_timelog_schema,
    delete_timelogs,
    duplicate_timelog,
    get_preferences,
    latest_tray_timezone,
    list_timelogs,
    merge_timelogs,
    review_timelogs,
    running_timelog,
    save_preferences,
    stop_running_timelog,
    submit_timelogs,
    task_totals,
    timelog_users,
    update_timelog,
)
from .title_crypto import TitleEncryptionError


class PresenceAddon(BaseServerAddon):
    settings_model: Type[PresenceSettings] = PresenceSettings
    frontend_scopes = {"settings": {}, "dashboard": {}}

    def initialize(self) -> None:
        self._scheduler_task = None
        self.add_endpoint("events", self.post_event, method="POST")
        self.add_endpoint("users", self.get_users, method="GET")
        self.add_endpoint("activity", self.get_activity, method="GET")
        self.add_endpoint("task-activity", self.get_task_activity, method="GET")
        self.add_endpoint("project-time", self.get_project_time, method="GET")
        self.add_endpoint("raw-events", self.get_raw_events, method="GET")
        self.add_endpoint("summaries", self.get_summaries, method="GET")
        self.add_endpoint("timelog/context", self.get_timelog_context, method="GET")
        self.add_endpoint("timelog/data", self.get_timelog_data, method="GET")
        self.add_endpoint("timelog/entries", self.create_timelog_entry, method="POST")
        self.add_endpoint(
            "timelog/entries/{entry_id}", self.update_timelog_entry, method="PATCH"
        )
        self.add_endpoint("timelog/delete", self.delete_timelog_entries, method="POST")
        self.add_endpoint(
            "timelog/duplicate/{entry_id}", self.duplicate_timelog_entry, method="POST"
        )
        self.add_endpoint("timelog/submit", self.submit_timelog_entries, method="POST")
        self.add_endpoint("timelog/review", self.review_timelog_entries, method="POST")
        self.add_endpoint("timelog/merge", self.merge_timelog_entries, method="POST")
        self.add_endpoint(
            "timelog/preferences", self.update_timelog_preferences, method="PUT"
        )
        self.add_endpoint("timelog/timer/stop", self.stop_timelog_timer, method="POST")

    async def get_default_settings(self) -> PresenceSettings:
        return PresenceSettings(**DEFAULT_VALUES)

    async def setup(self) -> None:
        await create_schema()
        await create_timelog_schema()
        if await self.is_production():
            self._scheduler_task = asyncio.create_task(
                self._scheduler(), name="presence-summary-scheduler"
            )

    async def post_event(self, event: PresenceEvent, user: CurrentUser) -> dict:
        settings = await self.get_studio_settings()
        if not settings.enabled:
            return {"success": False, "reason": "disabled"}
        if event.event_type.startswith("task_") and not settings.task_tracking_enabled:
            return {"success": False, "reason": "task_tracking_disabled"}
        if event.event_type == "foreground_change":
            if not (
                settings.foreground_application_enabled
                or settings.foreground_title_enabled
            ):
                return {"success": False, "reason": "foreground_reporting_disabled"}
            event = event.copy(
                update={
                    "foreground_application": (
                        event.foreground_application
                        if settings.foreground_application_enabled
                        else None
                    ),
                    "foreground_title": (
                        event.foreground_title[: settings.foreground_title_max_length]
                        if settings.foreground_title_enabled and event.foreground_title
                        else None
                    ),
                }
            )
        else:
            event = event.copy(
                update={
                    "foreground_application": None,
                    "foreground_title": None,
                }
            )
        title_key_name = (
            settings.foreground_title_secret
            if settings.foreground_title_enabled
            else None
        )
        title_stored = True
        try:
            received_at = await record_event(
                user.name,
                event,
                settings.active_idle_threshold_seconds,
                settings.timezone,
                settings.heartbeat_interval_seconds,
                settings.day_end_heartbeat_count,
                title_key_name,
            )
        except TitleEncryptionError:
            logger.warning(
                "Presence could not encrypt a foreground title; storing the "
                "application change without its title"
            )
            title_stored = False
            event = event.copy(update={"foreground_title": None})
            received_at = await record_event(
                user.name,
                event,
                settings.active_idle_threshold_seconds,
                settings.timezone,
                settings.heartbeat_interval_seconds,
                settings.day_end_heartbeat_count,
            )
        return {
            "success": True,
            "server_time": received_at,
            "foreground_title_stored": title_stored,
        }

    async def get_users(self, user: CurrentUser) -> dict:
        del user
        settings = await self.get_studio_settings()
        result = await dashboard_data(
            settings.timezone, settings.disconnect_timeout_seconds
        )
        result.update(
            {
                "disconnect_timeout_seconds": settings.disconnect_timeout_seconds,
                "active_idle_threshold_seconds": settings.active_idle_threshold_seconds,
                "projects_default_date_range": settings.projects_default_date_range,
                "projects_week_start": settings.projects_week_start,
                "raw_events_debug_enabled": settings.raw_events_debug_enabled,
                "foreground_application_enabled": (
                    settings.foreground_application_enabled
                ),
                "foreground_title_enabled": settings.foreground_title_enabled,
            }
        )
        return result

    async def get_project_time(
        self,
        user: CurrentUser,
        date_from: date = Query(..., alias="from"),
        date_to: date = Query(..., alias="to"),
    ) -> dict:
        if not user.is_manager:
            raise ForbiddenException("Project time reports require manager access")
        if date_to < date_from or (date_to - date_from).days > 366:
            return {"projects": [], "error": "Invalid date range"}
        settings = await self.get_studio_settings()
        return {
            "projects": await project_time_summary(
                date_from, date_to, settings.timezone
            )
        }

    async def get_raw_events(
        self,
        user: CurrentUser,
        page_size: int = Query(50, ge=10, le=200),
        before_id: int | None = Query(None, ge=1),
    ) -> dict:
        if not user.is_manager:
            raise ForbiddenException("Raw event inspection requires manager access")
        settings = await self.get_studio_settings()
        if not settings.raw_events_debug_enabled:
            raise ForbiddenException("Raw event inspection is disabled")
        return await raw_events_page(page_size, before_id)

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

    async def get_task_activity(
        self,
        user: CurrentUser,
        date_from: date = Query(..., alias="from"),
        date_to: date = Query(..., alias="to"),
        user_name: str | None = None,
    ) -> dict:
        requested_user = user_name or user.name
        if requested_user != user.name and not user.is_manager:
            raise ForbiddenException("Users may only view their own task activity")
        if date_to < date_from or (date_to - date_from).days > 366:
            return {"task_activity": [], "error": "Invalid date range"}
        settings = await self.get_studio_settings()
        return {
            "task_activity": await task_activity_log(
                requested_user, date_from, date_to, settings.timezone
            )
        }

    @staticmethod
    def _requested_user(user: CurrentUser, user_name: str | None) -> str:
        requested_user = user_name or user.name
        if requested_user != user.name and not user.is_manager:
            raise ForbiddenException("Users may only view their own TimeLogs")
        return requested_user

    @staticmethod
    def _validate_timelog_range(date_from: date, date_to: date) -> None:
        if date_to < date_from or (date_to - date_from).days > 366:
            raise BadRequestException("Invalid TimeLog date range")

    async def get_timelog_context(self, user: CurrentUser) -> dict:
        settings = await self.get_studio_settings()
        if not settings.timelog_enabled:
            raise ForbiddenException("Presence TimeLog is disabled")
        preferences = await get_preferences(
            user.name,
            settings.timezone,
            settings.timelog_default_start_hour,
            settings.timelog_assigned_tasks_only,
        )
        return {
            "user_name": user.name,
            "is_manager": user.is_manager,
            "studio_timezone": settings.timezone,
            "tray_timezone": await latest_tray_timezone(user.name),
            "preferences": preferences,
            "users": await timelog_users() if user.is_manager else [user.name],
            "week_start": settings.projects_week_start,
            "bid_attribute": settings.timelog_bid_attribute,
            "auto_submit_enabled": settings.timelog_auto_submit_enabled,
            "auto_submit_hours": settings.timelog_auto_submit_hours,
            "auto_approve_enabled": settings.timelog_auto_approve_enabled,
            "auto_approve_days": settings.timelog_auto_approve_days,
        }

    async def get_timelog_data(
        self,
        user: CurrentUser,
        date_from: date = Query(..., alias="from"),
        date_to: date = Query(..., alias="to"),
        user_name: str | None = None,
    ) -> dict:
        requested_user = self._requested_user(user, user_name)
        self._validate_timelog_range(date_from, date_to)
        settings = await self.get_studio_settings()
        if not settings.timelog_enabled:
            raise ForbiddenException("Presence TimeLog is disabled")
        return {
            "user_name": requested_user,
            "timelogs": await list_timelogs(
                requested_user, date_from, date_to, settings.timezone
            ),
            "activity": await activity_log(
                requested_user, date_from, date_to, settings.timezone
            ),
            "auto_logs": await task_activity_log(
                requested_user, date_from, date_to, settings.timezone
            ),
            "running": await running_timelog(requested_user),
            "tray_timezone": await latest_tray_timezone(requested_user),
            "task_totals": await task_totals(),
        }

    async def create_timelog_entry(
        self, payload: TimeLogCreate, user: CurrentUser
    ) -> dict:
        settings = await self.get_studio_settings()
        if not settings.timelog_enabled:
            raise ForbiddenException("Presence TimeLog is disabled")
        return {"timelog": await create_timelog(user.name, payload)}

    async def update_timelog_entry(
        self, entry_id: int, payload: TimeLogUpdate, user: CurrentUser
    ) -> dict:
        return {"timelog": await update_timelog(entry_id, user.name, payload)}

    async def delete_timelog_entries(
        self, payload: TimeLogSelection, user: CurrentUser
    ) -> dict:
        return {"deleted": await delete_timelogs(user.name, payload.ids)}

    async def duplicate_timelog_entry(self, entry_id: int, user: CurrentUser) -> dict:
        return {"timelog": await duplicate_timelog(entry_id, user.name)}

    async def submit_timelog_entries(
        self, payload: TimeLogSelection, user: CurrentUser
    ) -> dict:
        return {"submitted": await submit_timelogs(user.name, payload.ids)}

    async def review_timelog_entries(
        self, payload: TimeLogReview, user: CurrentUser
    ) -> dict:
        if not user.is_manager:
            raise ForbiddenException("TimeLog review requires manager access")
        return {"reviewed": await review_timelogs(user.name, payload)}

    async def merge_timelog_entries(
        self, payload: TimeLogSelection, user: CurrentUser
    ) -> dict:
        return {"timelog": await merge_timelogs(user.name, payload.ids)}

    async def update_timelog_preferences(
        self, payload: TimeLogPreferences, user: CurrentUser
    ) -> dict:
        return {"preferences": await save_preferences(user.name, payload)}

    async def stop_timelog_timer(self, user: CurrentUser) -> dict:
        return {"timelog": await stop_running_timelog(user.name)}

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
                    await advance_timelog_statuses(
                        settings.timelog_auto_submit_enabled,
                        settings.timelog_auto_submit_hours,
                        settings.timelog_auto_approve_enabled,
                        settings.timelog_auto_approve_days,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Presence scheduler failed")
            await asyncio.sleep(60)
