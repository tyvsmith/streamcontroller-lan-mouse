"""StreamController action to toggle a lan-mouse client connection and show its status."""

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
DEFAULT_COLOR_OFF = (0, 0, 0, 0)  # transparent — lan-mouse not running
DEFAULT_COLOR_INACTIVE = (40, 36, 27, 255)  # orange — client deactivated
DEFAULT_COLOR_ACTIVE = (39, 42, 39, 255)  # green — client activated

# Icon tint colors (applied to the white icon shape)
ICON_COLOR_INACTIVE = (227, 193, 101, 255)  # golden — client deactivated
ICON_COLOR_ACTIVE = (159, 210, 167, 255)  # mint — client activated

# Sentinel for "auto-detect the only client"
AUTO_DETECT = -1


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


class LanMouseToggle(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = True
        self._prev_state = None  # None | "off" | "inactive" | "active"
        self._last_check: float = 0.0
        self._icon_cache: dict[tuple[str, tuple[int, int, int, int]], str] = {}

        self.color_active = ColorButtonRow(
            action_core=self,
            var_name="color_active",
            default_value=DEFAULT_COLOR_ACTIVE,
            title=self.plugin_base.lm.get("color.active.title"),
            on_change=self._on_color_changed,
        )
        self.color_icon_active = ColorButtonRow(
            action_core=self,
            var_name="color_icon_active",
            default_value=ICON_COLOR_ACTIVE,
            title=self.plugin_base.lm.get("color.icon-active.title"),
            on_change=self._on_color_changed,
        )
        self.color_inactive = ColorButtonRow(
            action_core=self,
            var_name="color_inactive",
            default_value=DEFAULT_COLOR_INACTIVE,
            title=self.plugin_base.lm.get("color.inactive.title"),
            on_change=self._on_color_changed,
        )
        self.color_icon_inactive = ColorButtonRow(
            action_core=self,
            var_name="color_icon_inactive",
            default_value=ICON_COLOR_INACTIVE,
            title=self.plugin_base.lm.get("color.icon-inactive.title"),
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
        self._prev_state = None
        self._update_status()

    def _bp(self) -> str:
        return self.plugin_base.get_bin_path()

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

    def _get_show_hostname(self) -> bool:
        return self.get_settings().get("show_hostname", True)

    def on_ready(self):
        self._update_status()

    def on_tick(self):
        now = time.monotonic()
        if now - self._last_check < 2.0:
            return
        self._last_check = now
        self._update_status()

    def _configured_client_id(self) -> int:
        """Return the raw configured client ID setting (-1 for auto-detect)."""
        return int(self.get_settings().get("client_id", AUTO_DETECT))

    def _resolve_client_id(self, clients: list) -> int:
        """Resolve the client ID from a pre-fetched client list.

        Returns the configured ID, or the first client's ID for auto-detect.
        Returns AUTO_DETECT if auto-detect is set but the list is empty.
        """
        cid = self._configured_client_id()
        if cid == AUTO_DETECT and clients:
            return clients[0]["id"]
        return cid

    def _find_client(self, client_id: int, clients: list) -> dict | None:
        """Find a client by ID in a pre-fetched client list."""
        for client in clients:
            if client["id"] == client_id:
                return client
        return None

    def _get_auto_start(self) -> bool:
        return self.get_settings().get("auto_start", True)

    def _get_label(self, client: dict | None, fallback: str) -> str:
        if not self._get_show_hostname():
            return ""
        if client:
            return client["host"]
        return fallback

    def _update_status(self):
        # Single subprocess call to get running state + all clients
        status = lan_mouse.get_status(self._bp())
        clients = status["clients"]

        if not status["running"]:
            state = "off"
            client = None
        else:
            cid = self._resolve_client_id(clients)
            if cid == AUTO_DETECT:
                state = "off"
                client = None
            else:
                client = self._find_client(cid, clients)
                if client is None:
                    state = "off"
                elif client["active"]:
                    state = "active"
                else:
                    state = "inactive"

        if state == self._prev_state:
            return
        self._prev_state = state

        lm = self.plugin_base.lm
        if state == "active":
            self.set_background_color(list(self.color_active.get_value()))
            self.set_media(
                media_path=self._get_tinted_icon(
                    tuple(self.color_icon_active.get_value())
                ),
                size=0.8,
            )
            self.set_bottom_label(
                self._get_label(client, lm.get("status.active")), font_size=10
            )
        elif state == "inactive":
            self.set_background_color(list(self.color_inactive.get_value()))
            self.set_media(
                media_path=self._get_tinted_icon(
                    tuple(self.color_icon_inactive.get_value())
                ),
                size=0.8,
            )
            self.set_bottom_label(
                self._get_label(client, lm.get("status.inactive")), font_size=10
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
                self._get_label(None, lm.get("status.off")), font_size=10
            )

    def event_callback(self, event, data):
        if event == Input.Key.Events.SHORT_UP:
            self._handle_toggle()
        elif event == Input.Key.Events.HOLD_START:
            lan_mouse.kill(self._bp())
            self._prev_state = None
            self._update_status()

    def _try_launch(self):
        """Attempt to launch lan-mouse and activate the client."""
        if not self._get_auto_start():
            self.show_error(duration=2)
            return

        cmd = self.plugin_base.get_launch_command()
        bp = self._bp()
        lan_mouse.launch(cmd, bp)

        if lan_mouse.wait_for_ready(bp):
            status = lan_mouse.get_status(bp)
            cid = self._resolve_client_id(status["clients"])
            if cid != AUTO_DETECT:
                lan_mouse.activate(cid, bp)

        self._prev_state = None
        self._update_status()

    def _handle_toggle(self):
        bp = self._bp()
        status = lan_mouse.get_status(bp)

        if not status["running"]:
            self._try_launch()
            return

        clients = status["clients"]
        cid = self._resolve_client_id(clients)
        if cid == AUTO_DETECT:
            self._try_launch()
            return

        client = self._find_client(cid, clients)
        if client is None:
            self._try_launch()
            return

        if client["active"]:
            lan_mouse.deactivate(cid, bp)
        else:
            lan_mouse.activate(cid, bp)

        self._prev_state = None
        self._update_status()

    # --- Configuration UI ---

    def get_config_rows(self):
        self.client_id_row = Adw.SpinRow.new_with_range(-1, 100, 1)
        self.client_id_row.set_title(self.plugin_base.lm.get("toggle.client-id.title"))
        self.client_id_row.set_subtitle(
            self.plugin_base.lm.get("toggle.client-id.subtitle")
        )

        self.auto_start_row = Adw.SwitchRow(
            title=self.plugin_base.lm.get("toggle.auto-start.title"),
            subtitle=self.plugin_base.lm.get("toggle.auto-start.subtitle"),
        )

        self.icon_path_row = Adw.EntryRow(
            title=self.plugin_base.lm.get("action.icon-path.title"),
        )

        self.show_hostname_row = Adw.SwitchRow(
            title=self.plugin_base.lm.get("toggle.show-hostname.title"),
            subtitle=self.plugin_base.lm.get("toggle.show-hostname.subtitle"),
        )

        # Load current settings
        settings = self.get_settings()
        self.client_id_row.set_value(settings.get("client_id", AUTO_DETECT))
        self.auto_start_row.set_active(settings.get("auto_start", True))
        self.icon_path_row.set_text(settings.get("icon_path", ""))
        self.show_hostname_row.set_active(settings.get("show_hostname", True))

        # Connect signals
        self.client_id_row.connect("changed", self._on_client_id_changed)
        self.auto_start_row.connect("notify::active", self._on_auto_start_changed)
        self.icon_path_row.connect("notify::text", self._on_icon_path_changed)
        self.show_hostname_row.connect("notify::active", self._on_show_hostname_changed)

        return [
            self.client_id_row,
            self.auto_start_row,
            self.icon_path_row,
            self.show_hostname_row,
            self.color_active.widget,
            self.color_icon_active.widget,
            self.color_inactive.widget,
            self.color_icon_inactive.widget,
            self.color_off.widget,
            self.color_icon_off.widget,
        ]

    def _on_client_id_changed(self, spin):
        settings = self.get_settings()
        settings["client_id"] = int(spin.get_value())
        self.set_settings(settings)
        self._prev_state = None

    def _on_auto_start_changed(self, switch, _):
        settings = self.get_settings()
        settings["auto_start"] = switch.get_active()
        self.set_settings(settings)

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
        self._prev_state = None
        self._update_status()

    def _on_show_hostname_changed(self, switch, _):
        settings = self.get_settings()
        settings["show_hostname"] = switch.get_active()
        self.set_settings(settings)
        self._prev_state = None
        self._update_status()
