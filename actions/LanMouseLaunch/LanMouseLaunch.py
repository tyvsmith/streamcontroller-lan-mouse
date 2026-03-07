"""StreamController action to launch/kill the lan-mouse daemon and show its status."""

import os
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from GtkHelper.GenerativeUI.ColorButtonRow import ColorButtonRow

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionBase import ActionBase

from ... import lan_mouse

# Default colors (RGBA 0-255)
DEFAULT_COLOR_OFF = (0, 0, 0, 0)  # transparent — not running
DEFAULT_COLOR_RUNNING = (39, 42, 39, 255)  # green — daemon running

# Icon tint color (applied to the white icon shape)
ICON_COLOR_RUNNING = (159, 210, 167, 255)  # mint — daemon running


def _tint_icon(base_path: str, color: tuple[int, int, int, int]) -> str | None:
    """Return path to a temp PNG of base_path tinted to the given RGB color.

    Returns None if Pillow is unavailable.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(base_path).convert("RGBA")
    r, g, b = color[0], color[1], color[2]
    tinted = Image.new("RGBA", img.size, (r, g, b, 255))
    _, _, _, alpha = img.split()
    tinted.putalpha(alpha)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tinted.save(tmp.name)
    return tmp.name


class LanMouseLaunch(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = True
        self._prev_running = None
        self._last_check: float = 0.0
        self._icon_cache: dict[tuple[str, tuple[int, int, int, int]], str] = {}

        self.color_running = ColorButtonRow(
            action_core=self,
            var_name="color_running",
            default_value=DEFAULT_COLOR_RUNNING,
            title=self.plugin_base.lm.get("color.running.title"),
            on_change=self._on_color_changed,
        )
        self.color_icon_running = ColorButtonRow(
            action_core=self,
            var_name="color_icon_running",
            default_value=ICON_COLOR_RUNNING,
            title=self.plugin_base.lm.get("color.icon-running.title"),
            on_change=self._on_color_changed,
        )
        self.color_off = ColorButtonRow(
            action_core=self,
            var_name="color_off",
            default_value=DEFAULT_COLOR_OFF,
            title=self.plugin_base.lm.get("color.off.title"),
            on_change=self._on_color_changed,
        )
        self.color_icon_off = ColorButtonRow(
            action_core=self,
            var_name="color_icon_off",
            default_value=(255, 255, 255, 255),
            title=self.plugin_base.lm.get("color.icon-off.title"),
            on_change=self._on_color_changed,
        )

    def _on_color_changed(self, widget, new_value, old_value):
        self._prev_running = None
        self._update_status()

    def _get_icon_path(self) -> str:
        custom = self.get_settings().get("icon_path", "")
        if custom and Path(custom).is_file():
            return custom
        return str(Path(self.plugin_base.PATH) / "assets" / "lan-mouse.png")

    def _get_tinted_icon(self, color: tuple[int, int, int, int]) -> str:
        """Return cached path to the icon tinted to color. Falls back to white if Pillow missing."""
        base = self._get_icon_path()
        key = (base, color)
        if key not in self._icon_cache:
            tinted = _tint_icon(base, color)
            self._icon_cache[key] = tinted if tinted is not None else base
        return self._icon_cache[key]

    def _get_show_label(self) -> bool:
        return self.get_settings().get("show_label", True)

    def on_ready(self):
        self._update_status()

    def on_tick(self):
        now = time.monotonic()
        if now - self._last_check < 2.0:
            return
        self._last_check = now
        self._update_status()

    def _update_status(self):
        bp = self.plugin_base.get_bin_path()
        status = lan_mouse.get_status(bp)
        running = status["running"]

        if running == self._prev_running:
            return
        self._prev_running = running

        if running:
            self.set_background_color(list(self.color_running.get_value()))
            self.set_media(
                media_path=self._get_tinted_icon(
                    tuple(self.color_icon_running.get_value())
                ),
                size=0.8,
            )
            self.set_bottom_label(
                self.plugin_base.lm.get("status.running")
                if self._get_show_label()
                else "",
                font_size=12,
            )
        else:
            self.set_background_color(list(self.color_off.get_value()))
            self.set_media(
                media_path=self._get_tinted_icon(
                    tuple(self.color_icon_off.get_value())
                ),
                size=0.8,
            )
            self.set_bottom_label(
                self.plugin_base.lm.get("status.off") if self._get_show_label() else "",
                font_size=12,
            )

    def event_callback(self, event, data):
        cmd = self.plugin_base.get_launch_command()
        bp = self.plugin_base.get_bin_path()

        if event == Input.Key.Events.SHORT_UP:
            if lan_mouse.is_running(bp):
                lan_mouse.kill(bp)
            else:
                lan_mouse.launch(cmd, bp)
            self._prev_running = None
            self._update_status()

        elif event == Input.Key.Events.HOLD_START:
            lan_mouse.kill(bp)
            self._prev_running = None
            self._update_status()

    # --- Configuration UI ---

    def get_config_rows(self):
        self.icon_path_row = Adw.EntryRow(
            title=self.plugin_base.lm.get("action.icon-path.title"),
        )
        self.show_label_row = Adw.SwitchRow(
            title=self.plugin_base.lm.get("action.show-label.title"),
            subtitle=self.plugin_base.lm.get("action.show-label.subtitle"),
        )

        settings = self.get_settings()
        self.icon_path_row.set_text(settings.get("icon_path", ""))
        self.show_label_row.set_active(settings.get("show_label", True))

        self.icon_path_row.connect("notify::text", self._on_icon_path_changed)
        self.show_label_row.connect("notify::active", self._on_show_label_changed)

        return [
            self.icon_path_row,
            self.show_label_row,
            self.color_running.widget,
            self.color_icon_running.widget,
            self.color_off.widget,
            self.color_icon_off.widget,
        ]

    def _on_icon_path_changed(self, entry, _):
        settings = self.get_settings()
        settings["icon_path"] = entry.get_text()
        self.set_settings(settings)
        for path in self._icon_cache.values():
            try:
                os.unlink(path)
            except OSError:
                pass
        self._icon_cache.clear()
        self._prev_running = None
        self._update_status()

    def _on_show_label_changed(self, switch, _):
        settings = self.get_settings()
        settings["show_label"] = switch.get_active()
        self.set_settings(settings)
        self._prev_running = None
        self._update_status()
