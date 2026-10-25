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
    # uv keeps an installed package of the same version; PaperPi's stays the same between
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


def run_functions(snippet: str, answers: str = "", **variables: str):
    """Run ``snippet`` after the install script's settings and functions (not ``main``),
    with ``answers`` as what is typed in the terminal and ``variables`` set first."""
    body = SCRIPT.read_text().rsplit('\nmain "$@"', 1)[0]
    # The terminal is the test's input here.
    body = body.replace("</dev/tty", "")
    setup = "".join(f"{name}={value}\n" for name, value in variables.items())
    return subprocess.run(
        ["bash", "-c", body + "\n" + setup + snippet],
        input=answers,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_screen_menu_has_every_it8951_size():
    from epdlib.drivers.it8951 import MODELS

    sizes = re.search(r"^IT8951_MODELS=\(([^)]*)\)$", SCRIPT.read_text(), re.MULTILINE)[1]
    assert sizes.split() == list(MODELS)


CHOSEN = 'choose_screen; echo "<$DISPLAY_TYPE|$MODEL|$VCOM>"'
NEW = {"CONFIG": "/nonexistent/paperpi.toml", "DISPLAY_TYPE": "", "MODEL": "", "VCOM": ""}


def test_the_screen_menu_asks_the_size_and_the_vcom():
    # A wrong number and a wrong vcom are asked again.
    done = run_functions(CHOSEN, "7\n3\n1.9\n-4\n-1.90\n", ASK="yes", **NEW)
    assert done.stdout.endswith("<it8951|9.7|-1.90>\n"), done.stderr
    assert done.stdout.count("Type a number from the list.") == 1
    assert done.stdout.count("between -3.0 and -0.5") == 2


def test_the_screen_menu_can_be_skipped():
    done = run_functions(CHOSEN, "\n", ASK="yes", **NEW)
    assert done.stdout.endswith("<virtual||>\n")


def test_no_questions_with_yes_or_a_display():
    assert run_functions(CHOSEN, ASK="no", **NEW).stdout == "<virtual||>\n"
    given = NEW | {"DISPLAY_TYPE": "it8951", "MODEL": "6", "VCOM": "-2"}
    assert run_functions(CHOSEN, ASK="yes", **given).stdout == "<it8951|6|-2>\n"


def test_a_kept_config_tells_whether_spi_is_needed(tmp_path):
    config = tmp_path / "paperpi.toml"
    config.write_text('[display]\ntype = "it8951"\n')
    done = run_functions(CHOSEN, ASK="yes", **(NEW | {"CONFIG": str(config)}))
    assert done.stdout == "<it8951||>\n"


def test_an_ended_input_stops_the_questions():
    done = run_functions(CHOSEN, "3\n", ASK="yes", **NEW)
    assert done.returncode == 1
    assert "no answer" in done.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="as root it would really install")
def test_no_command_installs_when_paperpi_is_not_there(tmp_path):
    # "curl ... | sudo bash" gives no command.
    done = run_functions("main", CODE=str(tmp_path / "code"))
    assert "run it with sudo" in done.stderr
    (tmp_path / ".git").mkdir()
    installed = run_functions("main", CODE=str(tmp_path))
    assert installed.returncode == 2
    assert "Usage:" in installed.stderr


@pytest.mark.parametrize(
    ("tags", "newest"),
    [
        ([], "main"),
        (["v1-final"], "main"),
        (["v1-final", "v2.0.0a1", "v2.0.0a2"], "v2.0.0a2"),
        (["v2.0.0b1", "v2.0.0rc1"], "v2.0.0rc1"),
        # A test release only while there is no full one.
        (["v2.0.0a1", "v2.0.0", "v2.1.0b1"], "v2.0.0"),
        (["v2.0.0", "v2.0.1", "v2.0.10", "v2.1.0a1"], "v2.0.10"),
    ],
)
def test_the_newest_release(tmp_path, tags, newest):
    def git(*command):
        subprocess.run(["git", "-C", str(tmp_path), *command], check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "c")
    for tag in tags:
        git("tag", tag)
    done = run_functions("newest_release", CODE=str(tmp_path))
    assert done.stdout == f"{newest}\n", done.stderr


def test_the_version_can_be_a_release_tag():
    # .github/workflows/release.yml: the tag is "v" + this version; newest_release sorts
    # the tags by number, so the version must be numbers with an optional a, b or rc part.
    import tomllib

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?", version)
