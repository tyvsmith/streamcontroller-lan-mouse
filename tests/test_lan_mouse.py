"""Tests for the lan_mouse helper module."""

import subprocess
from unittest.mock import patch

import lan_mouse


# ---------------------------------------------------------------------------
# _bin()
# ---------------------------------------------------------------------------


class TestBin:
    def test_default_when_empty(self):
        assert lan_mouse._bin("") == "lan-mouse"

    def test_default_when_whitespace(self):
        assert lan_mouse._bin("   ") == "lan-mouse"

    def test_custom_path(self):
        assert lan_mouse._bin("/usr/local/bin/lan-mouse") == "/usr/local/bin/lan-mouse"

    def test_custom_path_stripped(self):
        assert lan_mouse._bin("  /opt/lan-mouse  ") == "/opt/lan-mouse"


# ---------------------------------------------------------------------------
# _host_prefix()
# ---------------------------------------------------------------------------


class TestHostPrefix:
    @patch("lan_mouse._IN_FLATPAK", False)
    def test_outside_flatpak(self):
        assert lan_mouse._host_prefix() == []

    @patch("lan_mouse._IN_FLATPAK", True)
    def test_inside_flatpak(self):
        assert lan_mouse._host_prefix() == ["flatpak-spawn", "--host"]


# ---------------------------------------------------------------------------
# _CLIENT_RE regex
# ---------------------------------------------------------------------------


class TestClientRegex:
    def test_standard_line(self):
        line = "id 0: 192.168.10.54:4242 (left) active: true, ips: {192.168.10.54}"
        m = lan_mouse._CLIENT_RE.search(line)
        assert m is not None
        assert m.group("id") == "0"
        assert m.group("host") == "192.168.10.54"
        assert m.group("port") == "4242"
        assert m.group("position") == "left"
        assert m.group("active") == "true"
        assert m.group("ips") == "192.168.10.54"

    def test_inactive_client(self):
        line = "id 1: myhost:9876 (right) active: false, ips: {10.0.0.1}"
        m = lan_mouse._CLIENT_RE.search(line)
        assert m is not None
        assert m.group("id") == "1"
        assert m.group("active") == "false"

    def test_multiple_ips(self):
        line = "id 2: host:1234 (top) active: true, ips: {10.0.0.1, 10.0.0.2}"
        m = lan_mouse._CLIENT_RE.search(line)
        assert m is not None
        assert m.group("ips") == "10.0.0.1, 10.0.0.2"

    def test_no_ips_field(self):
        line = "id 3: host:5555 (bottom) active: false"
        m = lan_mouse._CLIENT_RE.search(line)
        assert m is not None
        assert m.group("ips") is None

    def test_hostname_with_dots(self):
        line = "id 0: my.host.local:4242 (left) active: true, ips: {192.168.1.1}"
        m = lan_mouse._CLIENT_RE.search(line)
        assert m is not None
        assert m.group("host") == "my.host.local"

    def test_no_match_on_garbage(self):
        assert lan_mouse._CLIENT_RE.search("not a valid line") is None

    def test_no_match_on_empty(self):
        assert lan_mouse._CLIENT_RE.search("") is None


# ---------------------------------------------------------------------------
# list_clients()
# ---------------------------------------------------------------------------


def _make_run_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args="", returncode=returncode, stdout=stdout, stderr=""
    )


