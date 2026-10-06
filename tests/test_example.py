"""Config text made from the settings (paperpi.example) and the plugin list."""

import dataclasses
import re
from pathlib import Path

import pytest
from pydantic import Field, SecretStr

from paperpi import config, plugins
from paperpi.example import example_config, plugin_block
from paperpi.plugin import PluginSettings

EXAMPLE_FILE = Path(__file__).parent.parent / "paperpi.example.toml"
HEAD = 'config_version = 1\n[display]\ntype = "virtual"\n'


def test_example_file_is_up_to_date():
    assert EXAMPLE_FILE.read_text() == example_config(), (
        "paperpi.example.toml is out of date; make it again with "
        "uv run paperpi example-config -o paperpi.example.toml"
    )


def test_example_file_works_as_it_is():
    loaded = config.parse(EXAMPLE_FILE.read_text())
    assert loaded.problems == []
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
    assert [p.level for p in loaded.problems if p.level != "hint"] == []
    found = loaded.plugin("Test")
    assert found.settings == plugin.settings()
    assert found.refresh == plugin.refresh
    assert found.layout == plugin.default_layout


@pytest.mark.parametrize("plugin_type", plugins.available())
def test_block_lists_every_setting_of_the_plugin(plugin_type):
    plugin = plugins.load(plugin_type)
    block = plugin_block(plugin, "Test")
    for key in plugin.settings.model_fields:
        assert re.search(rf"^# {key} =", block, re.MULTILINE), key
    assert f"# Layouts: {', '.join(plugin.layouts)}" in block
    assert "# refresh =" in block and "# layout =" in block
    assert "display_time" not in block  # the other shared settings only with shared=True


def test_block_sets_the_values_given_and_says_what_each_setting_is():
    block = plugin_block(plugins.load("basic_clock"), 'Clock "big"', {"hours": 12, "refresh": 120})
    assert 'name = "Clock \\"big\\""' in block
    assert "\n# 12-hour (3:45 PM) or 24-hour (15:45) clock\nhours = 12\n" in block
    assert "\nrefresh = 120\n" in block  # 120, not 120.0
    assert "# refresh =" not in block  # set, so not repeated as a comment
    assert config.parse(HEAD + block).plugin('Clock "big"').settings.hours == 12


class Settings(PluginSettings):
    shade: str | None = Field(None, description="Colour")
    size: int = Field(3, description="How large. A very long help text that goes on and on " * 3)
    token: SecretStr = Field(SecretStr(""), description="API key")
    kinds: list[str] = Field(["a", "b"], description="Kinds")


def test_values_without_default_long_help_secrets_and_lists():
    plugin = dataclasses.replace(plugins.load("basic_clock"), settings=Settings)
    block = plugin_block(plugin, "Test")
    assert "\n# shade =\n" in block  # no value to show
    assert '\n# token = ""\n' in block
    assert '\n# kinds = ["a", "b"]\n' in block
    assert max(len(line) for line in block.splitlines()) <= 100  # long help is wrapped


def test_choices_are_listed_when_the_help_does_not_name_them():
    text = example_config()
    assert "# Turn the picture, in degrees. One of: 0, 90, 180, 270\n# rotation = 0" in text
    assert "# When it is shown: alert, interrupt or rotation\n" in text  # named already


def test_plugin_rows():
    text = (
        HEAD
        + '[[plugin]]\nname = "Clock"\ntype = "basic_clock"\n'
        + '[[plugin]]\nname = "Big"\ntype = "basic_clock"\nenabled = false\nrefresh = 300\n'
        + 'layout = "time_date"\ndisplay_time = 90\nlevel = "interrupt"\n'
        + '[[plugin]]\nname = "Broken"\ntype = "basic_clock"\nhours = 13\n'
    )
    rows = config.plugin_rows(config.parse(text))
    assert rows == [
        config.PluginRow("Clock", "basic_clock", True, "rotation", 120, 60, "time"),
        config.PluginRow("Big", "basic_clock", False, "interrupt", 90, 300, "time_date"),
    ]
