from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


SPEC = spec_from_file_location("presence_dashboard", Path("server/dashboard.py"))
dashboard = module_from_spec(SPEC)
sys.modules[SPEC.name] = dashboard
assert SPEC.loader is not None
SPEC.loader.exec_module(dashboard)


def utc(hour: int) -> datetime:
    return datetime(2026, 7, 13, hour, tzinfo=timezone.utc)


def test_dashboard_prioritizes_latest_user_machine_and_lists_others():
    sessions = [
        {
            "user_name": "alice",
            "machine_name": "WS-OLD",
            "last_input_at": utc(8),
            "last_heartbeat_at": utc(11),
            "is_connected": True,
        },
        {
            "user_name": "alice",
            "machine_name": "WS-NEW",
            "last_input_at": utc(10),
            "last_heartbeat_at": utc(10),
            "is_connected": True,
            "foreground_application": "nuke.exe",
            "foreground_title": "sh010 comp",
        },
        {
            "user_name": "bob",
            "machine_name": "WS-OLD",
            "last_input_at": utc(9),
            "last_heartbeat_at": utc(9),
            "is_connected": False,
        },
    ]
    tasks = [
        {
            "user_name": "alice",
            "project_name": "Demo",
            "folder_path": "/shots/010",
            "task_name": "Comp",
            "total_seconds": 3600,
            "dcc_name": "NukeX",
            "dcc_version": "15.2.1",
            "workfile_name": "sh010_comp_v012.nk",
        }
    ]
    day_starts = [{"user_name": "alice", "day_started_at": utc(7)}]

    machine_contexts = [
        {
            "source_machine_name": "WS-NEW",
            "dcc_name": "NukeX",
            "dcc_version": "15.2.1",
        }
    ]
    result = dashboard.build_dashboard_rows(
        sessions, tasks, day_starts, machine_contexts
    )

    alice = result["users"][0]
    assert alice == {
        "user_name": "alice",
        "computer_name": "WS-NEW",
        "other_computers": ["WS-OLD"],
        "last_active_at": utc(10),
        "last_project": "Demo",
        "last_folder": "/shots/010",
        "last_task": "Comp",
        "last_task_seconds": 3600,
        "dcc": "NukeX 15.2.1",
        "workfile": "sh010_comp_v012.nk",
        "foreground_application": "nuke.exe",
        "foreground_title": "sh010 comp",
        "day_started_at": utc(7),
    }
    new_computer = next(
        row for row in result["computers"] if row["computer_name"] == "WS-NEW"
    )
    assert new_computer["dcc"] == "NukeX 15.2.1"
    old_computer = next(
        row for row in result["computers"] if row["computer_name"] == "WS-OLD"
    )
    assert old_computer["last_user"] == "bob"
    assert old_computer["last_active_at"] == utc(9)


def test_dashboard_handles_missing_activity_timestamps():
    result = dashboard.build_dashboard_rows(
        [{"user_name": "alice", "machine_name": "WS-01"}], [], []
    )
    assert result["users"][0]["last_active_at"] is None
    assert result["computers"][0]["last_user"] == "alice"
