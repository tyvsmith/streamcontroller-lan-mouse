# AGENTS.md

Guidance for AI coding agents working on this repository.

## Project Overview

StreamController plugin (`me_tysmith_LanMouse`) that controls [lan-mouse](https://github.com/feschber/lan-mouse) (a software KVM) from an Elgato Stream Deck. Built for [StreamController](https://github.com/StreamController/StreamController) which runs as a Flatpak.

## Architecture

```
main.py                 # PluginBase — registers actions, plugin-level settings UI
lan_mouse.py            # Shared CLI helper — process management, client parsing
actions/
  LanMouseLaunch/       # Start/stop the lan-mouse daemon
  LanMouseToggle/       # Activate/deactivate a specific client connection
locales/en_US.json      # All user-facing strings (locale keys)
manifest.json           # StreamController plugin metadata (id, version, author, app-version)
assets/lan-mouse.png    # 72x72 action icon
store/Thumbnail.png     # 256x256 store thumbnail
pyproject.toml          # Project metadata, dev dependencies (uv), ruff and pyright config
uv.lock                 # Locked dependency versions — always commit this
```

## Key Constraints

- **Flatpak sandbox**: All subprocess calls to the host must use `flatpak-spawn --host`. The `_host_cmd()` helper in `lan_mouse.py` handles this automatically. Never call host binaries directly.
- **StreamController imports**: `src.backend.*` and `GtkHelper.*` imports only resolve inside the StreamController Flatpak runtime. LSP errors on these are expected and unavoidable during local development.
- **GTK4/Adwaita**: UI uses `gi.repository.Adw` and `gi.repository.Gtk` (version 4.0). These come from the Flatpak runtime, not pip.
- **`__pycache__` must be cleared** after code changes for StreamController to pick them up on restart. The plugin is symlinked from `~/.var/app/com.core447.StreamController/data/plugins/me_tysmith_LanMouse`.
- **`set_media()` is overridden by user custom assets** — if a user sets an icon via the sidebar icon selector, all `set_media()` calls are silently ignored.

## Plugin API Patterns

- **Plugin-level settings**: Override `get_settings_area()` on PluginBase, return `Adw.PreferencesGroup`. Uses `self.get_settings()`/`self.set_settings()` on PluginBase.
- **Per-action settings**: Override `get_config_rows()` on ActionBase, return list of `Adw.PreferencesRow`. Uses `self.get_settings()`/`self.set_settings()` on the action instance.
- **Events**: Override `event_callback(self, event, data)`. Use `Input.Key.Events.SHORT_UP` for short press and `Input.Key.Events.HOLD_START` for long press. These are mutually exclusive.
- **Color pickers**: `from GtkHelper.GenerativeUI.ColorButtonRow import ColorButtonRow` — auto-persists to action settings. RGBA tuples use 0-255 range.
- **`Adw.EntryRow`** does not support subtitles — title doubles as placeholder.

## Development

Uses [uv](https://docs.astral.sh/uv/) for dependency management. Dev dependencies and tool config are in `pyproject.toml`.

```bash
# Install dev dependencies and activate venv (direnv does this automatically)
uv sync
source .venv/bin/activate

# Type check (strict mode on lan_mouse.py only)
uv run pyright

# Lint
uv run ruff check .
uv run ruff format --check .

# Test
uv run pytest tests/ -v

# Clear cache after changes
find . -type d -name __pycache__ -exec rm -rf {} +
```

## Type System

- `lan_mouse.py` is checked with **pyright strict** mode — all functions are fully annotated
- `Client` TypedDict defines the shape returned by `list_clients()` and `get_client()`
- `main.py` and `actions/` are excluded from type checking (depend on Flatpak-only imports)
- `tests/` are excluded from pyright (mock parameters don't type well) — validated by pytest + ruff instead

## Locale Strings

All user-facing text must go through locale keys in `locales/en_US.json`, accessed via `self.plugin_base.lm.get("key.name")`. Add new keys there before referencing them in code.

## lan-mouse CLI

The plugin interacts with lan-mouse via its CLI:
- `lan-mouse cli list` — lists clients (parsed by regex in `lan_mouse.py`)
- `lan-mouse cli activate <id>` / `deactivate <id>` — toggle client connections
- `pgrep -x lan-mouse` — process detection
- `pkill -x lan-mouse` — process termination

Output format: `id 0: 192.168.10.54:4242 (left) active: true, ips: {192.168.10.54}`

## Versioning

- **Two places**: `manifest.json` `"version"` field (StreamController) and `pyproject.toml` `version` field — keep them in sync
- `main.py` reads version from `manifest.json` at import time — never hardcode it
- To release: bump `version` in both `manifest.json` and `pyproject.toml` (and `app-version` in `manifest.json` if needed), commit, push, then PR the commit hash to [StreamController-Store](https://github.com/StreamController/StreamController-Store) `Plugins.json`

## Design Decisions

- Client ID `-1` means auto-detect: picks the **first client** in the list (not "require exactly one")
- Short press toggles state; long press (`HOLD_START`) always kills the process
- When toggling and lan-mouse isn't running, auto-start it AND activate the client after ready
- `kill()` polls up to 2s for process exit to avoid race conditions
- Launch prefers `uwsm-app -- lan-mouse` if available, falls back to bare `lan-mouse`
