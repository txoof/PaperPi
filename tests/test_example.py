"""Config text made from the settings (paperpi.example) and the plugin list."""

import dataclasses
import re
import tomllib
from pathlib import Path

import pytest
from pydantic import BaseModel, Field, SecretStr

from paperpi import config, plugins
from paperpi.example import example_config, plugin_block
from paperpi.plugin import PluginEntry, PluginSettings

EXAMPLE_FILE = Path(__file__).parent.parent / "paperpi.example.toml"
HEAD = 'config_version = 1\n[display]\ntype = "virtual"\n'


def test_example_file_is_up_to_date():
    assert EXAMPLE_FILE.read_text() == example_config(), (
        "paperpi.example.toml is out of date; make it again with "
        "uv run paperpi example-config -o paperpi.example.toml"
    )


def test_example_file_works_as_it_is():
    loaded = config.parse(EXAMPLE_FILE.read_text())
    # The weather blocks wait for the user's own email address (met.no's terms).
    assert [(p.level, p.message, p.where) for p in loaded.problems] == [
        ("warning", "not shown until these required settings are filled in: email", where)
        for where in ("[[plugin]] 'Weather Berlin'", "[[plugin]] 'Weather Rio'")
    ]
    assert [p.entry.name for p in loaded.plugins if p.shown] == ["Clock"]
    assert [(p.entry.name, p.plugin.type) for p in loaded.plugins] == [
        ("Clock", "basic_clock"),
        ("Weather Berlin", "met_no"),
        ("Weather Rio", "met_no"),
    ]
    assert loaded.plugin("Weather Rio").settings.place == "Rio"


def uncomment(text):
    """Remove the # in front of every setting that has a value, e.g. ``# hours = 24``."""
    return re.sub(r"^# (\w+ = .+)$", r"\1", text, flags=re.MULTILINE)


@pytest.mark.parametrize("plugin_type", plugins.available())
def test_every_default_shown_is_a_valid_setting(plugin_type):
    # Uncommenting every setting gives a block that loads without problems, so each
    # default is written correctly and is a setting the plugin really has.
    plugin = plugins.load(plugin_type)
    block = plugin_block(plugin, "Test", shared=True)
    loaded = config.parse(HEAD + uncomment(block))
    waits = [f"not shown until these required settings are filled in: {', '.join(plugin.required)}"]
    assert [p.message for p in loaded.problems if p.level != "hint"] == (
        waits if plugin.required else []
    )
    found = loaded.plugin("Test")
    assert found.settings == plugin.settings()
    assert found.refresh == plugin.refresh
    assert found.layout == plugin.default_layout
    assert (found.storage_mb, found.storage_days) == (plugin.storage_mb, plugin.storage_days)
    skip = {"name", "type", "refresh", "layout", "storage_mb", "storage_days"}
    default = PluginEntry(name="Test", type=plugin_type)
    assert found.entry.model_dump(exclude=skip) == default.model_dump(exclude=skip)


def test_every_default_in_the_example_is_valid():
    # Also the [display] part.
    loaded = config.parse(uncomment(example_config()))
    waiting = "not shown until these required settings are filled in: email"
    assert [p.message for p in loaded.problems if p.level != "hint"] == [waiting, waiting]
    assert loaded.display.size == config.DisplaySettings(type="virtual").size


@pytest.mark.parametrize("plugin_type", plugins.available())
def test_block_lists_every_setting_of_the_plugin(plugin_type):
    plugin = plugins.load(plugin_type)
    block = plugin_block(plugin, "Test")
    for key in plugin.settings.model_fields:
        assert re.search(rf"^# {key} =", block, re.MULTILINE), key
    assert f'# Layouts (values for "layout"): {", ".join(plugin.layouts)}' in block
    assert "# refresh =" in block and "# layout =" in block
    assert "display_time" not in block  # the other shared settings only with shared=True
    full = plugin_block(plugin, "Test", shared=True)
    for key in set(PluginEntry.model_fields) - {"name", "type"}:
        assert re.search(rf"^# {key} =", full, re.MULTILINE), key


