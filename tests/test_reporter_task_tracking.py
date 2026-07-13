from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys


sys.modules.setdefault("ayon_api", ModuleType("ayon_api"))
test_package = ModuleType("presence_test_pkg")
test_package.__path__ = [str(Path("client/ayon_presence"))]
sys.modules.setdefault("presence_test_pkg", test_package)
version_module = ModuleType("presence_test_pkg.version")
version_module.__version__ = "test"
sys.modules.setdefault("presence_test_pkg.version", version_module)
SPEC = spec_from_file_location(
    "presence_test_pkg.reporter", Path("client/ayon_presence/reporter.py")
)
reporter_module = module_from_spec(SPEC)
sys.modules[SPEC.name] = reporter_module
assert SPEC.loader is not None
SPEC.loader.exec_module(reporter_module)


CONTEXT = {
    "project_name": "Demo",
    "folder_path": "/shots/sq01/sh010",
    "task_name": "Compositing",
}


def _reporter(is_active=True):
    reporter = reporter_module.PresenceReporter(300, SimpleNamespace())
    reporter.attach_monitor(
        SimpleNamespace(
            is_active=is_active,
            idle_seconds=0,
            last_input_at=datetime.now(timezone.utc),
        )
    )
    events = []
    reporter._enqueue_task_event = lambda event_type, context: events.append(
        (event_type, context)
    )
    return reporter, events


def test_task_pauses_on_idle_and_resumes_on_activity():
    reporter, events = _reporter()

    reporter.task_selected(CONTEXT)
    reporter.activity_state_changed(False)
    reporter.activity_state_changed(True)

    assert [event_type for event_type, _context in events] == [
        "task_start",
        "task_stop",
        "task_start",
    ]
    assert all(
        context["task_name"] == "Compositing" for _event_type, context in events
    )
    assert "task_started_at" in events[0][1]
    assert "task_started_at" in events[2][1]


def test_task_selected_while_idle_starts_when_activity_returns():
    reporter, events = _reporter(is_active=False)

    reporter.task_selected(CONTEXT)
    reporter.activity_state_changed(True)

    assert [event_type for event_type, _context in events] == ["task_start"]


def test_switching_native_context_stops_previous_task_first():
    reporter, events = _reporter()
    reporter.task_selected(CONTEXT)

    reporter.task_selected({**CONTEXT, "task_name": "Lighting"})

    assert [event_type for event_type, _context in events] == [
        "task_start",
        "task_stop",
        "task_start",
    ]
    assert events[1][1]["task_name"] == "Compositing"
    assert events[2][1]["task_name"] == "Lighting"
