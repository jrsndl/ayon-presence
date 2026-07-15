from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


SPEC = spec_from_file_location(
    "presence_foreground", Path("client/ayon_presence/foreground.py")
)
foreground = module_from_spec(SPEC)
sys.modules[SPEC.name] = foreground
assert SPEC.loader is not None
SPEC.loader.exec_module(foreground)


def test_window_title_cleanup_and_length_limit():
    assert (
        foreground.clean_window_title("  Client\nReview\t—\x00 Chrome  ", 18)
        == "Client Review — Ch"
    )
    assert foreground.clean_window_title("\x00\n\t", 32) is None


def test_foreground_monitor_emits_only_changes(monkeypatch):
    samples = iter(
        [
            ("nuke.exe", "shot 010"),
            ("nuke.exe", "shot 010"),
            ("chrome.exe", "AYON"),
        ]
    )
    monkeypatch.setattr(foreground, "_foreground_window", lambda *_args: next(samples))
    changes = []
    monitor = foreground.ForegroundMonitor(True, True, 32, changes.append)
    monitor._on_change = lambda application, title: changes.append((application, title))

    monitor._poll_once()
    monitor._poll_once()
    monitor._poll_once()

    assert changes == [
        ("nuke.exe", "shot 010"),
        ("chrome.exe", "AYON"),
    ]
