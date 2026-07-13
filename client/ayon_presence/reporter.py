"""Background delivery of presence events to AYON Server."""

from __future__ import annotations

import platform
import queue
import socket
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import ayon_api

from .version import __version__


class PresenceReporter:
    def __init__(self, heartbeat_seconds: int, log: Any) -> None:
        self.heartbeat_seconds = heartbeat_seconds
        self.log = log
        self.session_id = str(uuid.uuid4())
        self.machine_name = socket.gethostname()
        self._queue: queue.Queue[Optional[dict[str, Any]]] = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._monitor = None
        self._task_lock = threading.Lock()
        self._current_task: Optional[dict[str, str]] = None

    def attach_monitor(self, monitor: Any) -> None:
        self._monitor = monitor

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="AYONPresenceReporter", daemon=True
        )
        self._thread.start()
        self.enqueue("session_start", 0, datetime.now(timezone.utc))

    def stop(self) -> None:
        self.enqueue_current("session_end")
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._stop.set()

    def enqueue_current(self, event_type: str) -> None:
        monitor = self._monitor
        if monitor is None:
            return
        self.enqueue(event_type, monitor.idle_seconds, monitor.last_input_at)

    def task_started(self, context: dict[str, str]) -> None:
        with self._task_lock:
            if self._current_task and all(
                self._current_task.get(key) == value for key, value in context.items()
            ):
                return
            stored_context = dict(context)
            stored_context["task_started_at"] = datetime.now(timezone.utc).isoformat()
            self._current_task = stored_context
        self._enqueue_task_event("task_start", stored_context)

    def task_stopped(self) -> None:
        with self._task_lock:
            context = self._current_task
            self._current_task = None
        if context is not None:
            self._enqueue_task_event("task_stop", context)

    def _enqueue_task_heartbeat(self) -> None:
        with self._task_lock:
            context = self._current_task
        if context is not None:
            self._enqueue_task_event("task_heartbeat", context)

    def _enqueue_task_event(self, event_type: str, context: dict[str, str]) -> None:
        monitor = self._monitor
        if monitor is None:
            return
        self.enqueue(
            event_type,
            monitor.idle_seconds,
            monitor.last_input_at,
            extra=context,
        )

    def enqueue(
        self,
        event_type: str,
        idle_seconds: int,
        last_input_at: datetime,
        extra: Optional[dict[str, str]] = None,
    ) -> None:
        payload = {
            "event_type": event_type,
            "session_id": self.session_id,
            "machine_name": self.machine_name,
            "platform": platform.system().lower(),
            "client_version": __version__,
            "client_time": datetime.now(timezone.utc).isoformat(),
            "last_input_at": last_input_at.isoformat(),
            "idle_seconds": max(0, idle_seconds),
        }
        if extra:
            payload.update(extra)
        self._queue.put(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        endpoint = f"addons/presence/{__version__}/events"
        response = ayon_api.post(endpoint, json=payload)
        response.raise_for_status()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self._queue.get(timeout=self.heartbeat_seconds)
            except queue.Empty:
                self.enqueue_current("heartbeat")
                self._enqueue_task_heartbeat()
                continue
            if payload is None:
                return
            try:
                self._send(payload)
            except Exception:
                self.log.warning("Unable to report AYON presence", exc_info=True)
