# AYON Presence

> **Platform support:** AYON Presence is a Windows-only addon. Its tray activity
> and foreground application monitoring do not run on Linux or macOS.

AYON addon that records whether authenticated tray users are connected and
recently active, without recording keys, clicks, cursor positions, or absolute
workfile paths. Optional foreground application and encrypted window-title
reporting are disabled by default.

The launcher client listens only for the fact that keyboard or mouse input
occurred. It posts an event immediately when the user changes between active
and idle, plus a heartbeat every five minutes. The server stores the audit
events, turns them into activity intervals, and creates calendar-day summaries.

## Features

- Authenticated identity: the server uses the AYON API token user and ignores
  usernames in client payloads.
- Multi-machine sessions with crash/disconnect timeout handling.
- Current presence API and embedded AYON web page.
- Sortable user, computer, and project activity subtabs with DCC, workfile,
  date-range, and project-time context.
- Optional manager-only raw Events debug tab with cursor-based lazy loading.
- Opt-in foreground application reporting and passphrase-encrypted window titles,
  emitted only when foreground context changes.
- Startup workfile and configured DCC metadata for hosts that load files after
  AYON host installation or omit runtime application information.
- Raw events, sessions, durable activity intervals, and daily summaries.
- Per-user project/folder/task active-time intervals from native AYON application
  launches and in-host task changes, including start, end, and total seconds.
- Calendar days are always midnight-to-midnight in the configured timezone.
- Summary processing defaults to 04:00, independently of the day boundary.
- Active time merges overlapping intervals across a user's machines.
- Idempotent catch-up aggregation protected by a PostgreSQL advisory lock.

## Defaults

| Setting | Default |
| --- | --- |
| Heartbeat | 300 seconds |
| Day End quiet heartbeats | 20 |
| Active/idle threshold | 300 seconds |
| Disconnect timeout | 600 seconds |
| Summary run time | 04:00 |
| Reporting timezone | Europe/Prague |
| Per-task active-time tracking | Enabled |
| Foreground application reporting | Disabled |
| Foreground application title reporting | Disabled |
| Maximum foreground title length | 32 characters |
| Raw event retention | 90 days |
| Raw events debug view | Enabled |
| Projects calendar week start | Monday |

## Development

```powershell
python -m pytest
python create_package.py
```

The package command builds `frontend/` with npm when Node is available and
creates `package/presence-0.6.1.zip`. Upload that zip to AYON, add Presence to a
bundle, configure its studio settings, and restart the tray.

The Presence web page is registered in AYON's **Settings** frontend scope. AYON
loads addon frontends from the production bundle, so the bundle containing
Presence must be set as production before the page appears. Restart AYON Server
after installing or changing the production addon version, then refresh the
browser.

Presence requires AYON Core only. It does not require or integrate with ftrack
or Timers Manager, so neither addon needs to be included in the bundle.

## Foreground reporting

Foreground application and title reporting are independent opt-in studio
settings and currently run on Windows trays. Application executable names are
stored as plaintext. Titles are stripped of control characters, whitespace
normalized, truncated to the configured limit, and encrypted with AES-256-GCM
before they are written to PostgreSQL.

Title reporting requires selecting an AYON Secret containing a passphrase.
Presence derives the encryption key with scrypt and stores only the Secret name,
a random non-secret salt, ciphertext, and nonce. Keep old Secrets when rotating
keys so retained events remain readable; create a new Secret name instead of
changing an existing value. A server restart is required after changing a
Secret's value because derived keys are cached in server memory.

## Workday boundaries

The Users table shows Day Started and Day Ended in the reporting timezone. Day
Ended is set to the last input time after the configured number of heartbeat
intervals pass without newer activity. New activity clears Day Ended. Daily
summary processing repairs historical boundaries from retained activity data;
when activity crosses a calendar boundary, the earlier day ends exactly at local
midnight.

The server creates these tables in the `public` schema on setup:

- `presence_sessions`
- `presence_events`
- `presence_title_keys`
- `presence_activity_intervals`
- `presence_day_boundaries`
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
| `GET /project-time?from=YYYY-MM-DD&to=YYYY-MM-DD` | Project task-time totals | Manager |
| `GET /raw-events?page_size=50&before_id=123` | Cursor-paginated raw events | Manager |
| `GET /summaries?from=YYYY-MM-DD&to=YYYY-MM-DD` | Daily summaries | Manager |

## Native AYON task tracking

Presence uses AYON's own application context. A post-launch hook selects the
`project_name`, `folder_path`, and `task_name` used to launch a local application.
When a supported host emits AYON's native `taskChanged` event, Presence switches
to that new context as well.

Task intervals measure active input time for the most recently selected AYON
task. When the configured idle threshold is reached, Presence closes the current
task interval. It opens a new interval for the same task when input activity
returns. Launching or switching to another AYON task closes the prior interval
and selects the new one.

Each `presence_task_intervals` record contains:

- authenticated AYON `user_name`
- `project_name`, `folder_path`, and `task_name`
- `started_at` and `ended_at`
- `total_seconds`
- source session/machine and close status for diagnostics

`started_at` is the time the AYON tray observes the native task selection or
resumes it after an idle period. `ended_at` is recorded on idle, task switch,
explicit context clearing, or tray shutdown. A stale interval is also closed by
the server disconnect timeout after a crash or network loss.

Only one task interval is open per user. Starting a different task closes the
previous interval. Matching notifications from another tray refresh the existing
interval, avoiding double-counting when the same AYON user is active on multiple
machines.

Presence never records keystrokes, clicks, cursor positions, or absolute workfile
paths. Foreground application and title collection remain opt-in studio settings;
titles are cleaned, length-limited, and encrypted before database storage. If
multiple AYON hosts are open, the last native AYON task selection remains selected
until another launch or `taskChanged` event selects a different task.
