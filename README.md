# AYON Presence

AYON addon that records whether authenticated tray users are connected and
recently active, without recording keys, clicks, cursor positions, application
names, or window titles.

The launcher client listens only for the fact that keyboard or mouse input
occurred. It posts an event immediately when the user changes between active
and idle, plus a heartbeat every five minutes. The server stores the audit
events, turns them into activity intervals, and creates calendar-day summaries.

## Features

- Authenticated identity: the server uses the AYON API token user and ignores
  usernames in client payloads.
- Multi-machine sessions with crash/disconnect timeout handling.
- Current presence API and embedded AYON web page.
- Raw events, sessions, durable activity intervals, and daily summaries.
- Per-user project/folder/task timer intervals received through AYON Timers
  Manager, including start, end, and total seconds.
- Calendar days are always midnight-to-midnight in the configured timezone.
- Summary processing defaults to 04:00, independently of the day boundary.
- Active time merges overlapping intervals across a user's machines.
- Idempotent catch-up aggregation protected by a PostgreSQL advisory lock.

## Defaults

| Setting | Default |
| --- | --- |
| Heartbeat | 300 seconds |
| Active/idle threshold | 300 seconds |
| Disconnect timeout | 600 seconds |
| Summary run time | 04:00 |
| Reporting timezone | Europe/Prague |
| Task timer tracking | Enabled |
| Raw event retention | 30 days |

## Development

```powershell
python -m pytest
python create_package.py
```

The package command builds `frontend/` with npm when Node is available and
creates `package/presence-0.2.0.zip`. Upload that zip to AYON, add Presence to a
bundle, configure its studio settings, and restart the tray.

The server creates these tables in the `public` schema on setup:

- `presence_sessions`
- `presence_events`
- `presence_activity_intervals`
- `presence_task_intervals`
- `presence_daily_activity`
- `presence_summary_runs`

The scheduler runs only for the addon version in the production bundle. It
closes stale sessions every minute and catches up missing calendar days after a
server restart.

## API

All routes are below `/api/addons/presence/{version}` and require AYON
authentication.

| Method and route | Purpose | Access |
| --- | --- | --- |
| `POST /events` | Tray state changes and heartbeat | Authenticated user |
| `GET /users` | Current/recent machine presence | Authenticated user |
| `GET /activity?from=YYYY-MM-DD&to=YYYY-MM-DD` | Own interval log | Authenticated user |
| `GET /activity?...&user_name=name` | Another user's interval log | Manager |
| `GET /task-activity?from=YYYY-MM-DD&to=YYYY-MM-DD` | Own per-task time log | Authenticated user |
| `GET /task-activity?...&user_name=name` | Another user's task time log | Manager |
| `GET /summaries?from=YYYY-MM-DD&to=YYYY-MM-DD` | Daily summaries | Manager |

## Task timer integration

Presence registers as a passive AYON Timers Manager connector. The ftrack addon
listens for ftrack `Timer` changes and sends task starts and stops through Timers
Manager; Presence receives the same normalized notifications. It does not need
ftrack credentials and does not query ftrack directly.

Each `presence_task_intervals` record contains:

- authenticated AYON `user_name`
- `project_name`, `folder_path`, and `task_name`
- `started_at` and `ended_at`
- `total_seconds`
- source session/machine and close status for diagnostics

`started_at` is the time the AYON tray observed the timer start. Normal ftrack
events arrive immediately; if a tray starts while an ftrack timer is already
running, the first observation time is used because the current ftrack connector
does not include the original timer timestamp in its Timers Manager payload.

Only one task interval is open per user. Starting a different task closes the
previous interval. Matching notifications from another tray refresh the existing
interval, avoiding double-counting when the same ftrack account is observed on
multiple machines.
