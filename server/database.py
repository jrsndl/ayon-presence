from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from ayon_server.lib.postgres import Postgres

from .aggregation import ActivityInterval, summarize_day, utc_day_bounds
from .models import PresenceEvent


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS public.presence_sessions (
    session_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    platform TEXT NOT NULL,
    client_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ NOT NULL,
    last_input_at TIMESTAMPTZ,
    idle_seconds INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'active',
    exit_reason TEXT
);
CREATE INDEX IF NOT EXISTS presence_sessions_user_machine_idx
    ON public.presence_sessions (user_name, machine_name, last_heartbeat_at DESC);

CREATE TABLE IF NOT EXISTS public.presence_events (
    id BIGSERIAL PRIMARY KEY,
    user_name TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    client_time TIMESTAMPTZ,
    last_input_at TIMESTAMPTZ,
    idle_seconds INTEGER NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS presence_events_user_time_idx
    ON public.presence_events (user_name, received_at DESC);

CREATE TABLE IF NOT EXISTS public.presence_activity_intervals (
    id BIGSERIAL PRIMARY KEY,
    user_name TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    session_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS presence_one_open_interval_idx
    ON public.presence_activity_intervals (session_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS presence_intervals_range_idx
    ON public.presence_activity_intervals (started_at, ended_at);

CREATE TABLE IF NOT EXISTS public.presence_task_intervals (
    id BIGSERIAL PRIMARY KEY,
    user_name TEXT NOT NULL,
    project_name TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    task_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    total_seconds INTEGER NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ NOT NULL,
    source_session_id TEXT NOT NULL,
    source_machine_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS presence_one_open_task_per_user_idx
    ON public.presence_task_intervals (user_name) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS presence_task_intervals_range_idx
    ON public.presence_task_intervals (user_name, started_at, ended_at);

CREATE TABLE IF NOT EXISTS public.presence_daily_activity (
    user_name TEXT NOT NULL,
    activity_date DATE NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    machines JSONB NOT NULL,
    earliest_activity TIMESTAMPTZ,
    latest_activity TIMESTAMPTZ,
    total_active_seconds INTEGER NOT NULL DEFAULT 0,
    calculated_at TIMESTAMPTZ NOT NULL,
    calculation_version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_name, activity_date)
);

CREATE TABLE IF NOT EXISTS public.presence_summary_runs (
    activity_date DATE PRIMARY KEY,
    calculated_at TIMESTAMPTZ NOT NULL
);
"""


async def create_schema() -> None:
    await Postgres.execute(SCHEMA_SQL)


def _payload_json(event: PresenceEvent) -> str:
    return event.json()


async def record_event(
    user_name: str,
    event: PresenceEvent,
    idle_threshold_seconds: int,
) -> datetime:
    now = datetime.now(timezone.utc)
    last_input = event.last_input_at
    if last_input is not None and last_input.tzinfo is None:
        last_input = last_input.replace(tzinfo=timezone.utc)
    if last_input is None or last_input > now + timedelta(minutes=5):
        last_input = now - timedelta(seconds=event.idle_seconds)
    state = (
        "idle"
        if event.event_type == "idle" or event.idle_seconds >= idle_threshold_seconds
        else "active"
    )

    async with Postgres.transaction():
        await Postgres.execute(
            """
            INSERT INTO public.presence_events (
                user_name, machine_name, session_id, event_type, received_at,
                client_time, last_input_at, idle_seconds, payload
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            """,
            user_name,
            event.machine_name,
            event.session_id,
            event.event_type,
            now,
            event.client_time,
            last_input,
            event.idle_seconds,
            _payload_json(event),
        )
        await Postgres.execute(
            """
            INSERT INTO public.presence_sessions (
                session_id, user_name, machine_name, platform, client_version,
                started_at, last_heartbeat_at, last_input_at, idle_seconds, state
            ) VALUES ($1, $2, $3, $4, $5, $6, $6, $7, $8, $9)
            ON CONFLICT (session_id) DO UPDATE SET
                last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                last_input_at = EXCLUDED.last_input_at,
                idle_seconds = EXCLUDED.idle_seconds,
                state = EXCLUDED.state,
                ended_at = CASE WHEN $10 = 'session_end' THEN $6 ELSE NULL END,
                exit_reason = CASE WHEN $10 = 'session_end' THEN 'normal' ELSE NULL END
            """,
            event.session_id,
            user_name,
            event.machine_name,
            event.platform,
            event.client_version,
            now,
            last_input,
            event.idle_seconds,
            state,
            event.event_type,
        )

        if state == "active" and event.event_type != "session_end":
            inferred_start = max(
                last_input, now - timedelta(seconds=idle_threshold_seconds)
            )
            await Postgres.execute(
                """
                INSERT INTO public.presence_activity_intervals (
                    user_name, machine_name, session_id, started_at, last_heartbeat_at
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (session_id) WHERE ended_at IS NULL DO UPDATE SET
                    last_heartbeat_at = EXCLUDED.last_heartbeat_at
                """,
                user_name,
                event.machine_name,
                event.session_id,
                inferred_start,
                now,
            )
        else:
            end_at = now
            status = "closed"
            if event.event_type == "idle":
                end_at = min(
                    now, last_input + timedelta(seconds=idle_threshold_seconds)
                )
            await Postgres.execute(
                """
                UPDATE public.presence_activity_intervals
                SET ended_at = GREATEST(started_at, $2), status = $3,
                    last_heartbeat_at = $4
                WHERE session_id = $1 AND ended_at IS NULL
                """,
                event.session_id,
                end_at,
                status,
                now,
            )
        if event.event_type.startswith("task_"):
            await _record_task_event(user_name, event, now)
    return now


async def _record_task_event(
    user_name: str, event: PresenceEvent, now: datetime
) -> None:
    project_name = event.project_name
    folder_path = event.folder_path
    task_name = event.task_name
    assert project_name and folder_path and task_name

    open_row = await Postgres.fetchrow(
        """
        SELECT id, project_name, folder_path, task_name
        FROM public.presence_task_intervals
        WHERE user_name = $1 AND ended_at IS NULL
        FOR UPDATE
        """,
        user_name,
    )
    context_matches = bool(
        open_row
        and open_row["project_name"] == project_name
        and open_row["folder_path"] == folder_path
        and open_row["task_name"] == task_name
    )

    if event.event_type == "task_stop":
        if context_matches:
            await _close_task_interval(open_row["id"], now, "closed")
        return

    if context_matches:
        await Postgres.execute(
            """
            UPDATE public.presence_task_intervals
            SET last_seen_at = $2,
                source_session_id = $3,
                source_machine_name = $4,
                total_seconds = GREATEST(
                    0, FLOOR(EXTRACT(EPOCH FROM ($2 - started_at)))::integer
                )
            WHERE id = $1
            """,
            open_row["id"],
            now,
            event.session_id,
            event.machine_name,
        )
        return

    # A heartbeat from a stale second tray must not switch the current task.
    if event.event_type == "task_heartbeat" and open_row:
        return

    if open_row:
        await _close_task_interval(open_row["id"], now, "switched")

    started_at = event.task_started_at or now
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    # Client time is useful for retry recovery, but keep it close to the
    # authenticated server receipt time to prevent fabricated long intervals.
    if started_at > now + timedelta(minutes=5) or started_at < now - timedelta(
        hours=24
    ):
        started_at = now

    await Postgres.execute(
        """
        INSERT INTO public.presence_task_intervals (
            user_name, project_name, folder_path, task_name, started_at,
            last_seen_at, source_session_id, source_machine_name
        ) VALUES ($1, $2, $3, $4, $5, $5, $6, $7)
        """,
        user_name,
        project_name,
        folder_path,
        task_name,
        started_at,
        event.session_id,
        event.machine_name,
    )


async def _close_task_interval(
    interval_id: int, ended_at: datetime, status: str
) -> None:
    await Postgres.execute(
        """
        UPDATE public.presence_task_intervals
        SET ended_at = GREATEST(started_at, $2),
            total_seconds = GREATEST(
                0,
                FLOOR(EXTRACT(EPOCH FROM (
                    GREATEST(started_at, $2) - started_at
                )))::integer
            ),
            last_seen_at = GREATEST(last_seen_at, $2),
            status = $3
        WHERE id = $1 AND ended_at IS NULL
        """,
        interval_id,
        ended_at,
        status,
    )


async def close_stale_sessions(disconnect_timeout_seconds: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=disconnect_timeout_seconds)
    rows = await Postgres.fetch(
        """
        UPDATE public.presence_sessions
        SET ended_at = last_heartbeat_at, state = 'disconnected', exit_reason = 'timeout'
        WHERE ended_at IS NULL AND last_heartbeat_at < $1
        RETURNING session_id, last_heartbeat_at
        """,
        cutoff,
    )
    for row in rows:
        await Postgres.execute(
            """
            UPDATE public.presence_activity_intervals
            SET ended_at = GREATEST(started_at, $2), status = 'timed_out'
            WHERE session_id = $1 AND ended_at IS NULL
            """,
            row["session_id"],
            row["last_heartbeat_at"],
        )
    await Postgres.execute(
        """
        UPDATE public.presence_task_intervals
        SET ended_at = GREATEST(started_at, last_seen_at),
            total_seconds = GREATEST(
                0,
                FLOOR(EXTRACT(EPOCH FROM (
                    GREATEST(started_at, last_seen_at) - started_at
                )))::integer
            ),
            status = 'timed_out'
        WHERE ended_at IS NULL AND last_seen_at < $1
        """,
        cutoff,
    )
    return len(rows)


async def current_users() -> list[dict]:
    rows = await Postgres.fetch(
        """
        SELECT DISTINCT ON (user_name, machine_name)
            user_name, machine_name, platform, client_version, state,
            last_heartbeat_at, last_input_at, idle_seconds
        FROM public.presence_sessions
        WHERE last_heartbeat_at > NOW() - INTERVAL '30 days'
        ORDER BY user_name, machine_name, last_heartbeat_at DESC
        """,
    )
    return [dict(row) for row in rows]


async def consolidate_day(activity_date: date, timezone_name: str) -> None:
    period_start, period_end = utc_day_bounds(activity_date, timezone_name)
    rows = await Postgres.fetch(
        """
        SELECT user_name, machine_name, started_at, ended_at
        FROM public.presence_activity_intervals
        WHERE started_at < $2 AND COALESCE(ended_at, last_heartbeat_at) > $1
        """,
        period_start,
        period_end,
    )
    intervals = [
        ActivityInterval(
            row["user_name"],
            row["machine_name"],
            row["started_at"],
            row["ended_at"] or period_end,
        )
        for row in rows
    ]
    summaries = summarize_day(activity_date, timezone_name, intervals)
    async with Postgres.transaction():
        await Postgres.execute("SELECT pg_advisory_xact_lock(70726573656)")
        await Postgres.execute(
            "DELETE FROM public.presence_daily_activity WHERE activity_date = $1",
            activity_date,
        )
        for item in summaries.values():
            await Postgres.execute(
                """
                INSERT INTO public.presence_daily_activity (
                    user_name, activity_date, period_start, period_end, machines,
                    earliest_activity, latest_activity, total_active_seconds,
                    calculated_at, calculation_version
                ) VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8,NOW(),1)
                ON CONFLICT (user_name, activity_date) DO UPDATE SET
                    machines=EXCLUDED.machines,
                    earliest_activity=EXCLUDED.earliest_activity,
                    latest_activity=EXCLUDED.latest_activity,
                    total_active_seconds=EXCLUDED.total_active_seconds,
                    calculated_at=EXCLUDED.calculated_at
                """,
                item["user_name"],
                item["activity_date"],
                item["period_start"],
                item["period_end"],
                json.dumps(item["machines"]),
                item["earliest_activity"],
                item["latest_activity"],
                item["total_active_seconds"],
            )
        await Postgres.execute(
            """
            INSERT INTO public.presence_summary_runs (activity_date, calculated_at)
            VALUES ($1, NOW()) ON CONFLICT (activity_date)
            DO UPDATE SET calculated_at = EXCLUDED.calculated_at
            """,
            activity_date,
        )


async def summaries(date_from: date, date_to: date) -> list[dict]:
    rows = await Postgres.fetch(
        """
        SELECT * FROM public.presence_daily_activity
        WHERE activity_date BETWEEN $1 AND $2
        ORDER BY activity_date DESC, user_name
        """,
        date_from,
        date_to,
    )
    return [dict(row) for row in rows]


async def activity_log(
    user_name: str,
    date_from: date,
    date_to: date,
    timezone_name: str,
) -> list[dict]:
    period_start, _ = utc_day_bounds(date_from, timezone_name)
    _, period_end = utc_day_bounds(date_to, timezone_name)
    rows = await Postgres.fetch(
        """
        SELECT id, user_name, machine_name, session_id, started_at,
            COALESCE(ended_at, last_heartbeat_at) AS ended_at, status
        FROM public.presence_activity_intervals
        WHERE user_name = $1
            AND started_at < $3
            AND COALESCE(ended_at, last_heartbeat_at) > $2
        ORDER BY started_at DESC
        """,
        user_name,
        period_start,
        period_end,
    )
    return [dict(row) for row in rows]


async def task_activity_log(
    user_name: str,
    date_from: date,
    date_to: date,
    timezone_name: str,
) -> list[dict]:
    period_start, _ = utc_day_bounds(date_from, timezone_name)
    _, period_end = utc_day_bounds(date_to, timezone_name)
    rows = await Postgres.fetch(
        """
        SELECT id, user_name, project_name, folder_path, task_name,
            project_name || folder_path || '/' || task_name AS task_path,
            started_at, ended_at,
            CASE
                WHEN ended_at IS NULL THEN GREATEST(
                    total_seconds,
                    FLOOR(EXTRACT(EPOCH FROM (last_seen_at - started_at)))::integer
                )
                ELSE total_seconds
            END AS total_seconds,
            source_machine_name, status
        FROM public.presence_task_intervals
        WHERE user_name = $1
            AND started_at < $3
            AND COALESCE(ended_at, last_seen_at) > $2
        ORDER BY started_at DESC
        """,
        user_name,
        period_start,
        period_end,
    )
    return [dict(row) for row in rows]


async def missing_summary_dates(
    target_date: date, timezone_name: str, limit: int = 31
) -> list[date]:
    """Return unprocessed dates through target, oldest first.

    The bounded result lets a restarted server catch up incrementally without
    monopolizing a worker after a long outage.
    """
    rows = await Postgres.fetch(
        """
        WITH bounds AS (
            SELECT COALESCE(
                MIN((started_at AT TIME ZONE $2)::date), $1::date
            ) AS first_date
            FROM public.presence_activity_intervals
        ), days AS (
            SELECT generate_series(first_date, $1::date, INTERVAL '1 day')::date AS day
            FROM bounds
        )
        SELECT day FROM days
        LEFT JOIN public.presence_summary_runs runs ON runs.activity_date = day
        WHERE runs.activity_date IS NULL
        ORDER BY day
        LIMIT $3
        """,
        target_date,
        timezone_name,
        limit,
    )
    return [row["day"] for row in rows]


async def prune_events(retention_days: int) -> None:
    await Postgres.execute(
        "DELETE FROM public.presence_events WHERE received_at < NOW() - ($1 * INTERVAL '1 day')",
        retention_days,
    )
