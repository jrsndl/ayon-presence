from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ayon_server.lib.postgres import Postgres
from ayon_server.secrets import Secrets

from .aggregation import (
    ActivityInterval,
    repaired_day_ended_at,
    summarize_day,
    utc_day_bounds,
)
from .dashboard import build_dashboard_rows
from .models import PresenceEvent
from .raw_events import serialize_raw_events_page
from .title_crypto import EncryptedTitle, TitleCipher, TitleEncryptionError


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
    exit_reason TEXT,
    foreground_application TEXT,
    foreground_title_ciphertext BYTEA,
    foreground_title_nonce BYTEA,
    foreground_title_key_name TEXT,
    tray_timezone TEXT
);
CREATE INDEX IF NOT EXISTS presence_sessions_user_machine_idx
    ON public.presence_sessions (user_name, machine_name, last_heartbeat_at DESC);
ALTER TABLE public.presence_sessions
    ADD COLUMN IF NOT EXISTS foreground_application TEXT;
ALTER TABLE public.presence_sessions
    ADD COLUMN IF NOT EXISTS foreground_title_ciphertext BYTEA;
ALTER TABLE public.presence_sessions
    ADD COLUMN IF NOT EXISTS foreground_title_nonce BYTEA;
ALTER TABLE public.presence_sessions
    ADD COLUMN IF NOT EXISTS foreground_title_key_name TEXT;
ALTER TABLE public.presence_sessions
    ADD COLUMN IF NOT EXISTS tray_timezone TEXT;

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
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    foreground_title_ciphertext BYTEA,
    foreground_title_nonce BYTEA,
    foreground_title_key_name TEXT
);
CREATE INDEX IF NOT EXISTS presence_events_user_time_idx
    ON public.presence_events (user_name, received_at DESC);
ALTER TABLE public.presence_events
    ADD COLUMN IF NOT EXISTS foreground_title_ciphertext BYTEA;
ALTER TABLE public.presence_events
    ADD COLUMN IF NOT EXISTS foreground_title_nonce BYTEA;
ALTER TABLE public.presence_events
    ADD COLUMN IF NOT EXISTS foreground_title_key_name TEXT;

CREATE TABLE IF NOT EXISTS public.presence_title_keys (
    key_name TEXT PRIMARY KEY,
    salt BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

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

CREATE TABLE IF NOT EXISTS public.presence_day_boundaries (
    user_name TEXT NOT NULL,
    activity_date DATE NOT NULL,
    day_started_at TIMESTAMPTZ NOT NULL,
    last_active_at TIMESTAMPTZ NOT NULL,
    day_ended_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_name, activity_date),
    CHECK (last_active_at >= day_started_at),
    CHECK (day_ended_at IS NULL OR day_ended_at >= day_started_at)
);
CREATE INDEX IF NOT EXISTS presence_day_boundaries_date_idx
    ON public.presence_day_boundaries (activity_date, user_name);

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
ALTER TABLE public.presence_task_intervals
    ADD COLUMN IF NOT EXISTS dcc_name TEXT;
ALTER TABLE public.presence_task_intervals
    ADD COLUMN IF NOT EXISTS dcc_version TEXT;
ALTER TABLE public.presence_task_intervals
    ADD COLUMN IF NOT EXISTS workfile_name TEXT;

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


_TITLE_CIPHERS: dict[str, TitleCipher] = {}


def _payload_json(event: PresenceEvent) -> str:
    """Serialize an event while guaranteeing titles never enter JSON storage."""
    return event.json(exclude={"foreground_title"})


async def _title_cipher(key_name: str) -> TitleCipher:
    cached = _TITLE_CIPHERS.get(key_name)
    if cached is not None:
        return cached
    passphrase = await Secrets.get(key_name)
    if not passphrase:
        raise TitleEncryptionError("The selected AYON Secret is missing or empty")
    row = await Postgres.fetchrow(
        """
        INSERT INTO public.presence_title_keys (key_name, salt, created_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (key_name) DO UPDATE SET key_name = EXCLUDED.key_name
        RETURNING salt
        """,
        key_name,
        os.urandom(16),
    )
    if row is None:
        raise TitleEncryptionError("Unable to prepare title encryption metadata")
    cipher = TitleCipher(str(passphrase), bytes(row["salt"]), key_name)
    _TITLE_CIPHERS[key_name] = cipher
    return cipher


async def _encrypt_title(
    title: str | None, key_name: str | None
) -> EncryptedTitle | None:
    if not title:
        return None
    if not key_name:
        raise TitleEncryptionError("No AYON Secret is selected for title encryption")
    return (await _title_cipher(key_name)).encrypt(title)


