"""Normalize AYON Timers Manager task payloads."""

from __future__ import annotations

from typing import Any


def normalize_task_context(data: dict[str, Any]) -> dict[str, str]:
    """Return a stable project/folder/task context.

    ftrack sends ``project_name``, ``hierarchy`` and ``task_name`` while native
    AYON timer starts generally include ``folder_path``. Supporting both shapes
    keeps Presence independent from the ftrack addon itself.
    """
    project_name = str(data.get("project_name") or "").strip()
    task_name = str(data.get("task_name") or "").strip()
    folder_path = str(data.get("folder_path") or "").strip()

    if not folder_path:
        hierarchy = data.get("hierarchy") or []
        folder_path = "/" + "/".join(
            str(item).strip().strip("/") for item in hierarchy if str(item).strip()
        )

    if folder_path and not folder_path.startswith("/"):
        folder_path = f"/{folder_path}"
    folder_path = folder_path.rstrip("/") or "/"

    if not project_name or not task_name or folder_path == "/":
        raise ValueError("Timer payload must contain project, folder and task")

    return {
        "project_name": project_name,
        "folder_path": folder_path,
        "task_name": task_name,
    }
