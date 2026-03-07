"""StreamController plugin for lan-mouse — software KVM control from your Stream Deck."""

import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase

from .actions.LanMouseLaunch.LanMouseLaunch import LanMouseLaunch
from .actions.LanMouseToggle.LanMouseToggle import LanMouseToggle


def _load_manifest() -> dict:
    """Load manifest.json from the plugin directory."""
    manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


_MANIFEST = _load_manifest()


class LanMouse(PluginBase):
    def __init__(self):
        super().__init__()

        self.lm = self.locale_manager
        self.lm.set_to_os_default()
        self.lm.set_fallback_language("en_US")

        # Action: Launch / kill the lan-mouse daemon
        self.launch_holder = ActionHolder(
            plugin_base=self,
            action_base=LanMouseLaunch,
            action_id_suffix="LanMouseLaunch",
            action_name=self.lm.get("actions.launch.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.UNTESTED,
                Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
            },
        )
        self.add_action_holder(self.launch_holder)

        # Action: Toggle a specific client connection
        self.toggle_holder = ActionHolder(
            plugin_base=self,
            action_base=LanMouseToggle,
            action_id_suffix="LanMouseToggle",
            action_name=self.lm.get("actions.toggle.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.UNTESTED,
                Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
            },
        )
        self.add_action_holder(self.toggle_holder)

        self.register(
            plugin_name=self.lm.get("plugin.name"),
            github_repo=_MANIFEST["github"],
            plugin_version=_MANIFEST["version"],
            app_version=_MANIFEST["app-version"],
        )

    # --- Plugin-level helpers for actions ---

    def get_launch_command(self) -> str:
        """Return the custom launch command, or empty string for auto-detect."""
        return self.get_settings().get("launch_command", "")

    def get_bin_path(self) -> str:
        """Return the custom lan-mouse binary path, or empty string for default."""
        return self.get_settings().get("bin_path", "")

    # --- Plugin Settings UI ---

    def get_settings_area(self):
        group = Adw.PreferencesGroup(
            title=self.lm.get("plugin.name"),
            description=self.lm.get("settings.description"),
        )

        self._launch_cmd_row = Adw.EntryRow(
            title=self.lm.get("settings.launch-command.title"),
        )
        self._bin_path_row = Adw.EntryRow(
            title=self.lm.get("settings.bin-path.title"),
        )

        # Load current settings
        settings = self.get_settings()
        self._launch_cmd_row.set_text(settings.get("launch_command", ""))
        self._bin_path_row.set_text(settings.get("bin_path", ""))

        # Connect signals
        self._launch_cmd_row.connect("notify::text", self._on_launch_cmd_changed)
        self._bin_path_row.connect("notify::text", self._on_bin_path_changed)

        group.add(self._launch_cmd_row)
        group.add(self._bin_path_row)

        return group

    def _on_launch_cmd_changed(self, entry, _):
        settings = self.get_settings()
        settings["launch_command"] = entry.get_text()
        self.set_settings(settings)

    def _on_bin_path_changed(self, entry, _):
        settings = self.get_settings()
        settings["bin_path"] = entry.get_text()
        self.set_settings(settings)
