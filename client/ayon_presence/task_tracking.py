"""Native AYON task context helpers."""

from __future__ import annotations

import os
from typing import Any


OPTIONAL_CONTEXT_KEYS = ("dcc_name", "dcc_version", "workfile_name")
DCC_DISPLAY_NAMES = {"resolve": "DaVinci Resolve"}


def workfile_name_from_path(path: Any) -> str:
    """Return a portable filename without exposing its absolute path."""
    return os.path.basename(str(path).replace("\\", "/"))


def launch_metadata(
    data: dict[str, Any], application: Any, host_name: Any
) -> dict[str, str]:
    """Collect configured DCC and intended workfile data at launch time."""
    result: dict[str, str] = {}
    group = getattr(application, "group", None)
    group_name = getattr(group, "name", None) or host_name
    dcc_name = getattr(group, "label", None) or group_name
    dcc_version = getattr(application, "label", None) or getattr(
        application, "name", None
    )
    if dcc_name:
        result["dcc_name"] = str(dcc_name)
    if dcc_version:
        result["dcc_version"] = str(dcc_version)

    workfile_path = data.get("workfile_path")
    if not workfile_path and data.get("start_last_workfile"):
        workfile_path = data.get("last_workfile_path")
    if workfile_path:
        result["workfile_name"] = workfile_name_from_path(workfile_path)
    return result


def normalize_ayon_task_context(data: dict[str, Any]) -> dict[str, str]:
    """Validate and normalize a native AYON project/folder/task context."""
    if not isinstance(data, dict):
        raise TypeError("Task context must be a dictionary")

    project_name = str(data.get("project_name") or "").strip()
    task_name = str(data.get("task_name") or "").strip()
    folder_path = str(data.get("folder_path") or "").strip()

    if folder_path and not folder_path.startswith("/"):
        folder_path = f"/{folder_path}"
    folder_path = folder_path.rstrip("/") or "/"

    if not project_name or not task_name or folder_path == "/":
        raise ValueError("AYON context must contain project, folder and task")

    context = {
        "project_name": project_name,
        "folder_path": folder_path,
        "task_name": task_name,
    }
    for key in OPTIONAL_CONTEXT_KEYS:
        value = str(data.get(key) or "").strip()
        if value:
            context[key] = value
    return context


def host_metadata(host: Any) -> dict[str, str]:
    """Collect portable application metadata without exposing full paths."""
    result: dict[str, str] = {}
    app_name = None
    app_version = None
    try:
        app_info = host.get_app_information()
        app_name = app_info.app_name
        app_version = app_info.app_version
    except Exception:
        pass

    configured_app = os.environ.get("AYON_APP_NAME", "")
    configured_group, separator, configured_variant = configured_app.partition("/")
    fallback_name = getattr(host, "name", None) or configured_group
    if fallback_name:
        fallback_name = DCC_DISPLAY_NAMES.get(fallback_name, fallback_name)
    app_name = app_name or fallback_name
    app_version = app_version or (configured_variant if separator else None)
    if app_name:
        result["dcc_name"] = str(app_name)
    if app_version:
        result["dcc_version"] = str(app_version)

    if hasattr(host, "get_current_workfile"):
        try:
            workfile_path = host.get_current_workfile()
        except Exception:
            workfile_path = None
        if workfile_path:
            result["workfile_name"] = workfile_name_from_path(workfile_path)
    return result


def notify_tray_task_selected(data: dict[str, Any], logger: Any = None) -> None:
    """Send an AYON context from a launch/host process to the local tray."""
    context = normalize_ayon_task_context(data)
    _post_to_tray("task/start", context, logger)


def notify_tray_task_cleared(logger: Any = None) -> None:
    """Clear the selected task in the local Presence tray addon."""
    _post_to_tray("task/stop", None, logger)


def _post_to_tray(path: str, data: Any, logger: Any) -> None:
    webserver_url = os.environ.get("AYON_WEBSERVER_URL")
    if not webserver_url:
        _log_warning(logger, "Cannot update Presence task: AYON tray URL is missing")
        return

    try:
        import requests

        response = requests.post(
            f"{webserver_url}/addons/presence/{path}",
            json=data,
            timeout=5,
        )
        response.raise_for_status()
    except Exception:
        if logger is not None:
            logger.warning("Cannot update Presence task context", exc_info=True)
        else:
            raise


def _log_warning(logger: Any, message: str) -> None:
    if logger is not None:
        logger.warning(message)
    else:
        print(message)
