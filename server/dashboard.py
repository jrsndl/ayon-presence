"""Pure dashboard row construction shared by the API and tests."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional


def _last_active(session: Mapping[str, Any]) -> Optional[datetime]:
    return session.get("last_input_at") or session.get("last_heartbeat_at")


def _activity_sort_key(session: Mapping[str, Any]) -> tuple[float, str]:
    value = _last_active(session)
    timestamp = value.timestamp() if value is not None else float("-inf")
    return timestamp, str(session.get("machine_name") or "")


def build_dashboard_rows(
    sessions: Iterable[Mapping[str, Any]],
    latest_tasks: Iterable[Mapping[str, Any]],
    day_starts: Iterable[Mapping[str, Any]],
    latest_machine_contexts: Iterable[Mapping[str, Any]] = (),
) -> dict[str, list[dict[str, Any]]]:
    """Build deterministic user-centric and computer-centric rows."""
    task_by_user = {str(row["user_name"]): dict(row) for row in latest_tasks}
    day_start_by_user = {
        str(row["user_name"]): row.get("day_started_at") for row in day_starts
    }
    dcc_by_computer = {
        str(row["source_machine_name"]): _format_dcc(row)
        for row in latest_machine_contexts
    }
    by_user: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_computer: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for session in sessions:
        user_name = str(session["user_name"])
        machine_name = str(session["machine_name"])
        by_user[user_name].append(session)
        by_computer[machine_name].append(session)

    user_rows: list[dict[str, Any]] = []
    for user_name, user_sessions in sorted(by_user.items()):
        connected_sessions = [
            session for session in user_sessions if session.get("is_connected", True)
        ]
        primary_candidates = connected_sessions or user_sessions
        primary = max(primary_candidates, key=_activity_sort_key)
        primary_machine = str(primary["machine_name"])
        other_computers = sorted(
            {
                str(session["machine_name"])
                for session in connected_sessions
                if str(session["machine_name"]) != primary_machine
            }
        )
        task = task_by_user.get(user_name, {})
        user_rows.append(
            {
                "user_name": user_name,
                "computer_name": primary_machine,
                "other_computers": other_computers,
                "last_active_at": _last_active(primary),
                "last_project": task.get("project_name"),
                "last_folder": task.get("folder_path"),
                "last_task": task.get("task_name"),
                "last_task_seconds": task.get("total_seconds"),
                "dcc": _format_dcc(task),
                "workfile": task.get("workfile_name"),
                "day_started_at": day_start_by_user.get(user_name),
            }
        )

    computer_rows: list[dict[str, Any]] = []
    for computer_name, computer_sessions in sorted(by_computer.items()):
        latest = max(computer_sessions, key=_activity_sort_key)
        computer_rows.append(
            {
                "computer_name": computer_name,
                "last_user": str(latest["user_name"]),
                "last_active_at": _last_active(latest),
                "dcc": dcc_by_computer.get(computer_name),
            }
        )

    return {"users": user_rows, "computers": computer_rows}


def _format_dcc(context: Mapping[str, Any]) -> Optional[str]:
    name = context.get("dcc_name")
    version = context.get("dcc_version")
    if name and version:
        return f"{name} {version}"
    return str(name or version) if name or version else None
