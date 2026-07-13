from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


SPEC = spec_from_file_location(
    "presence_task_tracking", Path("client/ayon_presence/task_tracking.py")
)
task_tracking = module_from_spec(SPEC)
sys.modules[SPEC.name] = task_tracking
assert SPEC.loader is not None
SPEC.loader.exec_module(task_tracking)


def test_normalizes_ftrack_timer_payload():
    context = task_tracking.normalize_task_context(
        {
            "project_name": "Demo",
            "hierarchy": ["shots", "sq01", "sh010"],
            "task_name": "Compositing",
            "task_type": "Comp",
        }
    )
    assert context == {
        "project_name": "Demo",
        "folder_path": "/shots/sq01/sh010",
        "task_name": "Compositing",
    }


def test_preserves_native_ayon_folder_path():
    context = task_tracking.normalize_task_context(
        {
            "project_name": "Demo",
            "folder_path": "assets/CharacterA",
            "task_name": "Model",
        }
    )
    assert context["folder_path"] == "/assets/CharacterA"


def test_rejects_incomplete_timer_payload():
    with pytest.raises(ValueError):
        task_tracking.normalize_task_context(
            {"project_name": "Demo", "task_name": "Comp"}
        )