class TestListClients:
    @patch("lan_mouse._run")
    def test_single_client(self, mock_run):
        mock_run.return_value = _make_run_result(
            "id 0: 192.168.10.54:4242 (left) active: true, ips: {192.168.10.54}\n"
        )
        clients = lan_mouse.list_clients()
        assert len(clients) == 1
        assert clients[0] == {
            "id": 0,
            "host": "192.168.10.54",
            "port": 4242,
            "position": "left",
            "active": True,
            "ips": ["192.168.10.54"],
        }

    @patch("lan_mouse._run")
    def test_multiple_clients(self, mock_run):
        mock_run.return_value = _make_run_result(
            "id 0: 192.168.10.54:4242 (left) active: true, ips: {192.168.10.54}\n"
            "id 1: 10.0.0.5:4242 (right) active: false, ips: {10.0.0.5}\n"
        )
        clients = lan_mouse.list_clients()
        assert len(clients) == 2
        assert clients[0]["id"] == 0
        assert clients[0]["active"] is True
        assert clients[1]["id"] == 1
        assert clients[1]["active"] is False
        assert clients[1]["position"] == "right"

    @patch("lan_mouse._run")
    def test_multiple_ips_parsed(self, mock_run):
        mock_run.return_value = _make_run_result(
            "id 0: host:1234 (top) active: true, ips: {10.0.0.1, 10.0.0.2, 10.0.0.3}\n"
        )
        clients = lan_mouse.list_clients()
        assert clients[0]["ips"] == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    @patch("lan_mouse._run")
    def test_no_ips_field(self, mock_run):
        mock_run.return_value = _make_run_result(
            "id 0: host:5555 (bottom) active: false\n"
        )
        clients = lan_mouse.list_clients()
        assert clients[0]["ips"] == []

    @patch("lan_mouse._run")
    def test_empty_output(self, mock_run):
        mock_run.return_value = _make_run_result("")
        assert lan_mouse.list_clients() == []

    @patch("lan_mouse._run")
    def test_command_failure(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=1)
        assert lan_mouse.list_clients() == []

    @patch("lan_mouse._run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="", timeout=5)
        assert lan_mouse.list_clients() == []

    @patch("lan_mouse._run")
    def test_oserror(self, mock_run):
        mock_run.side_effect = OSError("broken")
        assert lan_mouse.list_clients() == []

    @patch("lan_mouse._run")
    def test_skips_malformed_lines(self, mock_run):
        mock_run.return_value = _make_run_result(
            "some header text\n"
            "id 0: 192.168.10.54:4242 (left) active: true, ips: {192.168.10.54}\n"
            "garbage line\n"
            "id 1: 10.0.0.5:4242 (right) active: false\n"
        )
        clients = lan_mouse.list_clients()
        assert len(clients) == 2

    @patch("lan_mouse._run")
    def test_custom_bin_path(self, mock_run):
        mock_run.return_value = _make_run_result("")
        lan_mouse.list_clients("/custom/lan-mouse")
        mock_run.assert_called_once_with(["/custom/lan-mouse", "cli", "list"])


# ---------------------------------------------------------------------------
# get_status()
# ---------------------------------------------------------------------------


class TestGetStatus:
    @patch("lan_mouse.is_running", return_value=True)
    @patch("lan_mouse._run")
    def test_running_with_clients(self, mock_run, _is_running):
        mock_run.return_value = _make_run_result(
            "id 0: 192.168.10.54:4242 (left) active: true, ips: {192.168.10.54}\n"
        )
        status = lan_mouse.get_status()
        assert status["running"] is True
        assert len(status["clients"]) == 1
        assert status["clients"][0]["id"] == 0

    @patch("lan_mouse.is_running", return_value=True)
    @patch("lan_mouse._run")
    def test_running_no_clients(self, mock_run, _is_running):
        mock_run.return_value = _make_run_result("")
        status = lan_mouse.get_status()
        assert status["running"] is True
        assert status["clients"] == []

    @patch("lan_mouse.is_running", return_value=False)
    def test_not_running(self, _is_running):
        status = lan_mouse.get_status()
        assert status["running"] is False
        assert status["clients"] == []

    @patch("lan_mouse.is_running", return_value=True)
    @patch("lan_mouse._run")
    def test_cli_fails_but_process_running(self, mock_run, _is_running):
        """pgrep says running but CLI fails — report not running to avoid false positives."""
        mock_run.return_value = _make_run_result("", returncode=1)
        status = lan_mouse.get_status()
        assert status["running"] is False
        assert status["clients"] == []

    @patch("lan_mouse.is_running", return_value=True)
    @patch("lan_mouse._run")
    def test_cli_timeout_with_running_process(self, mock_run, _is_running):
        """pgrep says running but CLI times out — report not running to avoid false positives."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="", timeout=5)
        status = lan_mouse.get_status()
        assert status["running"] is False
        assert status["clients"] == []

    @patch("lan_mouse.is_running", return_value=True)
    @patch("lan_mouse._run")
    def test_cli_called_once_when_running(self, mock_run, _is_running):
        """Verify CLI is called exactly once when the process is running."""
        mock_run.return_value = _make_run_result(
            "id 0: host:4242 (left) active: true\n"
        )
        lan_mouse.get_status()
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# is_running()
# ---------------------------------------------------------------------------


class TestIsRunning:
    @patch("lan_mouse._run")
    def test_running(self, mock_run):
        mock_run.return_value = _make_run_result("12345\n", returncode=0)
        assert lan_mouse.is_running() is True

    @patch("lan_mouse._run")
    def test_not_running(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=1)
        assert lan_mouse.is_running() is False

    @patch("lan_mouse._run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="", timeout=5)
        assert lan_mouse.is_running() is False

    @patch("lan_mouse._run")
    def test_oserror(self, mock_run):
        mock_run.side_effect = OSError("broken")
        assert lan_mouse.is_running() is False

    @patch("lan_mouse._run")
    def test_uses_basename_of_custom_path(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=0)
        lan_mouse.is_running("/usr/local/bin/lan-mouse")
        mock_run.assert_called_once_with(["pgrep", "-x", "lan-mouse"])


# ---------------------------------------------------------------------------
# activate() / deactivate()
# ---------------------------------------------------------------------------


class TestActivate:
    @patch("lan_mouse._run")
    def test_success(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=0)
        assert lan_mouse.activate(0) is True
        mock_run.assert_called_once_with(["lan-mouse", "cli", "activate", "0"])

    @patch("lan_mouse._run")
    def test_failure(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=1)
        assert lan_mouse.activate(0) is False

    @patch("lan_mouse._run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="", timeout=5)
        assert lan_mouse.activate(0) is False

    @patch("lan_mouse._run")
    def test_custom_bin_path(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=0)
        lan_mouse.activate(3, "/opt/lm")
        mock_run.assert_called_once_with(["/opt/lm", "cli", "activate", "3"])


class TestDeactivate:
    @patch("lan_mouse._run")
    def test_success(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=0)
        assert lan_mouse.deactivate(1) is True
        mock_run.assert_called_once_with(["lan-mouse", "cli", "deactivate", "1"])

    @patch("lan_mouse._run")
    def test_failure(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=1)
        assert lan_mouse.deactivate(1) is False

    @patch("lan_mouse._run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="", timeout=5)
        assert lan_mouse.deactivate(1) is False


# ---------------------------------------------------------------------------
# _resolve_launch_cmd()
# ---------------------------------------------------------------------------


class TestResolveLaunchCmd:
    def setup_method(self):
        lan_mouse._resolve_launch_cmd.cache_clear()

    def teardown_method(self):
        lan_mouse._resolve_launch_cmd.cache_clear()

    @patch("lan_mouse._has_command", return_value=True)
    def test_prefers_uwsm(self, _mock):
        assert lan_mouse._resolve_launch_cmd() == "uwsm-app -- lan-mouse"

    @patch("lan_mouse._has_command", return_value=False)
    def test_falls_back_to_bare(self, _mock):
        assert lan_mouse._resolve_launch_cmd() == "lan-mouse"

    @patch("lan_mouse._has_command", return_value=True)
    def test_custom_bin_with_uwsm(self, _mock):
        assert lan_mouse._resolve_launch_cmd("/opt/lm") == "uwsm-app -- /opt/lm"

    @patch("lan_mouse._has_command", return_value=False)
    def test_custom_bin_without_uwsm(self, _mock):
        assert lan_mouse._resolve_launch_cmd("/opt/lm") == "/opt/lm"


# ---------------------------------------------------------------------------
# launch()
# ---------------------------------------------------------------------------


class TestLaunch:
    @patch("subprocess.Popen")
    @patch("lan_mouse._IN_FLATPAK", False)
    @patch("lan_mouse._resolve_launch_cmd", return_value="uwsm-app -- lan-mouse")
    def test_auto_detect(self, _resolve, mock_popen):
        lan_mouse.launch()
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0] == ["uwsm-app", "--", "lan-mouse"]

    @patch("subprocess.Popen")
    @patch("lan_mouse._IN_FLATPAK", False)
    def test_custom_command(self, mock_popen):
        lan_mouse.launch("my-custom-launcher")
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0] == ["my-custom-launcher"]

    @patch("subprocess.Popen")
    @patch("lan_mouse._IN_FLATPAK", False)
    @patch("lan_mouse._resolve_launch_cmd", return_value="lan-mouse")
    def test_whitespace_command_uses_auto(self, _resolve, mock_popen):
        lan_mouse.launch("   ")
        assert mock_popen.call_args[0][0] == ["lan-mouse"]

    @patch("subprocess.Popen")
    @patch("lan_mouse._IN_FLATPAK", True)
    @patch("lan_mouse._resolve_launch_cmd", return_value="lan-mouse")
    def test_flatpak_prepends_host_prefix(self, _resolve, mock_popen):
        lan_mouse.launch()
        assert mock_popen.call_args[0][0] == ["flatpak-spawn", "--host", "lan-mouse"]


# ---------------------------------------------------------------------------
# kill()
# ---------------------------------------------------------------------------


class TestKill:
    @patch("lan_mouse.is_running", return_value=False)
    @patch("time.sleep")
    @patch("lan_mouse._run")
    def test_kill_success_immediate(self, mock_run, mock_sleep, mock_running):
        mock_run.return_value = _make_run_result("", returncode=0)
        assert lan_mouse.kill() is True
        mock_run.assert_called_once_with(["pkill", "-x", "lan-mouse"])
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch("lan_mouse._run")
    def test_kill_waits_for_exit(self, mock_run, mock_sleep):
        mock_run.return_value = _make_run_result("", returncode=0)
        # is_running: True 3 times, then False
        with patch("lan_mouse.is_running", side_effect=[True, True, True, False]):
            assert lan_mouse.kill() is True
        assert mock_sleep.call_count == 3

    @patch("lan_mouse._run")
    def test_kill_pkill_fails(self, mock_run):
        mock_run.return_value = _make_run_result("", returncode=1)
        assert lan_mouse.kill() is False

    @patch("lan_mouse._run")
    def test_kill_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="", timeout=5)
        assert lan_mouse.kill() is False

    @patch("lan_mouse.is_running", return_value=True)
    @patch("time.sleep")
    @patch("lan_mouse._run")
    def test_kill_process_never_exits(self, mock_run, mock_sleep, mock_running):
        mock_run.return_value = _make_run_result("", returncode=0)
        # is_running always returns True — kill gives up after 20 polls
        result = lan_mouse.kill()
        assert result is False  # returns False when process never exits
        assert mock_sleep.call_count == 20

    @patch("lan_mouse.is_running", return_value=False)
    @patch("time.sleep")
    @patch("lan_mouse._run")
    def test_kill_custom_bin_path(self, mock_run, mock_sleep, mock_running):
        mock_run.return_value = _make_run_result("", returncode=0)
        lan_mouse.kill("/usr/local/bin/lan-mouse")
        mock_run.assert_called_once_with(["pkill", "-x", "lan-mouse"])


# ---------------------------------------------------------------------------
# wait_for_ready()
# ---------------------------------------------------------------------------


class TestWaitForReady:
    @patch("time.sleep")
    @patch("lan_mouse._run")
    @patch("lan_mouse.is_running", return_value=True)
    def test_ready_immediately(self, mock_running, mock_run, mock_sleep):
        mock_run.return_value = _make_run_result("", returncode=0)
        assert lan_mouse.wait_for_ready(timeout=5.0) is True
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch("lan_mouse._run")
    def test_becomes_ready_after_retries(self, mock_run, mock_sleep):
        # is_running: False, False, True
        with patch("lan_mouse.is_running", side_effect=[False, False, True]):
            mock_run.return_value = _make_run_result("", returncode=0)
            assert lan_mouse.wait_for_ready(timeout=5.0) is True
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    @patch("lan_mouse.is_running", return_value=True)
    @patch("lan_mouse._run")
    def test_running_but_cli_fails_then_succeeds(
        self, mock_run, mock_running, mock_sleep
    ):
        # CLI fails twice, then succeeds
        mock_run.side_effect = [
            _make_run_result("", returncode=1),
            _make_run_result("", returncode=1),
            _make_run_result("", returncode=0),
        ]
        assert lan_mouse.wait_for_ready(timeout=5.0) is True

    @patch("time.monotonic")
    @patch("time.sleep")
    @patch("lan_mouse.is_running", return_value=False)
    def test_timeout(self, mock_running, mock_sleep, mock_monotonic):
        # Simulate time passing past deadline
        mock_monotonic.side_effect = [0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.1]
        assert lan_mouse.wait_for_ready(timeout=5.0) is False

    @patch("time.sleep")
    @patch("lan_mouse.is_running", return_value=True)
    @patch("lan_mouse._run")
    def test_cli_oserror_retries(self, mock_run, mock_running, mock_sleep):
        mock_run.side_effect = [
            OSError("broken"),
            _make_run_result("", returncode=0),
        ]
        assert lan_mouse.wait_for_ready(timeout=5.0) is True
