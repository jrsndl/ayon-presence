from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace

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


def test_normalizes_optional_dcc_and_workfile_context():
    context = task_tracking.normalize_ayon_task_context(
        {
            "project_name": "Demo",
            "folder_path": "/shots/010",
            "task_name": "Comp",
            "dcc_name": "NukeX",
            "dcc_version": "15.2.1",
            "workfile_name": "sh010_comp_v012.nk",
        }
    )
    assert context["dcc_name"] == "NukeX"
    assert context["dcc_version"] == "15.2.1"
    assert context["workfile_name"] == "sh010_comp_v012.nk"


def test_host_metadata_keeps_only_workfile_filename():
    host = SimpleNamespace(
        get_app_information=lambda: SimpleNamespace(
            app_name="Maya", app_version="2026"
        ),
        get_current_workfile=lambda: r"D:\projects\demo\model_v003.ma",
    )
    assert task_tracking.host_metadata(host) == {
        "dcc_name": "Maya",
        "dcc_version": "2026",
        "workfile_name": "model_v003.ma",
    }


def test_rejects_incomplete_ayon_context():
    with pytest.raises(ValueError):
        task_tracking.normalize_ayon_task_context(
            {"project_name": "Demo", "task_name": "Comp"}
        )


def test_rejects_non_dictionary_context():
    with pytest.raises(TypeError):
        task_tracking.normalize_ayon_task_context(None)
