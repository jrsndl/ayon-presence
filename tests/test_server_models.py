from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pydantic
import pytest


def load_module(name: str, path: str):
    spec = spec_from_file_location(name, Path(path))
    module = module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_event_model_is_compatible_with_ayon_pydantic():
    models = load_module("presence_models", "server/models.py")
    event = models.PresenceEvent(
        event_type="heartbeat",
        session_id="session-1",
        machine_name="WS-01",
    )
    assert '"event_type": "heartbeat"' in event.json()
    assert pydantic.VERSION.startswith("1.")


def test_settings_validate_run_time_and_timezone(monkeypatch):
    settings_module = ModuleType("ayon_server.settings")
    settings_module.BaseSettingsModel = pydantic.BaseModel
    settings_module.SettingsField = pydantic.Field
    ayon_server = ModuleType("ayon_server")
    ayon_server.settings = settings_module
    monkeypatch.setitem(sys.modules, "ayon_server", ayon_server)
    monkeypatch.setitem(sys.modules, "ayon_server.settings", settings_module)
    settings = load_module("presence_settings", "server/settings.py")

    assert settings.PresenceSettings().daily_summary_run_time == "04:00"
    with pytest.raises(pydantic.ValidationError):
        settings.PresenceSettings(daily_summary_run_time="25:00")
    with pytest.raises(pydantic.ValidationError):
        settings.PresenceSettings(timezone="Not/A-Timezone")
