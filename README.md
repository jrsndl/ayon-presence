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
| Raw event retention | 30 days |

## Development

```powershell
python -m pytest
python create_package.py
```

The package command builds `frontend/` with npm when Node is available and
creates `package/presence-0.1.0.zip`. Upload that zip to AYON, add Presence to a
bundle, configure its studio settings, and restart the tray.

The server creates these tables in the `public` schema on setup:

- `presence_sessions`
- `presence_events`
- `presence_activity_intervals`
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
| `GET /summaries?from=YYYY-MM-DD&to=YYYY-MM-DD` | Daily summaries | Manager |
