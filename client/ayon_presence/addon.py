from __future__ import annotations

import platform

from ayon_core.addon import AYONAddon, ITrayAddon

from .activity import ActivityMonitor
from .reporter import PresenceReporter
from .version import __version__


class PresenceAddon(AYONAddon, ITrayAddon):
    name = "presence"
    label = "Presence"
    version = __version__

    def initialize(self, studio_settings):
        settings = studio_settings.get(self.name, {})
        self.enabled = settings.get("enabled", True)
        self.heartbeat_seconds = settings.get("heartbeat_interval_seconds", 300)
        self.idle_threshold_seconds = settings.get("active_idle_threshold_seconds", 300)
        self._reporter = None
        self._monitor = None

        if platform.system().lower() != "windows":
            self.log.warning(
                "Presence input monitoring currently supports Windows only"
            )
            self.enabled = False

    def tray_init(self):
        if not self.enabled:
            return
        self._reporter = PresenceReporter(self.heartbeat_seconds, self.log)

        def on_state_change(is_active, idle_seconds, last_input_at):
            event_type = "active" if is_active else "idle"
            self._reporter.enqueue(event_type, idle_seconds, last_input_at)

        self._monitor = ActivityMonitor(self.idle_threshold_seconds, on_state_change)
        self._reporter.attach_monitor(self._monitor)

    def tray_start(self):
        if self._monitor is None or self._reporter is None:
            return
        self._monitor.start()
        self._reporter.start()

    def tray_exit(self, *_args, **_kwargs):
        if self._reporter is not None:
            self._reporter.stop()
        if self._monitor is not None:
            self._monitor.stop()
