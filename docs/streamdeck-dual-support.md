# Dual StreamController + Elgato Stream Deck Plugin Support

## Summary

This document outlines what it would take to support both the **StreamController** plugin format (current) and the official **Elgato Stream Deck** plugin format.

**Bottom line:** `lan_mouse.py` is pure Python with no framework deps — it's the ideal shared core. The StreamController actions and `main.py` are coupled to StreamController's GTK4/ActionBase API and need to be reimplemented for Stream Deck. Estimated effort: ~2.5 days.

---

## What's Shared vs What Must Be Rewritten

### Shared as-is (zero changes)
- `lan_mouse.py` — no deps, pure stdlib, fully typed, fully tested
- `tests/test_lan_mouse.py` — tests only `lan_mouse.py`, works for both plugins
- `assets/lan-mouse.png` — usable in both
- Settings schema — same logical fields (`client_id`, `auto_start`, `bin_path`, etc.)

### Must be rewritten for Stream Deck
- `main.py` — `PluginBase` is StreamController-only
- `actions/LanMouseLaunch/LanMouseLaunch.py` — `ActionBase` is StreamController-only
- `actions/LanMouseToggle/LanMouseToggle.py` — `ActionBase` is StreamController-only
- `manifest.json` — completely different Elgato schema
- Settings UI — HTML/CSS Property Inspector replaces GTK4/Adwaita widgets

---

## Recommended Approach: Python SDK + Monorepo

Reuse `lan_mouse.py` directly via the Python Stream Deck SDK. Do **not** rewrite it in TypeScript — that doubles maintenance burden with no functional gain.

**Key tradeoffs vs TypeScript SDK:**
- Python SDK is community-maintained (less polished), TypeScript is officially supported by Elgato
- Python SDK: `lan_mouse.py` reused directly, tests cover both plugins, ~2.5 days effort
- TypeScript SDK: must reimplement `lan_mouse.py` + tests in TS, ~4 days, better store support

Use Python SDK unless official Elgato store submission is required.

---

## Proposed Directory Structure

```
streamcontroller-lan-mouse/
├── lan_mouse.py                     # Shared core — unchanged, stays at root
├── streamcontroller/                # Existing SC plugin (moved from root)
│   ├── main.py
│   ├── actions/
│   │   ├── LanMouseLaunch/
│   │   └── LanMouseToggle/
│   ├── manifest.json
│   ├── locales/en_US.json
│   ├── assets/
│   └── store/
├── streamdeck/                      # New Elgato Stream Deck plugin
│   ├── app.py                       # Plugin entry point (Python SDK)
│   ├── actions/
│   │   ├── lan_mouse_launch.py
│   │   └── lan_mouse_toggle.py
│   ├── pi/                          # Property Inspector HTML
│   │   ├── launch.html
│   │   ├── toggle.html
│   │   └── style.css
│   ├── imgs/actions/                # 20/40/60px icon variants
│   └── manifest.json                # Elgato format
└── tests/
    └── test_lan_mouse.py            # Unchanged — covers both plugins
```

`lan_mouse.py` stays at repo root. Both plugins import it via `sys.path` insertion or symlink.

---

## StreamDeck Manifest Format

The Elgato `manifest.json` schema is fundamentally different from StreamController's:

```json
{
  "Name": "Lan Mouse",
  "Version": "1.0.0",
  "Author": "Ty Smith",
  "Actions": [
    {
      "Name": "Lan Mouse Launch",
      "UUID": "me.tysmith.lanmouse.launch",
      "Icon": "imgs/actions/lan-mouse",
      "States": [
        {"Image": "imgs/actions/lan-mouse", "Name": "Off"},
        {"Image": "imgs/actions/lan-mouse-running", "Name": "Running"}
      ],
      "PropertyInspectorPath": "pi/launch.html"
    },
    {
      "Name": "Lan Mouse Toggle",
      "UUID": "me.tysmith.lanmouse.toggle",
      "Icon": "imgs/actions/lan-mouse",
      "States": [
        {"Image": "imgs/actions/lan-mouse", "Name": "Off"},
        {"Image": "imgs/actions/lan-mouse-inactive", "Name": "Inactive"},
        {"Image": "imgs/actions/lan-mouse-active", "Name": "Active"}
      ],
      "PropertyInspectorPath": "pi/toggle.html"
    }
  ],
  "Category": "Lan Mouse",
  "CodePath": "app.py",
  "SDKVersion": 2,
  "Software": {"MinimumVersion": "6.4"},
  "OS": [
    {"Platform": "mac", "MinimumVersion": "10.15"},
    {"Platform": "windows", "MinimumVersion": "10"}
  ],
  "Python": {"MinimumVersion": "3.11"}
}
```

Key differences:
- `UUID` per action (reverse-DNS, globally unique)
- `States` array defines button images by index (replaces `set_background_color`)
- `PropertyInspectorPath` → HTML file per action
- `OS` and `Software` version gates
- `Python` section — Stream Deck software finds and launches Python automatically

