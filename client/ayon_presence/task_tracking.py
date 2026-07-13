"""Native AYON task context helpers."""

from __future__ import annotations

import os
from typing import Any


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

    return {
        "project_name": project_name,
        "folder_path": folder_path,
        "task_name": task_name,
    }


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
