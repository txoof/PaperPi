"""The paperpi command (paperpi.cli)."""

import subprocess
import sys

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


def test_run_shows_plugins_reloads_and_stops(tmp_path):
    import signal
    import time

    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\nwidth = 200\nheight = 100\n'
        '[[plugin]]\nname = "Test"\ntype = "debugging"\nrefresh = 1\n'
    )
    out, state = tmp_path / "screen", tmp_path / "state"
    args = ["--config", str(cfg), "--out", str(out), "--state-dir", str(state)]
    process = subprocess.Popen(
        [sys.executable, "-m", "paperpi", "run", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not (out / "latest.png").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert (out / "latest.png").exists()
        assert Image.open(out / "latest.png").size == (200, 100)
        # A changed setting is applied on SIGHUP and redraws the screen.
        cfg.write_text(cfg.read_text() + 'text = "changed"\n')
        process.send_signal(signal.SIGHUP)
        deadline = time.monotonic() + 30
        while not (out / "0002.png").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert (out / "0002.png").exists()
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=30)
    finally:
        process.kill()
    assert process.returncode == 0, stderr
    assert "showing 1 plugin;" in stdout
    assert (state / "paperpi.last-good.toml").is_file()


def test_run_with_broken_config(tmp_path, capsys):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text("not toml [")
    assert main(["run", "--config", str(cfg), "--state-dir", str(tmp_path)]) == 1
    assert "can't be used" in capsys.readouterr().err
