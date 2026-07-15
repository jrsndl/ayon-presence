from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres

from .aggregation import utc_day_bounds
from .models import (
    TimeLogCreate,
    TimeLogPreferences,
    TimeLogReview,
    TimeLogUpdate,
)


TIMELOG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS public.presence_timelog_preferences (
    user_name TEXT PRIMARY KEY,
    artist_timezone TEXT NOT NULL,
    start_hour TEXT NOT NULL DEFAULT '09:00',
    assigned_tasks_only BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS public.presence_timelogs (
    id BIGSERIAL PRIMARY KEY,
    user_name TEXT NOT NULL,
    source_task_interval_id BIGINT UNIQUE,
    source_synced BOOLEAN NOT NULL DEFAULT FALSE,
    project_name TEXT,
    folder_path TEXT,
    folder_name TEXT,
    folder_label TEXT,
    folder_id TEXT,
    task_name TEXT,
    task_type TEXT,
    task_status TEXT,
    task_id TEXT,
    thumbnail_id TEXT,
    bid_hours DOUBLE PRECISION,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'not_submitted',
    submitted_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    reviewed_by TEXT,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    CHECK (ended_at IS NULL OR ended_at > started_at),
    CHECK (status IN (
        'not_submitted', 'submitted', 'approved', 'disputed', 'rejected'
    ))
);
CREATE INDEX IF NOT EXISTS presence_timelogs_user_range_idx
    ON public.presence_timelogs (user_name, started_at, ended_at)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS presence_timelogs_status_idx
    ON public.presence_timelogs (status, submitted_at)
    WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS presence_one_running_timelog_per_user_idx
    ON public.presence_timelogs (user_name)
    WHERE ended_at IS NULL AND deleted_at IS NULL;
"""


EDITABLE_STATUSES = {"not_submitted", "disputed"}
SUBMITTABLE_STATUSES = {"not_submitted", "disputed"}


async def create_timelog_schema() -> None:
    await Postgres.execute(TIMELOG_SCHEMA_SQL)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _validate_range(started_at: datetime, ended_at: datetime | None) -> None:
    if ended_at is not None and _aware(ended_at) <= _aware(started_at):
        raise BadRequestException("TimeLog end must be after its start")


def _serialize(row: Any) -> dict[str, Any]:
    result = dict(row)
    effective_end = result.get("ended_at") or datetime.now(timezone.utc)
    result["total_seconds"] = max(
        0, int((_aware(effective_end) - _aware(result["started_at"])).total_seconds())
    )
    result["is_running"] = result.get("ended_at") is None
    result["is_editable"] = result.get("status") in EDITABLE_STATUSES
    return result


async def get_preferences(
    user_name: str,
    studio_timezone: str,
    default_start_hour: str,
    default_assigned_tasks_only: bool,
) -> dict[str, Any]:
    row = await Postgres.fetchrow(
        """
        SELECT artist_timezone, start_hour, assigned_tasks_only
        FROM public.presence_timelog_preferences
        WHERE user_name = $1
        """,
        user_name,
    )
    if row:
        return dict(row)
    return {
        "artist_timezone": studio_timezone,
        "start_hour": default_start_hour,
        "assigned_tasks_only": default_assigned_tasks_only,
    }


async def save_preferences(
    user_name: str, preferences: TimeLogPreferences
) -> dict[str, Any]:
    row = await Postgres.fetchrow(
        """
        INSERT INTO public.presence_timelog_preferences (
            user_name, artist_timezone, start_hour, assigned_tasks_only, updated_at
        ) VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (user_name) DO UPDATE SET
            artist_timezone = EXCLUDED.artist_timezone,
            start_hour = EXCLUDED.start_hour,
            assigned_tasks_only = EXCLUDED.assigned_tasks_only,
            updated_at = EXCLUDED.updated_at
        RETURNING artist_timezone, start_hour, assigned_tasks_only
        """,
        user_name,
        preferences.artist_timezone,
        preferences.start_hour,
        preferences.assigned_tasks_only,
    )
    return dict(row)


async def timelog_users() -> list[str]:
    rows = await Postgres.fetch(
        """
        SELECT DISTINCT user_name
        FROM (
            SELECT user_name FROM public.presence_sessions
            UNION
            SELECT user_name FROM public.presence_timelogs
        ) users
        ORDER BY user_name
        """
    )
    return [str(row["user_name"]) for row in rows]


async def latest_tray_timezone(user_name: str) -> str | None:
    row = await Postgres.fetchrow(
        """
        SELECT tray_timezone
        FROM public.presence_sessions
        WHERE user_name = $1 AND tray_timezone IS NOT NULL
        ORDER BY last_heartbeat_at DESC
        LIMIT 1
        """,
        user_name,
    )
    return str(row["tray_timezone"]) if row else None


async def task_totals() -> list[dict[str, Any]]:
    """Return studio-wide logged time totals without exposing other users' rows."""
    rows = await Postgres.fetch(
        """
        SELECT project_name, folder_path, task_name,
            COUNT(DISTINCT user_name)::integer AS user_count,
            GREATEST(0, FLOOR(SUM(EXTRACT(EPOCH FROM (
                COALESCE(ended_at, NOW()) - started_at
            ))))::integer) AS total_seconds
        FROM public.presence_timelogs
        WHERE deleted_at IS NULL
            AND status <> 'rejected'
            AND project_name IS NOT NULL AND folder_path IS NOT NULL
            AND task_name IS NOT NULL
        GROUP BY project_name, folder_path, task_name
        """
    )
    return [dict(row) for row in rows]


async def sync_task_copies(
    user_name: str,
    date_from: date,
    date_to: date,
    timezone_name: str,
) -> None:
    """Create/update connected copies without ever changing source intervals."""
    period_start, _ = utc_day_bounds(date_from, timezone_name)
    _, period_end = utc_day_bounds(date_to, timezone_name)
    await Postgres.execute(
        """
        INSERT INTO public.presence_timelogs (
            user_name, source_task_interval_id, source_synced,
            project_name, folder_path, folder_name, task_name,
            started_at, ended_at, created_at, updated_at
        )
        SELECT intervals.user_name, intervals.id, TRUE,
            intervals.project_name, intervals.folder_path,
            NULLIF(regexp_replace(intervals.folder_path, '^.*/', ''), ''),
            intervals.task_name, intervals.started_at, intervals.ended_at,
            intervals.started_at, COALESCE(intervals.ended_at, intervals.last_seen_at)
        FROM public.presence_task_intervals intervals
        WHERE intervals.user_name = $1
            AND intervals.started_at < $3
            AND COALESCE(intervals.ended_at, intervals.last_seen_at) > $2
            AND (
                intervals.ended_at IS NOT NULL
                OR NOT EXISTS (
                    SELECT 1 FROM public.presence_timelogs running
                    WHERE running.user_name = $1 AND running.ended_at IS NULL
                        AND running.deleted_at IS NULL
                        AND running.source_task_interval_id IS DISTINCT FROM intervals.id
                )
            )
        ON CONFLICT (source_task_interval_id) DO UPDATE SET
            project_name = EXCLUDED.project_name,
            folder_path = EXCLUDED.folder_path,
            folder_name = EXCLUDED.folder_name,
            task_name = EXCLUDED.task_name,
            started_at = EXCLUDED.started_at,
            ended_at = EXCLUDED.ended_at,
            updated_at = EXCLUDED.updated_at
        WHERE presence_timelogs.source_synced = TRUE
            AND presence_timelogs.status = 'not_submitted'
            AND presence_timelogs.deleted_at IS NULL
        """,
        user_name,
        period_start,
        period_end,
    )


async def list_timelogs(
    user_name: str,
    date_from: date,
    date_to: date,
    timezone_name: str,
) -> list[dict[str, Any]]:
    await sync_task_copies(user_name, date_from, date_to, timezone_name)
    period_start, _ = utc_day_bounds(date_from, timezone_name)
    _, period_end = utc_day_bounds(date_to, timezone_name)
    rows = await Postgres.fetch(
        """
        SELECT * FROM public.presence_timelogs
        WHERE user_name = $1
            AND deleted_at IS NULL
            AND started_at < $3
            AND COALESCE(ended_at, NOW()) > $2
        ORDER BY started_at DESC, id DESC
        """,
        user_name,
        period_start,
        period_end,
    )
    return [_serialize(row) for row in rows]


async def running_timelog(user_name: str) -> dict[str, Any] | None:
    row = await Postgres.fetchrow(
        """
        SELECT * FROM public.presence_timelogs
        WHERE user_name = $1 AND ended_at IS NULL AND deleted_at IS NULL
        ORDER BY started_at DESC LIMIT 1
        """,
        user_name,
    )
    return _serialize(row) if row else None


async def create_timelog(user_name: str, payload: TimeLogCreate) -> dict[str, Any]:
    _validate_range(payload.started_at, payload.ended_at)
    if payload.ended_at is None:
        running = await Postgres.fetchrow(
            """
            SELECT id FROM public.presence_timelogs
            WHERE user_name = $1 AND ended_at IS NULL AND deleted_at IS NULL
            LIMIT 1
            """,
            user_name,
        )
        if running:
            raise BadRequestException(
                "Stop the current TimeLog before starting another"
            )
    row = await Postgres.fetchrow(
        """
        INSERT INTO public.presence_timelogs (
            user_name, source_synced, project_name, folder_path, folder_name,
            folder_label, folder_id, task_name, task_type, task_status, task_id,
            thumbnail_id, bid_hours, started_at, ended_at, created_at, updated_at
        ) VALUES (
            $1, FALSE, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, NOW(), NOW()
        ) RETURNING *
        """,
        user_name,
        payload.project_name,
        payload.folder_path,
        payload.folder_name,
        payload.folder_label,
        payload.folder_id,
        payload.task_name,
        payload.task_type,
        payload.task_status,
        payload.task_id,
        payload.thumbnail_id,
        payload.bid_hours,
        _aware(payload.started_at),
        _aware(payload.ended_at) if payload.ended_at else None,
    )
    return _serialize(row)


async def _editable_row(entry_id: int, user_name: str) -> dict[str, Any]:
    row = await Postgres.fetchrow(
        """
        SELECT * FROM public.presence_timelogs
        WHERE id = $1 AND user_name = $2 AND deleted_at IS NULL
        FOR UPDATE
        """,
        entry_id,
        user_name,
    )
    if not row:
        raise BadRequestException("TimeLog was not found")
    result = dict(row)
    if result["status"] not in EDITABLE_STATUSES:
        raise BadRequestException(f"{result['status']} TimeLogs cannot be edited")
    return result


async def update_timelog(
    entry_id: int, user_name: str, payload: TimeLogUpdate
) -> dict[str, Any]:
    async with Postgres.transaction():
        current = await _editable_row(entry_id, user_name)
        values = payload.dict(exclude_unset=True)
        current.update(values)
        _validate_range(current["started_at"], current.get("ended_at"))
        row = await Postgres.fetchrow(
            """
            UPDATE public.presence_timelogs SET
                project_name = $3, folder_path = $4, folder_name = $5,
                folder_label = $6, folder_id = $7, task_name = $8,
                task_type = $9, task_status = $10, task_id = $11,
                thumbnail_id = $12, bid_hours = $13, started_at = $14,
                ended_at = $15, source_synced = FALSE, updated_at = NOW()
            WHERE id = $1 AND user_name = $2
            RETURNING *
            """,
            entry_id,
            user_name,
            current.get("project_name"),
            current.get("folder_path"),
            current.get("folder_name"),
            current.get("folder_label"),
            current.get("folder_id"),
            current.get("task_name"),
            current.get("task_type"),
            current.get("task_status"),
            current.get("task_id"),
            current.get("thumbnail_id"),
            current.get("bid_hours"),
            _aware(current["started_at"]),
            _aware(current["ended_at"]) if current.get("ended_at") else None,
        )
    return _serialize(row)


async def delete_timelogs(user_name: str, ids: list[int]) -> int:
    async with Postgres.transaction():
        rows = await Postgres.fetch(
            """
            UPDATE public.presence_timelogs
            SET deleted_at = NOW(), updated_at = NOW(), source_synced = FALSE
            WHERE user_name = $1 AND id = ANY($2::bigint[])
                AND deleted_at IS NULL
                AND status IN ('not_submitted', 'disputed')
            RETURNING id
            """,
            user_name,
            ids,
        )
        if len(rows) != len(set(ids)):
            raise BadRequestException("Only editable TimeLogs may be deleted")
    return len(rows)


async def duplicate_timelog(entry_id: int, user_name: str) -> dict[str, Any]:
    row = await Postgres.fetchrow(
        """
        INSERT INTO public.presence_timelogs (
            user_name, source_synced, project_name, folder_path, folder_name,
            folder_label, folder_id, task_name, task_type, task_status, task_id,
            thumbnail_id, bid_hours, started_at, ended_at, created_at, updated_at
        ) SELECT user_name, FALSE, project_name, folder_path, folder_name,
            folder_label, folder_id, task_name, task_type, task_status, task_id,
            thumbnail_id, bid_hours, started_at, ended_at, NOW(), NOW()
        FROM public.presence_timelogs
        WHERE id = $1 AND user_name = $2 AND deleted_at IS NULL
            AND ended_at IS NOT NULL
        RETURNING *
        """,
        entry_id,
        user_name,
    )
    if not row:
        raise BadRequestException("Only stopped TimeLogs may be duplicated")
    return _serialize(row)


async def submit_timelogs(user_name: str, ids: list[int]) -> int:
    async with Postgres.transaction():
        rows = await Postgres.fetch(
            """
            UPDATE public.presence_timelogs
            SET status = 'submitted', submitted_at = NOW(), reviewed_at = NULL,
                reviewed_by = NULL, review_note = NULL, source_synced = FALSE,
                updated_at = NOW()
            WHERE user_name = $1 AND id = ANY($2::bigint[])
                AND deleted_at IS NULL
                AND status IN ('not_submitted', 'disputed')
                AND ended_at IS NOT NULL
                AND NULLIF(BTRIM(project_name), '') IS NOT NULL
                AND NULLIF(BTRIM(folder_path), '') IS NOT NULL
                AND NULLIF(BTRIM(task_name), '') IS NOT NULL
            RETURNING id
            """,
            user_name,
            ids,
        )
        if len(rows) != len(set(ids)):
            raise BadRequestException(
                "TimeLogs must be editable, stopped, and assigned to a task before submission"
            )
    return len(rows)


async def review_timelogs(reviewer: str, payload: TimeLogReview) -> int:
    async with Postgres.transaction():
        rows = await Postgres.fetch(
            """
            UPDATE public.presence_timelogs
            SET status = $2, reviewed_at = NOW(), reviewed_by = $3,
                review_note = $4, updated_at = NOW()
            WHERE id = ANY($1::bigint[]) AND deleted_at IS NULL
                AND status = 'submitted'
            RETURNING id
            """,
            payload.ids,
            payload.status,
            reviewer,
            payload.note,
        )
        if len(rows) != len(set(payload.ids)):
            raise BadRequestException("Only submitted TimeLogs may be reviewed")
    return len(rows)


async def merge_timelogs(user_name: str, ids: list[int]) -> dict[str, Any]:
    if len(set(ids)) < 2:
        raise BadRequestException("Select at least two TimeLogs to merge")
    async with Postgres.transaction():
        rows = await Postgres.fetch(
            """
            SELECT * FROM public.presence_timelogs
            WHERE user_name = $1 AND id = ANY($2::bigint[])
                AND deleted_at IS NULL
                AND status IN ('not_submitted', 'disputed')
            ORDER BY started_at, id
            FOR UPDATE
            """,
            user_name,
            ids,
        )
        if len(rows) != len(set(ids)):
            raise BadRequestException("Only editable TimeLogs may be merged")
        source = dict(rows[0])
        ended_values = [row["ended_at"] for row in rows]
        if any(value is None for value in ended_values):
            raise BadRequestException("Stop running TimeLogs before merging")
        merged_end = max(ended_values)
        row = await Postgres.fetchrow(
            """
            UPDATE public.presence_timelogs
            SET ended_at = $3, source_synced = FALSE, updated_at = NOW()
            WHERE id = $1 AND user_name = $2
            RETURNING *
            """,
            source["id"],
            user_name,
            merged_end,
        )
        other_ids = [item["id"] for item in rows[1:]]
        await Postgres.execute(
            """
            UPDATE public.presence_timelogs
            SET deleted_at = NOW(), source_synced = FALSE, updated_at = NOW()
            WHERE user_name = $1 AND id = ANY($2::bigint[])
            """,
            user_name,
            other_ids,
        )
    return _serialize(row)


async def stop_running_timelog(user_name: str) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    async with Postgres.transaction():
        row = await Postgres.fetchrow(
            """
            UPDATE public.presence_timelogs
            SET ended_at = GREATEST(started_at + INTERVAL '1 second', $2),
                source_synced = FALSE, updated_at = NOW()
            WHERE user_name = $1 AND ended_at IS NULL AND deleted_at IS NULL
            RETURNING *
            """,
            user_name,
            now,
        )
        if row:
            await Postgres.execute(
                """
                UPDATE public.presence_task_intervals
                SET ended_at = GREATEST(started_at, $2), status = 'manual_stop',
                    total_seconds = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (
                        GREATEST(started_at, $2) - started_at
                    )))::integer), last_seen_at = GREATEST(last_seen_at, $2)
                WHERE user_name = $1 AND ended_at IS NULL
                """,
                user_name,
                now,
            )
    return _serialize(row) if row else None


async def advance_timelog_statuses(
    auto_submit_enabled: bool,
    auto_submit_hours: int,
    auto_approve_enabled: bool,
    auto_approve_days: int,
) -> dict[str, int]:
    submitted = []
    approved = []
    if auto_submit_enabled:
        submitted = await Postgres.fetch(
            """
            UPDATE public.presence_timelogs
            SET status = 'submitted', submitted_at = NOW(), updated_at = NOW(),
                source_synced = FALSE
            WHERE status IN ('not_submitted', 'disputed') AND deleted_at IS NULL
                AND ended_at IS NOT NULL
                AND NULLIF(BTRIM(project_name), '') IS NOT NULL
                AND NULLIF(BTRIM(folder_path), '') IS NOT NULL
                AND NULLIF(BTRIM(task_name), '') IS NOT NULL
                AND updated_at <= NOW() - ($1 * INTERVAL '1 hour')
            RETURNING id
            """,
            auto_submit_hours,
        )
    if auto_approve_enabled:
        approved = await Postgres.fetch(
            """
            UPDATE public.presence_timelogs
            SET status = 'approved', reviewed_at = NOW(),
                reviewed_by = 'presence:auto', updated_at = NOW()
            WHERE status = 'submitted' AND deleted_at IS NULL
                AND submitted_at <= NOW() - ($1 * INTERVAL '1 day')
            RETURNING id
            """,
            auto_approve_days,
        )
    return {"submitted": len(submitted), "approved": len(approved)}