---

## API Mapping: StreamController → Stream Deck

| StreamController | Stream Deck Python SDK |
|---|---|
| `on_ready()` | `on_will_appear(event)` — start asyncio polling task |
| `on_tick()` | `asyncio` loop: `while True: update(); await sleep(2)` |
| `event_callback(SHORT_UP)` | `on_key_up(event)` |
| `event_callback(HOLD_START)` | `on_key_down` + timestamp → elapsed check in `on_key_up` |
| `set_background_color([R,G,B,A])` | `event.action.set_state(index)` |
| `set_bottom_label(text)` | `event.action.set_title(text)` |
| `get_settings()` / `set_settings(d)` | `event.payload.settings` / `event.action.set_settings(d)` |
| `show_error()` | `event.action.show_alert()` |
| Plugin-level settings (PluginBase) | Move to per-action Property Inspector settings |

**Visual states** use pre-defined `States` from manifest rather than dynamic color setting:
- LanMouseLaunch: State 0 = Off, State 1 = Running
- LanMouseToggle: State 0 = Off, State 1 = Inactive, State 2 = Active

---

## Key Implementation Challenges

### 1. Asyncio + blocking subprocess
`lan_mouse.py` uses blocking `subprocess.run`. The Stream Deck SDK runs an async event loop. The polling task must use `loop.run_in_executor` to avoid blocking the WebSocket connection:

```python
async def poll_status(self, action, settings):
    loop = asyncio.get_event_loop()
    while True:
        status = await loop.run_in_executor(None, lan_mouse.get_status, settings.get("bin_path", ""))
        await self._update_button(action, status)
        await asyncio.sleep(2.0)
```

### 2. Hold-press simulation
Stream Deck has no native long-press event. Must roll own:

```python
def on_key_down(self, event):
    self._key_down_time = time.monotonic()

def on_key_up(self, event):
    elapsed = time.monotonic() - self._key_down_time
    if elapsed >= 0.5:  # hold threshold
        self._handle_kill(event)
    else:
        self._handle_toggle(event)
```

### 3. Flatpak
Stream Deck runs natively on macOS/Windows — not inside Flatpak. `_IN_FLATPAK` will always be `False` and `_host_cmd()` is a no-op. This is a simplification, not a problem.

### 4. Plugin-level settings
StreamController has `PluginBase.get_settings_area()` for plugin-wide config (bin_path, launch_command). Stream Deck has no equivalent. Move these into each action's Property Inspector — every action shows the same `bin_path`/`launch_command` fields. Slightly redundant but the standard Stream Deck pattern.

---

## Property Inspector

The Property Inspector is an HTML page loaded in an iframe next to the button config. It communicates with the plugin via WebSocket (`connectElgatoStreamDeckSocket` API).

**launch.html fields:** Custom Icon Path, Show Status Label, Running Color, Off Color, Bin Path, Launch Command

**toggle.html fields:** Client ID (-1 for auto), Auto-start, Custom Icon Path, Show Hostname, Active/Inactive/Off Colors, Bin Path, Launch Command

Elgato provides `sdpi.css` and `sdpi-components` for consistent styling. ~100 lines HTML + ~50 lines JS per file for two-way settings sync.

---

## Build & Packaging

Stream Deck plugins are distributed as `.sdPlugin` bundles (renamed ZIP):

```
com.tysmith.lanmouse.sdPlugin/
├── manifest.json
├── app.py
├── lan_mouse.py          # copied from repo root
├── actions/
├── pi/
└── imgs/
```

Build script (`scripts/build_streamdeck.sh`):
1. Create output dir structure
2. Copy `lan_mouse.py` from repo root into bundle
3. Copy `streamdeck/` contents
4. Zip into `.sdPlugin`

Stream Deck software launches `app.py` directly — no bundling of Python interpreter needed when manifest specifies `"Python": {"MinimumVersion": "3.11"}`.

---

## Effort Estimate

| Task | Time |
|---|---|
| Directory restructure + shared lan_mouse.py wiring | 0.5 day |
| StreamDeck manifest.json | 2 hours |
| `app.py` entry point | 1 hour |
| `lan_mouse_launch.py` action | 2 hours |
| `lan_mouse_toggle.py` action | 3 hours |
| Property Inspector HTML (both) | 4 hours |
| Image variants (20/40/60px) | 1 hour |
| Build/packaging script | 2 hours |
| Testing + debugging | 4 hours |
| **Total** | **~2.5 days** |

---

## Python SDK Options

The main Python SDK options for Elgato Stream Deck:

- **`streamdeck-sdk-python`** (PyPI) — most feature-complete, mirrors the official TS SDK structure
- **`streamdeck`** (PyPI) — older, simpler, still maintained
- **DIY WebSocket client** — the Stream Deck protocol is well-documented and minimal; ~100 lines to implement the handshake + event routing yourself

Check the chosen SDK's GitHub issues for Windows/macOS compatibility before committing.
