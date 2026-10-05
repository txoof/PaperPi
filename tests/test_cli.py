"""The paperpi command (paperpi.cli)."""

import subprocess
import sys

import pytest
from PIL import Image

from paperpi.cli import main

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
