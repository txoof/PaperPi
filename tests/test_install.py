"""The systemd service file and the install script in install/ (docs/install-systemd.md).

They are tried on a real Pi with install/check-service; these tests only check that the
settings PaperPi depends on are there, so a later edit can't drop one by accident.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INSTALL = Path(__file__).parent.parent / "install"
SERVICE = INSTALL / "paperpi.service"
SCRIPT = INSTALL / "paperpi-install"


def settings(text: str) -> dict[str, list[str]]:
    """Every ``Key=value`` line of a service file, as key: all its values."""
    found: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"(\w+)=(.*)", line.strip())
        if match:
            found.setdefault(match[1], []).append(match[2])
    return found


SET = settings(SERVICE.read_text())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        # PaperPi sends READY=1 and WATCHDOG=1 itself (paperpi.health).
        ("Type", "notify"),
        ("WatchdogSec", "120"),
        ("RuntimeDirectory", "paperpi"),  # /run/paperpi, for the health file
        ("StateDirectory", "paperpi"),  # /var/lib/paperpi, the default --state-dir
        ("User", "paperpi"),
        ("Restart", "on-failure"),
        ("ExecReload", "/opt/paperpi/venv/bin/paperpi reload"),  # applies config changes
    ],
)
def test_service_setting(key, value):
    assert SET[key] == [value]


def test_a_restart_from_the_web_interface_starts_paperpi_again():
    from paperpi.cli import RESTART_STATUS

    # A clean stop (not a failure in the log), and started again all the same.
    assert SET["SuccessExitStatus"] == SET["RestartForceExitStatus"] == [str(RESTART_STATUS)]


def test_stop_waits_for_the_screen_clear():
    # The exit clear may take 30 s, its check 2 s more.
    assert int(SET["TimeoutStopSec"][0]) > 32


def test_stop_ends_every_process():
    # #209: only the default KillMode=control-group also ends the plugin processes, the
    # forkserver and the resource tracker after "kill -9" of the main process.
    assert "KillMode" not in SET
    # Only the main process may say "still running" (a plugin can't hide a stuck loop).
    assert SET.get("NotifyAccess", ["main"]) == ["main"]


def test_service_can_use_the_screen_and_write_the_config():
    assert set(SET["SupplementaryGroups"][0].split()) == {"spi", "gpio"}
    assert SET["DeviceAllow"] == ["char-spi rw", "char-gpiochip rw"]
    # The web interface saves the config file (a new file in the same folder).
    assert SET["ReadWritePaths"] == ["/etc/paperpi"]


def test_service_starts_what_the_script_installs():
    script = SCRIPT.read_text()
    venv = re.search(r"^VENV=\$PREFIX/(\S+)$", script, re.MULTILINE)[1]
    prefix = re.search(r"^PREFIX=(\S+)$", script, re.MULTILINE)[1]
    assert SET["ExecStart"] == [f"{prefix}/{venv}/bin/paperpi run"]


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="needs systemd")
def test_an_update_installs_the_new_paperpi_code():
    # uv keeps an installed package of the same version; PaperPi's stays 2.0.0.dev0 between
    # commits, so without this an update would keep running the old code (issue #319).
    sync = re.search(r'"\$TOOLS/bin/uv" sync [^)]*', SCRIPT.read_text())
    assert sync and "--reinstall-package paperpi" in sync[0]


def test_systemd_accepts_the_service_file(tmp_path):
    # The installed program isn't here, so the check gets one that is.
    text = SERVICE.read_text().replace("/opt/paperpi/venv/bin/paperpi", shutil.which("true"))
    unit = tmp_path / "paperpi.service"
    unit.write_text(text)
    done = subprocess.run(
        ["systemd-analyze", "verify", str(unit)], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""


@pytest.mark.parametrize("script", [SCRIPT, INSTALL / "check-service"])
def test_scripts_are_valid_bash(script):
    subprocess.run(["bash", "-n", str(script)], check=True)
    assert script.stat().st_mode & 0o111


def test_install_script_help():
    done = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True, check=True)
    for command in ("install", "update", "uninstall"):
        assert f"  {command}  " in done.stdout


def test_install_script_refuses_unknown_commands():
    done = subprocess.run([str(SCRIPT), "reinstall"], capture_output=True, text=True)
    assert done.returncode == 2
    assert "Usage:" in done.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="as root it would really update")
def test_install_script_needs_root():
    done = subprocess.run([str(SCRIPT), "update"], capture_output=True, text=True)
    assert done.returncode == 1
    assert "run it with sudo" in done.stderr
