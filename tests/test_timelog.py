from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pydantic
import pytest


def load_models():
    name = "presence_timelog_models"
    spec = spec_from_file_location(name, Path("server/models.py"))
    module = module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_timelog_models_validate_ranges_statuses_and_preferences():
    models = load_models()
    entry = models.TimeLogCreate(
        project_name="Demo",
        folder_path="/shots/010",
        task_name="comp",
        started_at="2026-07-16T08:00:00Z",
        ended_at="2026-07-16T09:30:00Z",
    )
    assert entry.task_name == "comp"

    with pytest.raises(pydantic.ValidationError):
        models.TimeLogCreate(
            started_at="2026-07-16T09:00:00Z",
            ended_at="2026-07-16T08:00:00Z",
        )
    with pytest.raises(pydantic.ValidationError):
        models.TimeLogReview(ids=[1], status="not_submitted")

    preferences = models.TimeLogPreferences(
        artist_timezone="Europe/Prague",
        start_hour="09:00",
        assigned_tasks_only=True,
    )
    assert preferences.artist_timezone == "Europe/Prague"


def test_timelog_is_a_connected_copy_with_server_side_ownership_rules():
    database = Path("server/timelog.py").read_text(encoding="utf-8")
    server = Path("server/__init__.py").read_text(encoding="utf-8")

    assert "source_task_interval_id BIGINT UNIQUE" in database
    assert "source_synced BOOLEAN" in database
    assert "FROM public.presence_task_intervals intervals" in database
    assert "presence_timelogs.source_synced = TRUE" in database
    assert "user_name = $1 AND id = ANY" in database
    assert "status IN ('not_submitted', 'disputed')" in database
    assert "Only submitted TimeLogs may be reviewed" in database
    assert "requested_user != user.name and not user.is_manager" in server
    assert "TimeLog review requires manager access" in server
    assert "update_timelog(entry_id, user.name" in server


def test_timelog_lifecycle_and_automation_are_configurable():
    settings = Path("server/settings.py").read_text(encoding="utf-8")
    database = Path("server/timelog.py").read_text(encoding="utf-8")
    server = Path("server/__init__.py").read_text(encoding="utf-8")

    assert '"timelog_auto_submit_hours": 24' in settings
    assert '"timelog_auto_approve_days": 7' in settings
    assert '"timelog_default_start_hour": "09:00"' in settings
    assert '"timelog_assigned_tasks_only": True' in settings
    assert "SET status = 'submitted'" in database
    assert "SET status = 'approved'" in database
    assert "await advance_timelog_statuses(" in server


def test_artist_frontend_exposes_shared_tracker_timesheet_and_calendar_views():
    main = Path("frontend/src/main.jsx").read_text(encoding="utf-8")
    source = Path("frontend/src/TimeLogApp.jsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/timelog.css").read_text(encoding="utf-8")

    assert "context.scope === 'dashboard'" in main
    assert "Presence TimeLog" in Path("package.py").read_text(encoding="utf-8")
    assert "TrackerView" in source
    assert "TimesheetView" in source
    assert "CalendarView" in source
    assert "Studio Time" not in source  # Labels are generated from timezone modes.
    assert "['studio', 'tray', 'artist']" in source
    assert "Activity" in source and "AutoLog" in source
    assert "Submit Selected" in source
    assert "Any User" in source
    assert "Limit task picker to tasks assigned to me" in source
    assert ".calendar-segment" in styles
    assert ".timesheet .frozen" in styles


def test_tray_advertises_timezone_without_third_party_dependencies():
    reporter = Path("client/ayon_presence/reporter.py").read_text(encoding="utf-8")
    models = Path("server/models.py").read_text(encoding="utf-8")
    database = Path("server/database.py").read_text(encoding="utf-8")

    assert '"tray_timezone": self.tray_timezone' in reporter
    assert "def local_timezone_name()" in reporter
    assert "tray_timezone: Optional[str]" in models
    assert "ADD COLUMN IF NOT EXISTS tray_timezone TEXT" in database


def test_schema_upgrades_are_ensured_before_heartbeat_and_timelog_requests():
    server = Path("server/__init__.py").read_text(encoding="utf-8")
    frontend = Path("frontend/src/TimeLogApp.jsx").read_text(encoding="utf-8")

    assert "async def _ensure_schema(self)" in server
    assert "self._schema_lock = asyncio.Lock()" in server
    assert server.count("await self._ensure_schema()") >= 5
    assert "Unable to load Presence TimeLog" in frontend
    assert "requestErrorMessage" in frontend
    assert ">Retry</button>" in frontend
