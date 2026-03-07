"""Shared helpers for interacting with the lan-mouse CLI from inside the flatpak sandbox."""

from __future__ import annotations

import functools
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import TypedDict

# Default binary name (searched in PATH)
DEFAULT_BIN: str = "lan-mouse"

# Cache immutable runtime values (these never change while the process is alive)
_IN_FLATPAK: bool = Path("/.flatpak-info").is_file()
_HOME_DIR: Path = Path.home()


class Client(TypedDict):
    """A parsed lan-mouse client entry."""

    id: int
    host: str
    port: int
    position: str
    active: bool
    ips: list[str]


def _host_prefix() -> list[str]:
    """Return the flatpak-spawn --host prefix when running inside the Flatpak sandbox."""
    return ["flatpak-spawn", "--host"] if _IN_FLATPAK else []


def _run(args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    """Run a host command and return the CompletedProcess."""
    return subprocess.run(
        _host_prefix() + args,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        start_new_session=True,
        cwd=_HOME_DIR,
    )


def _bin(bin_path: str = "") -> str:
    """Return the lan-mouse binary path, defaulting to 'lan-mouse'."""
    return bin_path.strip() or DEFAULT_BIN


def _has_command(name: str) -> bool:
    """Check if a command exists on the host."""
    if not _IN_FLATPAK:
        return shutil.which(name) is not None
    try:
        result = _run(["which", name])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def is_running(bin_path: str = "") -> bool:
    """Check if the lan-mouse process is running."""
    try:
        name = Path(_bin(bin_path)).name
        result = _run(["pgrep", "-x", name])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# Example line: id 0: 192.168.10.54:4242 (left) active: true, ips: {192.168.10.54}
_CLIENT_RE = re.compile(
    r"id\s+(?P<id>\d+):\s+"
    r"(?P<host>[^:]+):(?P<port>\d+)\s+"
    r"\((?P<position>\w+)\)\s+"
    r"active:\s+(?P<active>true|false)"
    r"(?:,\s+ips:\s+\{(?P<ips>[^}]*)\})?"
)


def _parse_clients(stdout: str) -> list[Client]:
    """Parse lan-mouse CLI output into a list of :class:`Client` dicts."""
    clients: list[Client] = []
    for line in stdout.splitlines():
        m = _CLIENT_RE.search(line)
        if m:
            ips_raw: str = m.group("ips") or ""
            clients.append(
                Client(
                    id=int(m.group("id")),
                    host=m.group("host"),
                    port=int(m.group("port")),
                    position=m.group("position"),
                    active=m.group("active") == "true",
                    ips=[ip.strip() for ip in ips_raw.split(",") if ip.strip()],
                )
            )
    return clients


def list_clients(bin_path: str = "") -> list[Client]:
    """Parse output of ``lan-mouse cli list`` into a list of :class:`Client` dicts.

    Returns an empty list if lan-mouse is not running or the command fails.
    """
    try:
        result = _run([_bin(bin_path), "cli", "list"])
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, OSError):
        return []

    return _parse_clients(result.stdout)


class Status(TypedDict):
    """Snapshot of lan-mouse state from a single CLI call."""

    running: bool
    clients: list[Client]


def get_status(bin_path: str = "") -> Status:
    """Get running state and client list.

    Requires BOTH pgrep and a successful CLI response to report running.
    This prevents false positives from either source during process
    startup/shutdown races (e.g. IPC socket cleanup, auto-restart delay).
    """
    if not is_running(bin_path):
        return Status(running=False, clients=[])
    try:
        result = _run([_bin(bin_path), "cli", "list"])
        if result.returncode == 0:
            return Status(running=True, clients=_parse_clients(result.stdout))
    except (subprocess.TimeoutExpired, OSError):
        pass
    return Status(running=False, clients=[])


def activate(client_id: int, bin_path: str = "") -> bool:
    """Activate a client connection. Returns True on success."""
    try:
        result = _run([_bin(bin_path), "cli", "activate", str(client_id)])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def deactivate(client_id: int, bin_path: str = "") -> bool:
    """Deactivate a client connection. Returns True on success."""
    try:
        result = _run([_bin(bin_path), "cli", "deactivate", str(client_id)])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@functools.lru_cache(maxsize=4)
def _resolve_launch_cmd(bin_path: str = "") -> str:
    """Determine the best launch command for this system.

    Prefers uwsm-app (systemd session integration) if available,
    falls back to the bare binary. Result is cached per bin_path since
    available commands don't change at runtime.
    """
    b = _bin(bin_path)
    if _has_command("uwsm-app"):
        return f"uwsm-app -- {b}"
    return b


def launch(command: str = "", bin_path: str = "") -> None:
    """Start the lan-mouse daemon (fire-and-forget).

    Args:
        command: Custom launch command. If empty, auto-detects the best method.
        bin_path: Custom path to the lan-mouse binary.
    """
    args = _host_prefix() + shlex.split(
        command.strip() or _resolve_launch_cmd(bin_path)
    )
    subprocess.Popen(
        args,
        shell=False,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=_HOME_DIR,
    )


def wait_for_ready(bin_path: str = "", timeout: float = 5.0) -> bool:
    """Wait for lan-mouse to be running and its CLI to respond. Returns True if ready."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(bin_path):
            try:
                result = _run([_bin(bin_path), "cli", "list"])
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, OSError):
                pass
        time.sleep(0.3)
    return False


def kill(bin_path: str = "") -> bool:
    """Kill the lan-mouse daemon and wait for it to exit. Returns True on success."""
    try:
        name = Path(_bin(bin_path)).name
        result = _run(["pkill", "-x", name])
        if result.returncode != 0:
            return False
        for _ in range(20):
            if not is_running(bin_path):
                return True
            _run(["pkill", "-x", name])  # re-kill in case of auto-restart
            time.sleep(0.1)
        return not is_running(bin_path)
    except (subprocess.TimeoutExpired, OSError):
        return False