def test_block_sets_the_values_given_and_says_what_each_setting_is():
    clock = plugins.load("basic_clock")
    block = plugin_block(clock, 'Clock "big"', {"hours": 12, "refresh": 120.0, "layout": None})
    assert 'name = "Clock \\"big\\""' in block
    assert "\n# 12-hour (3:45 PM) or 24-hour (15:45) clock\nhours = 12\n" in block
    assert "\nrefresh = 120\n" in block  # 120, not 120.0
    assert "# refresh =" not in block  # set, so not repeated as a comment
    assert '# layout = "time"' in block  # None: not set, shown with its default
    assert config.parse(HEAD + block).plugin('Clock "big"').settings.hours == 12


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"hours": 13}, "Input should be 12 or 24"),
        ({"houres": 12}, "basic_clock has no setting 'houres'; it has: hours, enabled"),
        ({"name": "Other"}, "has no setting 'name'"),
        ({"display_time": -1}, "greater than 0"),
        ({"layout": "nope"}, "basic_clock has no layout 'nope'"),
    ],
)
def test_block_refuses_values_the_plugin_would_not_accept(values, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        plugin_block(plugins.load("basic_clock"), "Clock", values)


def test_block_refuses_what_paperpi_could_not_read_back():
    # tomlkit writes the control character ESC in a form Python's TOML reader doesn't know.
    with pytest.raises(ValueError, match="control characters"):
        plugin_block(plugins.load("basic_clock"), "B\x1bad")
    with pytest.raises(ValueError, match="reads it back"):
        plugin_block(plugins.load("met_no"), "Weather", {"place": "B\x1bad"})


def test_config_file_refuses_control_characters_in_names():
    loaded = config.parse(HEAD + '[[plugin]]\nname = "A\\u001b[31m"\ntype = "basic_clock"\n')
    assert loaded.plugins == []
    assert "control characters" in loaded.problems[0].message


class Part(BaseModel):
    a: int = 1
    b: str = "x"


class Settings(PluginSettings):
    shade: str | None = Field(None, description="Colour")
    size: int = Field(3, description="How large. A very long help text that goes on and on " * 3)
    token: SecretStr = Field(SecretStr("default-secret"), description="API key")
    kinds: list[str] = Field(["a", "b"], description="Kinds")
    empty: list[str] = Field(default_factory=list, description="Made by a function")
    part: Part = Field(Part(), description="A group of settings")
    parts: list[Part] = Field([Part(a=2)], description="Several groups")


def test_values_without_default_long_help_secrets_lists_and_groups():
    plugin = dataclasses.replace(
        plugins.load("basic_clock"), settings=Settings, description="Two\nlines"
    )
    block = plugin_block(plugin, "Test", {"token": "my-key", "part": {"a": 5}})
    assert "\n# shade =\n" in block  # no value to show
    assert "default-secret" not in block  # a secret default is never written
    assert '\ntoken = "my-key"\n' in block  # a secret that is set is
    assert '\n# kinds = ["a", "b"]\n' in block
    assert "\n# empty = []\n" in block
    assert "\npart = {a = 5}\n" in block
    assert '\n# parts = [{a = 2, b = "x"}]\n' in block
    assert block.startswith("# basic_clock: Two lines\n")
    assert max(len(line) for line in block.splitlines()) <= 100  # long help is wrapped
    # Uncommented, the block reads back as valid settings (it is not a real plugin, so it
    # is checked here, not by loading a config).
    read = tomllib.loads(uncomment(block))["plugin"][0]
    settings = Settings.model_validate(
        {k: v for k, v in read.items() if k in Settings.model_fields}
    )
    assert settings.part == Part(a=5)
    assert settings.parts == [Part(a=2)]
    assert settings.empty == []


def test_choices_are_listed_when_the_help_does_not_name_them():
    text = example_config()
    assert "# Turn the picture, in degrees. One of: 0, 90, 180, 270\n# rotation = 0" in text
    assert "# When it is shown: alert, interrupt or rotation\n" in text  # named already
    assert 'what it can show. One of: "bw", "gray4", "gray16", "7color", "rgb"\n' in text
    # "C" is in "Celsius", but not as a word of its own.
    assert '# Degrees Celsius or Fahrenheit. One of: "C", "F"\n' in text
    assert "\n# display_time = 120\n" in text  # 120, not 120.0


def test_plugin_rows():
    text = (
        HEAD
        + '[[plugin]]\nname = "Clock"\ntype = "basic_clock"\n'
        + '[[plugin]]\nname = "Big"\ntype = "basic_clock"\nenabled = false\nrefresh = 300\n'
        + 'layout = "time_date"\ndisplay_time = 90\nlevel = "interrupt"\n'
        + "storage_mb = 20000\nstorage_days = 0\n"
        + '[[plugin]]\nname = "Broken"\ntype = "basic_clock"\nhours = 13\n'
    )
    rows = config.plugin_rows(config.parse(text))
    assert rows == [
        config.PluginRow("Clock", "basic_clock", True, "rotation", 120, 60, "time", 500, 30),
        config.PluginRow("Big", "basic_clock", False, "interrupt", 90, 300, "time_date", 20000, 0),
    ]


def test_block_marks_the_required_settings():
    block = plugin_block(plugins.load("met_no"), "Weather", {"lat": 1, "lon": 2})
    assert "# Latitude of the place, e.g. 52.52 (required)\nlat = 1\n" in block
    assert 'way to contact its user (required)\n# email = ""\n' in block
    assert "Berlin (else lat, lon)\n# place" in block  # not required
