"""Select the launched application's native AYON task in Presence."""

from ayon_applications import LaunchTypes, PostLaunchHook

from ayon_presence.task_tracking import notify_tray_task_selected


class PostSelectPresenceTaskHook(PostLaunchHook):
    """Notify the local Presence tray after an AYON application launch."""

    order = None
    launch_types = {LaunchTypes.local}

    def execute(self):
        context = {
            "project_name": self.data.get("project_name"),
            "folder_path": self.data.get("folder_path"),
            "task_name": self.data.get("task_name"),
        }
        if not all(context.values()):
            self.log.debug("Presence task hook skipped: incomplete AYON context")
            return
        notify_tray_task_selected(context, self.log)
