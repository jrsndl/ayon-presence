"""Privacy-preserving local input activity monitor."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional


class ActivityMonitor:
    """Track only the time of the last keyboard or mouse input."""

    def __init__(
        self,
        idle_threshold_seconds: int,
        on_state_change: Callable[[bool, int, datetime], None],
    ) -> None:
        self.idle_threshold_seconds = idle_threshold_seconds
        self._on_state_change = on_state_change
        self._last_input_monotonic = time.monotonic()
        self._last_input_at = datetime.now(timezone.utc)
        self._active = True
        self._running = False
        self._lock = threading.Lock()
        self._watcher: Optional[threading.Thread] = None
        self._mouse_listener = None
        self._keyboard_listener = None

    @property
    def idle_seconds(self) -> int:
        with self._lock:
            return max(0, int(time.monotonic() - self._last_input_monotonic))

    @property
    def last_input_at(self) -> datetime:
        with self._lock:
            return self._last_input_at

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def start(self) -> None:
        from pynput import keyboard, mouse

        if self._running:
            return
        self._running = True
        self._mouse_listener = mouse.Listener(
            on_move=self._record_input,
            on_click=self._record_input,
            on_scroll=self._record_input,
        )
        self._keyboard_listener = keyboard.Listener(on_press=self._record_input)
        self._mouse_listener.start()
        self._keyboard_listener.start()
        self._watcher = threading.Thread(
            target=self._watch_idle_state,
            name="AYONPresenceIdleWatcher",
            daemon=True,
        )
        self._watcher.start()

    def stop(self) -> None:
        self._running = False
        for listener in (self._mouse_listener, self._keyboard_listener):
            if listener is not None:
                listener.stop()
        if self._watcher is not None:
            self._watcher.join(timeout=2)

    def _record_input(self, *_args, **_kwargs) -> None:
        notify = False
        now = datetime.now(timezone.utc)
        with self._lock:
            self._last_input_monotonic = time.monotonic()
            self._last_input_at = now
            if not self._active:
                self._active = True
                notify = True
        if notify:
            self._on_state_change(True, 0, now)

    def _watch_idle_state(self) -> None:
        while self._running:
            idle_seconds = self.idle_seconds
            notify = False
            last_input = self.last_input_at
            with self._lock:
                if self._active and idle_seconds >= self.idle_threshold_seconds:
                    self._active = False
                    notify = True
            if notify:
                self._on_state_change(False, idle_seconds, last_input)
            time.sleep(1)