async def _decrypt_title(
    ciphertext: object, nonce: object, key_name: object
) -> str | None:
    if not ciphertext or not nonce or not key_name:
        return None
    try:
        return (await _title_cipher(str(key_name))).decrypt(
            bytes(ciphertext), bytes(nonce)
        )
    except Exception:
        return None


async def _rows_with_decrypted_titles(rows) -> list[dict]:
    result = []
    for source in rows:
        row = dict(source)
        row["foreground_title"] = await _decrypt_title(
            row.get("foreground_title_ciphertext"),
            row.get("foreground_title_nonce"),
            row.get("foreground_title_key_name"),
        )
        row.pop("foreground_title_ciphertext", None)
        row.pop("foreground_title_nonce", None)
        row.pop("foreground_title_key_name", None)
        result.append(row)
    return result


async def record_event(
    user_name: str,
    event: PresenceEvent,
    idle_threshold_seconds: int,
    timezone_name: str,
    heartbeat_interval_seconds: int,
    day_end_heartbeat_count: int,
    foreground_title_key_name: str | None = None,
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
    encrypted_title = await _encrypt_title(
        event.foreground_title, foreground_title_key_name
    )
    title_ciphertext = encrypted_title.ciphertext if encrypted_title else None
    title_nonce = encrypted_title.nonce if encrypted_title else None
    stored_key_name = foreground_title_key_name if encrypted_title else None

    async with Postgres.transaction():
        await Postgres.execute(
            """
            INSERT INTO public.presence_events (
                user_name, machine_name, session_id, event_type, received_at,
                client_time, last_input_at, idle_seconds, payload,
                foreground_title_ciphertext, foreground_title_nonce,
                foreground_title_key_name
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12)
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
            title_ciphertext,
            title_nonce,
            stored_key_name,
        )
        await Postgres.execute(
            """
            INSERT INTO public.presence_sessions (
                session_id, user_name, machine_name, platform, client_version,
                started_at, last_heartbeat_at, last_input_at, idle_seconds, state,
                foreground_application, foreground_title_ciphertext,
                foreground_title_nonce, foreground_title_key_name, tray_timezone
            ) VALUES ($1, $2, $3, $4, $5, $6, $6, $7, $8, $9, $11, $12, $13, $14, $15)
            ON CONFLICT (session_id) DO UPDATE SET
                last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                last_input_at = EXCLUDED.last_input_at,
                idle_seconds = EXCLUDED.idle_seconds,
                state = EXCLUDED.state,
                ended_at = CASE WHEN $10 = 'session_end' THEN $6 ELSE NULL END,
                exit_reason = CASE WHEN $10 = 'session_end' THEN 'normal' ELSE NULL END,
                foreground_application = CASE
                    WHEN $10 = 'foreground_change' THEN $11
                    ELSE presence_sessions.foreground_application
                END,
                foreground_title_ciphertext = CASE
                    WHEN $10 = 'foreground_change' THEN $12
                    ELSE presence_sessions.foreground_title_ciphertext
                END,
                foreground_title_nonce = CASE
                    WHEN $10 = 'foreground_change' THEN $13
                    ELSE presence_sessions.foreground_title_nonce
                END,
                foreground_title_key_name = CASE
                    WHEN $10 = 'foreground_change' THEN $14
                    ELSE presence_sessions.foreground_title_key_name
                END,
                tray_timezone = COALESCE($15, presence_sessions.tray_timezone)
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
            event.foreground_application,
            title_ciphertext,
            title_nonce,
            stored_key_name,
            event.tray_timezone,
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
        await _record_day_boundary(
            user_name,
            event.event_type,
            last_input,
            now,
            timezone_name,
            heartbeat_interval_seconds,
            day_end_heartbeat_count,
        )
    return now


async def _record_day_boundary(
    user_name: str,
    event_type: str,
    last_input: datetime,
    now: datetime,
    timezone_name: str,
    heartbeat_interval_seconds: int,
    day_end_heartbeat_count: int,
) -> None:
    """Update today's workday and close it after the configured quiet period."""
    activity_date = last_input.astimezone(ZoneInfo(timezone_name)).date()
    await Postgres.execute(
        """
        INSERT INTO public.presence_day_boundaries (
            user_name, activity_date, day_started_at, last_active_at, updated_at
        ) VALUES ($1, $2, $3, $3, $4)
        ON CONFLICT (user_name, activity_date) DO UPDATE SET
            day_started_at = LEAST(
                presence_day_boundaries.day_started_at,
                EXCLUDED.day_started_at
            ),
            last_active_at = GREATEST(
                presence_day_boundaries.last_active_at,
                EXCLUDED.last_active_at
            ),
            day_ended_at = CASE
                WHEN EXCLUDED.last_active_at
                    > presence_day_boundaries.last_active_at THEN NULL
                ELSE presence_day_boundaries.day_ended_at
            END,
            updated_at = EXCLUDED.updated_at
        """,
        user_name,
        activity_date,
        last_input,
        now,
    )
    if event_type != "heartbeat":
        return
    quiet_seconds = heartbeat_interval_seconds * day_end_heartbeat_count
    await Postgres.execute(
        """
        UPDATE public.presence_day_boundaries
        SET day_ended_at = last_active_at, updated_at = $3
        WHERE user_name = $1
            AND activity_date = $2
            AND day_ended_at IS NULL
            AND last_active_at <= $3 - ($4 * INTERVAL '1 second')
        """,
        user_name,
        activity_date,
        now,
        quiet_seconds,
    )


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
                dcc_name = COALESCE($5, dcc_name),
                dcc_version = COALESCE($6, dcc_version),
                workfile_name = COALESCE($7, workfile_name),
                total_seconds = GREATEST(
                    0, FLOOR(EXTRACT(EPOCH FROM ($2 - started_at)))::integer
                )
            WHERE id = $1
            """,
            open_row["id"],
            now,
            event.session_id,
            event.machine_name,
            event.dcc_name,
            event.dcc_version,
            event.workfile_name,
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
            last_seen_at, source_session_id, source_machine_name,
            dcc_name, dcc_version, workfile_name
        ) VALUES ($1, $2, $3, $4, $5, $5, $6, $7, $8, $9, $10)
        """,
        user_name,
        project_name,
        folder_path,
        task_name,
        started_at,
        event.session_id,
        event.machine_name,
        event.dcc_name,
        event.dcc_version,
        event.workfile_name,
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


async def dashboard_data(
    timezone_name: str, disconnect_timeout_seconds: int
) -> dict[str, list[dict]]:
    sessions = await Postgres.fetch(
        """
        SELECT DISTINCT ON (user_name, machine_name)
            user_name, machine_name, platform, client_version, state,
            last_heartbeat_at, last_input_at, idle_seconds,
            foreground_application, foreground_title_ciphertext,
            foreground_title_nonce, foreground_title_key_name,
            last_heartbeat_at >= NOW() - ($1 * INTERVAL '1 second')
                AS is_connected
        FROM public.presence_sessions
        WHERE last_heartbeat_at > NOW() - INTERVAL '30 days'
        ORDER BY user_name, machine_name, last_heartbeat_at DESC
        """,
        disconnect_timeout_seconds,
    )
    sessions = await _rows_with_decrypted_titles(sessions)
    latest_tasks = await Postgres.fetch(
        """
        SELECT DISTINCT ON (user_name)
            user_name, project_name, folder_path, task_name,
            dcc_name, dcc_version, workfile_name,
            CASE
                WHEN ended_at IS NULL THEN GREATEST(
                    total_seconds,
                    FLOOR(EXTRACT(EPOCH FROM (NOW() - started_at)))::integer
                )
                ELSE total_seconds
            END AS total_seconds
        FROM public.presence_task_intervals
        ORDER BY user_name, COALESCE(ended_at, last_seen_at) DESC, started_at DESC
        """,
    )
    latest_machine_contexts = await Postgres.fetch(
        """
        SELECT DISTINCT ON (source_machine_name)
            source_machine_name, dcc_name, dcc_version
        FROM public.presence_task_intervals
        WHERE dcc_name IS NOT NULL
        ORDER BY source_machine_name, last_seen_at DESC, started_at DESC
        """,
    )
    local_today = datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
    day_boundaries = await Postgres.fetch(
        """
        SELECT user_name, day_started_at, day_ended_at
        FROM public.presence_day_boundaries
        WHERE activity_date = $1
        """,
        local_today,
    )
    return build_dashboard_rows(
        sessions,
        [dict(row) for row in latest_tasks],
        [dict(row) for row in day_boundaries],
        [dict(row) for row in latest_machine_contexts],
    )


async def consolidate_day(activity_date: date, timezone_name: str) -> None:
    period_start, period_end = utc_day_bounds(activity_date, timezone_name)
    rows = await Postgres.fetch(
        """
        SELECT user_name, machine_name, started_at, ended_at, last_heartbeat_at
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
            row["ended_at"] or row["last_heartbeat_at"],
        )
        for row in rows
    ]
    summaries = summarize_day(activity_date, timezone_name, intervals)
    input_rows = await Postgres.fetch(
        """
        SELECT user_name, MAX(last_input_at) AS last_active_at
        FROM public.presence_events
        WHERE last_input_at >= $1 AND last_input_at < $2
        GROUP BY user_name
        """,
        period_start,
        period_end,
    )
    last_input_by_user = {row["user_name"]: row["last_active_at"] for row in input_rows}
    active_over_midnight = {
        row["user_name"]
        for row in rows
        if (row["ended_at"] or row["last_heartbeat_at"]) >= period_end
    }
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
            last_active_at = last_input_by_user.get(
                item["user_name"], item["latest_activity"]
            )
            last_active_at = max(last_active_at, item["earliest_activity"])
            day_ended_at = repaired_day_ended_at(
                last_active_at,
                period_end,
                item["user_name"] in active_over_midnight,
            )
            await Postgres.execute(
                """
                INSERT INTO public.presence_day_boundaries (
                    user_name, activity_date, day_started_at, last_active_at,
                    day_ended_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (user_name, activity_date) DO UPDATE SET
                    day_started_at = EXCLUDED.day_started_at,
                    last_active_at = EXCLUDED.last_active_at,
                    day_ended_at = EXCLUDED.day_ended_at,
                    updated_at = EXCLUDED.updated_at
                """,
                item["user_name"],
                activity_date,
                item["earliest_activity"],
                last_active_at,
                day_ended_at,
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
        SELECT intervals.id, intervals.user_name, intervals.machine_name,
            intervals.session_id, intervals.started_at,
            COALESCE(intervals.ended_at, intervals.last_heartbeat_at) AS ended_at,
            intervals.status,
            sample.payload ->> 'foreground_application' AS foreground_application,
            sample.foreground_title_ciphertext,
            sample.foreground_title_nonce,
            sample.foreground_title_key_name
        FROM public.presence_activity_intervals intervals
        LEFT JOIN LATERAL (
            SELECT payload, foreground_title_ciphertext,
                foreground_title_nonce, foreground_title_key_name
            FROM public.presence_events events
            WHERE events.user_name = intervals.user_name
                AND events.session_id = intervals.session_id
                AND events.event_type = 'foreground_change'
                AND events.received_at <= COALESCE(
                    intervals.ended_at, intervals.last_heartbeat_at
                )
            ORDER BY events.received_at DESC
            LIMIT 1
        ) sample ON TRUE
        WHERE intervals.user_name = $1
            AND intervals.started_at < $3
            AND COALESCE(intervals.ended_at, intervals.last_heartbeat_at) > $2
        ORDER BY intervals.started_at DESC
        """,
        user_name,
        period_start,
        period_end,
    )
    return await _rows_with_decrypted_titles(rows)


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
            source_machine_name, status, dcc_name, dcc_version, workfile_name
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


async def project_time_summary(
    date_from: date,
    date_to: date,
    timezone_name: str,
) -> list[dict]:
    """Aggregate tracked task time per project within an inclusive local range."""
    period_start, _ = utc_day_bounds(date_from, timezone_name)
    _, period_end = utc_day_bounds(date_to, timezone_name)
    rows = await Postgres.fetch(
        """
        SELECT project_name,
            ARRAY_AGG(DISTINCT user_name ORDER BY user_name) AS users,
            COUNT(DISTINCT user_name)::integer AS user_count,
            GREATEST(
                0,
                FLOOR(SUM(EXTRACT(EPOCH FROM (
                    LEAST(COALESCE(ended_at, last_seen_at), $2)
                    - GREATEST(started_at, $1)
                ))))::integer
            ) AS total_seconds
        FROM public.presence_task_intervals
        WHERE started_at < $2
            AND COALESCE(ended_at, last_seen_at) > $1
        GROUP BY project_name
        ORDER BY project_name
        """,
        period_start,
        period_end,
    )
    return [dict(row) for row in rows]


async def raw_events_page(
    page_size: int,
    before_id: int | None = None,
) -> dict:
    """Return one newest-first page of raw PresenceEvent payloads."""
    rows = await Postgres.fetch(
        """
        SELECT id, user_name, received_at, payload,
            foreground_title_ciphertext, foreground_title_nonce,
            foreground_title_key_name
        FROM public.presence_events
        WHERE ($2::bigint IS NULL OR id < $2)
        ORDER BY id DESC
        LIMIT $1
        """,
        page_size + 1,
        before_id,
    )
    decrypted_rows = await _rows_with_decrypted_titles(rows)
    for row in decrypted_rows:
        if row["foreground_title"] is not None:
            payload = row["payload"] or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            row["payload"] = {**payload, "foreground_title": row["foreground_title"]}
    return serialize_raw_events_page(decrypted_rows, page_size)


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
