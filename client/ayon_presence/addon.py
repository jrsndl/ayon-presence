from __future__ import annotations

import os
import platform

from ayon_core.addon import AYONAddon, ITrayAddon
from ayon_core.lib.events import register_event_callback

from .activity import ActivityMonitor
from .reporter import PresenceReporter
from .task_tracking import (
    host_metadata,
    normalize_ayon_task_context,
    notify_tray_task_cleared,
    notify_tray_task_selected,
    workfile_name_from_path,
)
from .version import __version__


ADDON_DIR = os.path.dirname(os.path.abspath(__file__))


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
        self._host = None

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
            if self.task_tracking_enabled:
                self._reporter.activity_state_changed(is_active)

        self._monitor = ActivityMonitor(self.idle_threshold_seconds, on_state_change)
        self._reporter.attach_monitor(self._monitor)

    def tray_menu(self, tray_menu):
        """Presence runs silently and does not add a tray menu action."""
        del tray_menu

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

    def get_launch_hook_paths(self):
        """Expose the native AYON application post-launch task hook."""
        if not self.enabled or not self.task_tracking_enabled:
            return []
        return [os.path.join(ADDON_DIR, "launch_hooks")]

    def on_host_install(self, host, host_name, project_name):
        """Follow native AYON task changes inside a running host."""
        if self.enabled and self.task_tracking_enabled:
            self._host = host
            register_event_callback("taskChanged", self._on_host_task_change)
            register_event_callback("workfile.open.after", self._on_workfile_change)
            register_event_callback("workfile.save.after", self._on_workfile_change)
            self._report_current_host_context(project_name)

    def _on_host_task_change(self, event):
        try:
            context = dict(getattr(event, "data", event))
            if self._host is not None:
                context.update(host_metadata(self._host))
            notify_tray_task_selected(context, self.log)
        except (TypeError, ValueError):
            notify_tray_task_cleared(self.log)

    def _on_workfile_change(self, event):
        event_data = getattr(event, "data", event)
        metadata = {}
        if isinstance(event_data, dict) and event_data.get("filepath"):
            metadata["workfile_name"] = workfile_name_from_path(
                event_data["filepath"]
            )
        self._report_current_host_context(metadata=metadata)

    def _report_current_host_context(self, project_name=None, metadata=None):
        host = self._host
        if host is None:
            return
        try:
            context = {
                "project_name": project_name or host.get_current_project_name(),
                "folder_path": host.get_current_folder_path(),
                "task_name": host.get_current_task_name(),
            }
            context.update(host_metadata(host))
            context.update(metadata or {})
            notify_tray_task_selected(context, self.log)
        except Exception:
            self.log.debug("Presence host context is not available yet", exc_info=True)

    def webserver_initialization(self, server_manager):
        """Register local-only endpoints used by AYON launch/host processes."""
        if not self.enabled or not self.task_tracking_enabled:
            return
        server_manager.add_addon_route(
            self.name, "task/start", "POST", self._start_task_request
        )
        server_manager.add_addon_route(
            self.name, "task/stop", "POST", self._stop_task_request
        )

    async def _start_task_request(self, request):
        from aiohttp import web

        try:
            context = normalize_ayon_task_context(await request.json())
        except (TypeError, ValueError):
            return web.json_response(
                {"success": False, "reason": "invalid_ayon_context"}, status=400
            )
        if self._reporter is None:
            return web.json_response(
                {"success": False, "reason": "tray_not_ready"}, status=503
            )
        self._reporter.task_selected(context)
        return web.json_response({"success": True})

    async def _stop_task_request(self, _request):
        from aiohttp import web

        if self._reporter is not None:
            self._reporter.task_cleared()
        return web.json_response({"success": True})
