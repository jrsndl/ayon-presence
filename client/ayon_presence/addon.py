from __future__ import annotations

import platform

from ayon_core.addon import AYONAddon, ITrayAddon

from .activity import ActivityMonitor
from .reporter import PresenceReporter
from .task_tracking import normalize_task_context
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
        self.task_tracking_enabled = settings.get("task_tracking_enabled", True)
        self._reporter = None
        self._monitor = None
        self._timers_manager_addon = None
        self.timers_manager_connector = None

        if platform.system().lower() != "windows":
            self.log.warning(
                "Presence input monitoring currently supports Windows only"
            )
            self.enabled = False

    def tray_init(self):
        if not self.enabled:
            return
        self._reporter = PresenceReporter(self.heartbeat_seconds, self.log)
        if self.task_tracking_enabled:
            self.timers_manager_connector = self

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

    # AYON Timers Manager connector API. ftrack forwards its Timer events to
    # these methods through Timers Manager.
    def register_timers_manager(self, timers_manager_addon):
        self._timers_manager_addon = timers_manager_addon

    def start_timer(self, data):
        if self._reporter is None or not self.task_tracking_enabled:
            return
        try:
            context = normalize_task_context(data)
        except (TypeError, ValueError):
            self.log.warning("Unable to normalize timer task context", exc_info=True)
            return
        self._reporter.task_started(context)

    def stop_timer(self):
        if self._reporter is not None:
            self._reporter.task_stopped()
