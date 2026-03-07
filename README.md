# Lan Mouse for StreamController

A [StreamController](https://github.com/StreamController/StreamController) plugin to control [lan-mouse](https://github.com/feschber/lan-mouse) (a software KVM for sharing mouse and keyboard between machines) from your Elgato Stream Deck.

## Features

**Lan Mouse Launch** — Start and stop the lan-mouse daemon
- Short press toggles the daemon on/off
- Long press always kills the daemon
- Live status indicator with configurable colors

**Lan Mouse Toggle** — Activate/deactivate a specific client connection
- Short press toggles the client connection
- Long press kills the daemon
- Auto-starts lan-mouse if not running (configurable)
- Auto-detects the first client when client ID is set to `-1`
- Displays client hostname/IP on the button

## Requirements

- [StreamController](https://github.com/StreamController/StreamController) (Flatpak or alternative install)
- [lan-mouse](https://github.com/feschber/lan-mouse) installed on the host system

## Installation

### From the StreamController Store

Search for "Lan Mouse" in the StreamController plugin store.

### Manual Installation

Clone this repo into the StreamController plugins directory:

```bash
git clone https://github.com/tyvsmith/streamcontroller-lan-mouse.git
ln -s "$(pwd)/streamcontroller-lan-mouse" \
  ~/.var/app/com.core447.StreamController/data/plugins/me_tysmith_LanMouse
```

Restart StreamController.

## Configuration

### Plugin Settings

Go to **Settings > Plugins > Lan Mouse** to configure:

| Setting | Description | Default |
|---|---|---|
| **Launch Command** | Custom command to start lan-mouse (e.g., `uwsm-app -- lan-mouse`) | Auto-detect |
| **Lan Mouse Path** | Path to the lan-mouse binary | `lan-mouse` (from PATH) |

The plugin auto-detects the best launch method: it prefers `uwsm-app -- lan-mouse` (for systemd session integration) if available, otherwise falls back to the bare `lan-mouse` binary.

### Per-Action Settings

Each action can be configured with:

| Setting | Description |
|---|---|
| **Custom Icon Path** | Path to a custom icon (overrides the default) |
| **Show Status Label** | Show running/off text on the Launch button |
| **Running / Off / Active / Inactive Color** | Background color for each state |

The Toggle action additionally supports:

| Setting | Description | Default |
|---|---|---|
| **Client ID** | lan-mouse client ID to control (`-1` = auto-detect first client) | `-1` |
| **Auto-start lan-mouse** | Automatically start the daemon when toggling if it's not running | On |
| **Show Hostname** | Display the client hostname/IP on the button | On |

## Development

The plugin runs inside the StreamController Flatpak sandbox. All subprocess calls to the host go through `flatpak-spawn --host` (handled automatically by `lan_mouse.py`).

### Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/tyvsmith/streamcontroller-lan-mouse.git
cd streamcontroller-lan-mouse

# Install dev dependencies (creates .venv automatically)
uv sync

# Symlink into StreamController plugins
ln -s "$(pwd)" \
  ~/.var/app/com.core447.StreamController/data/plugins/me_tysmith_LanMouse
```

If you use [direnv](https://direnv.net/), `direnv allow` will run `uv sync` and activate the venv automatically on `cd`.

### Checks

```bash
uv run ruff check .        # Lint
uv run ruff format --check # Format check
uv run pyright             # Type check (strict on lan_mouse.py)
uv run pytest tests/ -v    # Unit tests
```

### Testing in StreamController

After editing code, clear the Python cache and restart StreamController:

```bash
find . -type d -name __pycache__ -exec rm -rf {} +
# Then restart StreamController
```

### Releasing

Version is defined in both `manifest.json` and `pyproject.toml` — keep them in sync.

1. Bump `version` in `manifest.json` and `pyproject.toml` (and `app-version` in `manifest.json` if targeting a new StreamController release)
2. Commit and push to GitHub
3. Submit a PR to [StreamController-Store](https://github.com/StreamController/StreamController-Store) adding your commit hash to `Plugins.json`

### Project Structure

```
main.py                 # PluginBase — action registration, plugin-level settings
lan_mouse.py            # Shared CLI helper — process management, client parsing
actions/
  LanMouseLaunch/       # Start/stop daemon action
  LanMouseToggle/       # Per-client toggle action
locales/en_US.json      # All user-facing strings
manifest.json           # StreamController plugin metadata
assets/lan-mouse.png    # 72x72 action icon
store/Thumbnail.png     # 256x256 store thumbnail
tests/                  # Unit tests for lan_mouse.py
pyproject.toml          # Project metadata, dev dependencies, tool config
uv.lock                 # Locked dependency versions
```

### Notes

- `src.backend.*` and `GtkHelper.*` imports only resolve inside the StreamController Flatpak runtime. LSP errors on these are expected.
- GTK4 and Adwaita come from the Flatpak runtime, not pip.
- `set_media()` calls are silently ignored if the user has set a custom icon via the StreamController sidebar.

## License

[Apache License 2.0](LICENSE)
