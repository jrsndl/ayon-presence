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


def test_normalizes_native_ayon_folder_path():
    context = task_tracking.normalize_ayon_task_context(
        {
            "project_name": "Demo",
            "folder_path": "assets/CharacterA",
            "task_name": "Model",
        }
    )
    assert context["folder_path"] == "/assets/CharacterA"


def test_rejects_incomplete_ayon_context():
    with pytest.raises(ValueError):
        task_tracking.normalize_ayon_task_context(
            {"project_name": "Demo", "task_name": "Comp"}
        )


def test_rejects_non_dictionary_context():
    with pytest.raises(TypeError):
        task_tracking.normalize_ayon_task_context(None)
