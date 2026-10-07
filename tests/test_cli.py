"""The paperpi command (paperpi.cli)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from paperpi import cli, config
from paperpi.cli import main
from paperpi.plugin import State
from paperpi.runner import PluginFailed, UpdateResult

from .test_config import GOOD


def render(*args):
    return main(["render", *args])


def test_render_sample_without_config(tmp_path, capsys):
    out = tmp_path / "clock.png"
    assert render("basic_clock", "-o", str(out)) == 0
    image = Image.open(out)
    assert image.size == (1200, 825)
    assert "saved" in capsys.readouterr().out


def test_render_default_output_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert render("basic_clock") == 0
    assert (tmp_path / "basic_clock.png").is_file()


def test_render_options(tmp_path):
    out = tmp_path / "c.png"
    args = ["basic_clock", "--size", "264x176", "--mode", "bw", "--layout", "time_date"]
    assert render(*args, "--set", "hours=12", "-o", str(out)) == 0
    image = Image.open(out)
    assert image.size == (264, 176)
    assert image.mode == "1"


def test_render_live(tmp_path):
    assert render("basic_clock", "--live", "-o", str(tmp_path / "c.png")) == 0


def test_render_from_config(tmp_path):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        GOOD.replace(
            'type = "virtual"', 'type = "virtual"\nwidth = 400\nheight = 300\nrotation = 90'
        )
    )
    out = tmp_path / "c.png"
    assert render("--config", str(cfg), "--name", "Clock", "-o", str(out)) == 0
    assert Image.open(out).size == (300, 400)  # drawn for a screen turned on its side
    assert not (tmp_path / "paperpi.last-good.toml").exists()


@pytest.mark.parametrize(("mode", "image_mode"), [("7color", "1"), ("rgb", "L")])
def test_render_from_config_with_color_off(tmp_path, mode, image_mode):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        GOOD.replace('type = "virtual"', f'type = "virtual"\nmode = "{mode}"\ncolor = false')
    )
    out = tmp_path / "c.png"
    assert render("--config", str(cfg), "--name", "Clock", "-o", str(out)) == 0
    assert Image.open(out).mode == image_mode


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "which plugin?"),
        (["nope"], "unknown plugin 'nope'; known: basic_clock"),
        (["basic_clock", "--set", "hour=12"], "unknown setting hour; basic_clock has: hours"),
        (["basic_clock", "--set", "hours=13"], "hours: Input should be 12 or 24"),
        (["basic_clock", "--set", "hours"], "--set needs SETTING=VALUE"),
        (["basic_clock", "--size", "big"], "--size must be WIDTHxHEIGHT"),
        (["basic_clock", "--size", "0x10"], "--size must be WIDTHxHEIGHT"),
        (
            ["basic_clock", "--layout", "huge"],
            "unknown layout 'huge'; choose from: time, time_date",
        ),
        (["basic_clock", "--time-limit", "0"], "--time-limit must be above 0"),
        (["--config", "x.toml"], "give the plugin's name"),
    ],
)
def test_render_usage_errors(args, message, capsys):
    assert render(*args) == 2
    assert message in capsys.readouterr().err


def test_render_config_problems(tmp_path, capsys):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(GOOD + "hours = 13\n")
    assert render("--config", str(cfg), "--name", "Clock") == 2
    err = capsys.readouterr().err
    assert "no usable plugin named 'Clock'" in err

    cfg.write_text("config_version = 1\n")
    assert render("--config", str(cfg), "--name", "Clock") == 2
    assert "a [display] part is needed" in capsys.readouterr().err


def test_render_options_not_allowed_with_config(tmp_path, capsys):
    args = ["--config", "x.toml", "--name", "Clock", "--size", "10x10"]
    assert render(*args) == 2
    assert "come from the config file" in capsys.readouterr().err


def test_python_dash_m_paperpi(tmp_path):
    out = tmp_path / "c.png"
    result = subprocess.run(
        [sys.executable, "-m", "paperpi", "render", "basic_clock", "-o", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert out.is_file()


# --- Added after review ------------------------------------------------------------------------


def fake_result(monkeypatch, result=None, error=None):
    def run_update(*args, **kwargs):
        if error:
            raise error
        return result

    monkeypatch.setattr(cli, "run_update", run_update)


def test_render_failed_plugin(monkeypatch, capsys):
    fake_result(monkeypatch, error=PluginFailed("basic_clock", "ValueError: no"))
    assert render("basic_clock") == 1
    assert "plugin 'basic_clock': ValueError: no" in capsys.readouterr().err


def test_render_nothing_to_show(monkeypatch, tmp_path, capsys):
    fake_result(monkeypatch, UpdateResult(State.NOTHING, None, 0.1))
    out = tmp_path / "c.png"
    assert render("basic_clock", "-o", str(out)) == 0
    assert "nothing to show" in capsys.readouterr().out
    assert not out.exists()


def test_render_alert(monkeypatch, tmp_path, capsys):
    fake_result(monkeypatch, UpdateResult(State.ALERT, Image.new("L", (10, 10)), 0.1))
    assert render("basic_clock", "-o", str(tmp_path / "c.png")) == 0
    assert "(alert)" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["no-ending", "missing/c.png"])
def test_render_output_names(tmp_path, capsys, name):
    out = tmp_path / name
    code = render("basic_clock", "-o", str(out))
    if out.parent.exists():
        assert code == 0
        assert Image.open(out).format == "PNG"
    else:
        assert code == 2
        assert "can't write" in capsys.readouterr().err


def test_render_from_config_never_saves_a_last_good_copy(tmp_path, monkeypatch):
    def save(*args):
        raise AssertionError("render must not save a last good copy")

    monkeypatch.setattr(config, "_save_last_good", save)
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(GOOD)
    assert render("--config", str(cfg), "--name", "Clock", "-o", str(tmp_path / "c.png")) == 0


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["basic_clock", "--name", "Clock"], "--name only works together with --config"),
        (["basic_clock", "--config", "x.toml", "--name", "C"], "not both"),
    ],
)
def test_render_name_and_config_mistakes(args, message, capsys):
    assert render(*args) == 2
    assert message in capsys.readouterr().err


def test_render_prints_the_mode_name(tmp_path, capsys):
    render("basic_clock", "--mode", "7color", "-o", str(tmp_path / "c.png"))
    assert "1200x825 7color" in capsys.readouterr().out


@pytest.mark.parametrize("stop", ["SIGTERM", "SIGINT"])
def test_run_shows_plugins_reloads_and_stops(tmp_path, stop):
    import signal
    import socket
    import time
    import urllib.request

    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\nwidth = 200\nheight = 100\n'
        f'[web]\naddress = "127.0.0.1"\nport = {port}\n'
        '[[plugin]]\nname = "Test"\ntype = "debugging"\nrefresh = 5\n'
    )
    state = tmp_path / "state"
    out = state / "screen"  # the default for --out
    out.mkdir(parents=True)
    (out / "0007.png").write_bytes(b"from an earlier run")
    health = tmp_path / "run" / "health"
    args = ["--config", str(cfg), "--state-dir", str(state), "--health-file", str(health)]
    # Stands in for systemd, which listens on this socket for "READY=1" and so on.
    systemd = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    systemd.bind(str(tmp_path / "notify"))
    systemd.settimeout(30)
    process = subprocess.Popen(
        [sys.executable, "-m", "paperpi", "run", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "NOTIFY_SOCKET": str(tmp_path / "notify")},
    )
    try:
        assert systemd.recv(100) == b"READY=1"
        assert systemd.recv(100) == b"WATCHDOG=1"
        assert main(["health", "--health-file", str(health)]) == 0
        # The web interface runs too; with no password yet, it asks for one.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30) as page:
            assert page.url.endswith("/setup")
        # The first write cleans the screen (0001.png, white), then draws (0002.png).
        deadline = time.monotonic() + 30
        while not (out / "0002.png").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert (out / "0002.png").exists()
        # (0001.png is complete once 0002.png exists; latest.png may be half written.)
        assert Image.open(out / "0001.png").getextrema() == (255, 255)
        assert Image.open(out / "0001.png").size == (200, 100)
        # A changed setting is applied on SIGHUP and redraws the screen; the web interface
        # gets its new settings too.
        text = cfg.read_text().replace("[web]\n", "[web]\nlogin = false\n")
        cfg.write_text(text + 'text = "changed"\n')
        process.send_signal(signal.SIGHUP)
        deadline = time.monotonic() + 30
        while not (out / "0003.png").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert (out / "0003.png").exists()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30) as page:
            assert page.url == f"http://127.0.0.1:{port}/"  # log-in is off now
        process.send_signal(getattr(signal, stop))
        stdout, stderr = process.communicate(timeout=30)
        # More "WATCHDOG=1" reports may come first, every 30 seconds.
        while (message := systemd.recv(100)) == b"WATCHDOG=1":
            pass
        assert message == b"STOPPING=1"
    finally:
        process.kill()
        systemd.close()
    assert process.returncode == 0, stderr
    assert not health.exists()  # removed when stopping on purpose
    assert "INFO: health: since_screen" in stderr  # the health values, in the log
    assert "showing 1 plugin;" in stdout
    assert f"web interface on port {port}" in stdout
    assert f"process id {process.pid}" in stdout
    assert not (out / "0007.png").exists()  # files of an earlier run are removed
    assert (state / "paperpi.last-good.toml").is_file()
    # Stopped on purpose: the screen is cleared (on_exit = "clear", the default).
    assert (out / "0004.png").exists()
    assert Image.open(out / "latest.png").getextrema() == (255, 255)


IT8951_CONFIG = (
    'config_version = 1\n[display]\ntype = "it8951"\nmodel = "9.7"\nvcom = -1.90\n'
    'max_refresh = 2\n{extra}[[plugin]]\nname = "Test"\ntype = "debugging"\n'
)


def test_driver_for_an_it8951_screen():
    from epdlib.drivers.it8951 import IT8951Driver

    from paperpi import config
    from paperpi.screen import driver_for

    display = config.parse(IT8951_CONFIG.format(extra="")).display
    make = driver_for(display, Path("unused"))
    assert make.func is IT8951Driver
    driver = make()  # makes no connection yet: that is init's job, in the helper process
    assert (driver.info.width, driver.vcom, driver.max_refresh) == (1200, -1.90, 2)


@pytest.mark.parametrize("on_exit, cleared", [("clear", True), ("keep", False)])
def test_run_with_an_it8951_screen(tmp_path, monkeypatch, capsys, on_exit, cleared):
    """A real screen type, with a pretend driver: no SPI or pins are used."""
    from functools import partial

    from .fake_screens import Pretend, notes

    made = []

    def pretend_driver(display, out):
        made.append(display)
        return partial(Pretend, tmp_path)

    monkeypatch.setattr(cli, "driver_for", pretend_driver)
    # The check at start, then a stop that was asked for.
    monkeypatch.setattr(cli.Scheduler, "run", lambda self: self.screen.check())
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(IT8951_CONFIG.format(extra=f'on_exit = "{on_exit}"\n'))
    args = ["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]
    assert main([*args, "--health-file", str(tmp_path / "health")]) == 0
    assert [(d.type, d.model, d.vcom) for d in made] == [("it8951", "9.7", -1.90)]
    assert "screen it8951" in capsys.readouterr().out
    steps = [what for _, what in notes(tmp_path)]
    assert steps == (["init", "clear", "close"] if cleared else ["init", "close"])


def test_run_exits_at_once_when_the_helper_is_stuck_while_clearing(tmp_path, monkeypatch):
    from paperpi.screen import Screen, ScreenStuck

    def stuck(self):
        raise ScreenStuck("the screen helper process 1234 can't be stopped")

    def exit_now(code):
        raise SystemExit(code)

    monkeypatch.setattr(cli.Scheduler, "run", lambda self: None)
    monkeypatch.setattr(Screen, "clear_before_exit", stuck)
    monkeypatch.setattr(cli.os, "_exit", exit_now)
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(GOOD)
    args = ["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]
    with pytest.raises(SystemExit) as ended:
        main([*args, "--health-file", str(tmp_path / "health")])
    assert ended.value.code == 1


def test_run_reloads_vcom_and_on_exit(tmp_path, monkeypatch):
    from functools import partial

    from .fake_screens import Pretend, notes

    made = []

    def pretend_driver(display, out):
        made.append(display.vcom)
        return partial(Pretend, tmp_path)

    cfg = tmp_path / "paperpi.toml"

    def run(self):
        self.screen.check()
        cfg.write_text(IT8951_CONFIG.format(extra='on_exit = "keep"\n').replace("-1.90", "-2.10"))
        self._apply(self._reload())

    monkeypatch.setattr(cli, "driver_for", pretend_driver)
    monkeypatch.setattr(cli.Scheduler, "run", run)
    cfg.write_text(IT8951_CONFIG.format(extra=""))
    args = ["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]
    assert main([*args, "--health-file", str(tmp_path / "health")]) == 0
    assert made == [-1.90, -2.10]  # a new driver for the new vcom
    assert "clear" not in [what for _, what in notes(tmp_path)]  # on_exit = "keep" now


def test_run_does_not_clear_the_screen_after_an_error(tmp_path, monkeypatch):
    from functools import partial

    from .fake_screens import Pretend, notes

    def broken(self):
        self.screen.check()
        raise RuntimeError("a bug")

    monkeypatch.setattr(cli, "driver_for", lambda display, out: partial(Pretend, tmp_path))
    monkeypatch.setattr(cli.Scheduler, "run", broken)
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(IT8951_CONFIG.format(extra=""))
    args = ["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]
    with pytest.raises(RuntimeError, match="a bug"):
        main([*args, "--health-file", str(tmp_path / "health")])
    assert [what for _, what in notes(tmp_path)] == ["init", "close"]


def test_health_command(tmp_path, capsys):
    path = tmp_path / "health"
    assert main(["health", "--health-file", str(path)]) == 1
    assert "PaperPi is not running" in capsys.readouterr().out


def test_run_with_broken_config(tmp_path, capsys):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text("not toml [")
    assert main(["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]) == 1
    assert "can't be used" in capsys.readouterr().err


def test_run_exits_at_once_when_a_screen_helper_is_stuck(tmp_path, monkeypatch, capsys):
    from paperpi.screen import ScreenStuck

    def stuck(self):
        raise ScreenStuck("the screen helper process 1234 can't be stopped")

    def exit_now(code):
        raise SystemExit(code)

    # os._exit, not a normal return: Python would wait for the stuck process at exit.
    monkeypatch.setattr(cli.Scheduler, "run", stuck)
    monkeypatch.setattr(cli.os, "_exit", exit_now)
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(GOOD)
    args = ["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]
    with pytest.raises(SystemExit) as ended:
        main([*args, "--health-file", str(tmp_path / "health")])
    assert ended.value.code == 1
    assert "1234 can't be stopped; exiting" in capsys.readouterr().err


def test_run_cleans_every_plugin_folder_at_start(tmp_path, monkeypatch):
    import time as clock

    from paperpi import storage

    monkeypatch.setattr(storage, "_changed", lambda info: info.st_mtime)
    monkeypatch.setattr(cli.Scheduler, "run", lambda self: None)
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        '[[plugin]]\nname = "Off"\ntype = "basic_clock"\nenabled = false\n'
    )
    old = tmp_path / "plugins" / "off" / "old.json"
    old.parent.mkdir(parents=True)
    old.write_text("{}")
    when = clock.time() - 400 * 24 * 60 * 60
    os.utime(old, (when, when))
    args = ["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]
    assert main([*args, "--health-file", str(tmp_path / "health")]) == 0
    assert not old.exists()


def test_run_counts_only_the_plugins_that_are_shown(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.Scheduler, "run", lambda self: None)
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        '[[plugin]]\nname = "Clock"\ntype = "basic_clock"\n'
        '[[plugin]]\nname = "Weather"\ntype = "met_no"\nlat = 1\nlon = 2\n'
    )
    args = ["run", "--no-web", "--config", str(cfg), "--state-dir", str(tmp_path)]
    assert main([*args, "--health-file", str(tmp_path / "health")]) == 0
    assert "showing 1 plugin;" in capsys.readouterr().out


def test_list_says_which_required_settings_are_missing(tmp_path, capsys):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        '[[plugin]]\nname = "Weather"\ntype = "met_no"\n'
        '[[plugin]]\nname = "Off"\ntype = "met_no"\nenabled = false\n'
    )
    assert main(["list", "--config", str(cfg)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].split()[:6] == ["Weather", "met_no", "needs", "lat,", "lon,", "email"]
    assert lines[2].split()[:3] == ["Off", "met_no", "no"]  # switched off: no "needs"


def test_render_live_says_which_required_settings_are_missing(capsys):
    assert main(["render", "met_no", "--live", "--set", "lat=1"]) == 2
    assert "met_no needs these required settings: --set lon=... --set email=..." in (
        capsys.readouterr().err
    )


def test_list_shows_no_age_limit(tmp_path, capsys):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        '[[plugin]]\nname = "Photos"\ntype = "basic_clock"\nstorage_days = 0\n'
    )
    assert main(["list", "--config", str(cfg)]) == 0
    assert capsys.readouterr().out.splitlines()[1].endswith("500 MB, no age limit")


def test_list_shows_the_plugins_as_used(capsys):
    example = Path(__file__).parent.parent / "paperpi.example.toml"
    assert main(["list", "--config", str(example)]) == 0
    lines = capsys.readouterr().out.splitlines()
    header = ["name", "type", "on", "level", "display", "refresh", "layout", "storage"]
    assert lines[0].split() == header
    assert lines[1].split() == "Clock basic_clock yes rotation 120 s 60 s time 500 MB, 30 d".split()
    assert lines[3].startswith("Weather Rio ")
    # Not shown until the user fills in their email address.
    assert lines[2].split()[:5] == ["Weather", "Berlin", "met_no", "needs", "email"]


def test_list_says_how_many_problems(tmp_path, capsys):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        '[[plugin]]\nname = "Clock"\ntype = "basic_clock"\nhours = 13\n'
    )
    assert main(["list", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "(no plugins)" in out
    assert "1 problem in the file, shown above" in out


def test_list_with_broken_config(tmp_path, capsys):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text("not toml [")
    assert main(["list", "--config", str(cfg)]) == 1
    assert "can't be used" in capsys.readouterr().err


def test_example_config_prints_or_saves_the_example(tmp_path, capsys):
    from paperpi.example import example_config

    assert main(["example-config"]) == 0
    assert capsys.readouterr().out == example_config()
    out = tmp_path / "example.toml"
    assert main(["example-config", "-o", str(out)]) == 0
    assert out.read_text() == example_config()


@pytest.mark.parametrize(
    ("web", "args", "started"),
    [("", [], True), ("[web]\nenabled = false\n", [], False), ("", ["--no-web"], False)],
)
def test_run_starts_the_web_interface_unless_asked_not_to(
    tmp_path, monkeypatch, web, args, started
):
    from paperpi.web import server

    calls = []
    monkeypatch.setattr(server, "start", lambda *a: calls.append(a))
    monkeypatch.setattr(cli.Scheduler, "run", lambda self: None)
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(f'config_version = 1\n[display]\ntype = "virtual"\n{web}')
    run = ["run", *args, "--config", str(cfg), "--state-dir", str(tmp_path)]
    assert main([*run, "--health-file", str(tmp_path / "health")]) == 0
    assert bool(calls) == started
