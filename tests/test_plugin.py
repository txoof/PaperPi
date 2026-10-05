"""The plugin interface rules (paperpi.plugin) and the plugin loader."""

import pytest
from epdlib import ScreenMode
from pydantic import Field

from paperpi import plugins
from paperpi.plugin import (
    NOTHING,
    Context,
    Drawn,
    Plugin,
    PluginDefinitionError,
    PluginSettings,
    State,
    draw_update,
    ready,
)


class Settings(PluginSettings):
    word: str = Field("hi", description="what to show")


def make(**changes) -> Plugin:
    options = dict(
        type="demo",
        description="Demo.",
        settings=Settings,
        layouts={"one": {"column": [{"name": "text", "type": "text"}]}},
        fetch=lambda context: ready(context.settings.word),
        draw=lambda word, context: {"text": word},
        sample="sample",
        refresh=60,
    )
    return Plugin(**(options | changes))


def context(tmp_path, plugin=None):
    plugin = plugin or make()
    return Context(plugin.settings(), 100, 50, ScreenMode.bw(), tmp_path, plugin.default_layout)


def test_a_good_plugin():
    plugin = make()
    assert plugin.default_layout == "one"


class Clash(PluginSettings):
    name: str = "x"
    refresh: int = 1


class NoDefault(PluginSettings):
    word: str


class NotSettings:
    pass


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"type": "Bad Name"}, "type must be lowercase"),
        ({"settings": NotSettings}, "subclass of PluginSettings"),
        ({"settings": Clash}, "names of shared settings: name, refresh"),
        ({"settings": NoDefault}, "every setting needs a default"),
        ({"layouts": {}}, "at least one layout"),
        ({"refresh": 0}, "refresh must be between 5 and 604800 seconds"),
        ({"refresh": 4.9}, "refresh must be between 5 and 604800 seconds"),
    ],
)
def test_plugin_rules(changes, message):
    with pytest.raises(PluginDefinitionError, match=message):
        make(**changes)


def test_draw_update_fetches_and_draws(tmp_path):
    state, image = draw_update(make(), context(tmp_path), sample=False)
    assert state is State.READY
    assert image.size == (100, 50)
    assert image.mode == "1"


def test_draw_update_with_nothing(tmp_path):
    plugin = make(fetch=lambda context: NOTHING)
    assert draw_update(plugin, context(tmp_path, plugin), sample=False) == (State.NOTHING, None)


def test_layout_can_depend_on_settings(tmp_path):
    def layout(settings):
        return {"column": [{"name": "text", "type": "text", "sample": settings.word}]}

    plugin = make(layouts={"one": layout})
    state, image = draw_update(plugin, context(tmp_path, plugin), sample=True)
    assert state is State.READY


def test_drawn_seed_makes_random_placement_repeatable(tmp_path):
    layouts = {
        "one": {
            "column": [
                {
                    "name": "text",
                    "type": "text",
                    "align": "random",
                    "valign": "random",
                    "font_size": 0.2,
                }
            ]
        }
    }

    def image(seed):
        plugin = make(layouts=layouts, draw=lambda word, context: Drawn({"text": "x"}, seed=seed))
        return draw_update(plugin, context(tmp_path, plugin), sample=True)[1].tobytes()

    assert image(1) == image(1)
    assert image(1) != image(2)


def test_drawn_colors_change_only_rgb_support_blocks(tmp_path):
    layouts = {
        "one": {
            "row": [
                {"name": "a", "type": "text", "rgb_support": True},
                {"name": "b", "type": "text"},
            ],
            "gap": 0,
        }
    }
    plugin = make(layouts=layouts, draw=lambda word, context: Drawn({}, colors=("white", "black")))
    ctx = Context(Settings(), 100, 50, ScreenMode.gray(16), tmp_path, "one")
    image = draw_update(plugin, ctx, sample=True)[1].convert("L")
    assert image.getpixel((0, 0)) == 0  # block a: black background
    assert image.getpixel((99, 0)) == 255  # block b: still white


def test_loader_lists_and_loads_the_plugins():
    assert "basic_clock" in plugins.available()
    assert plugins.load("basic_clock").type == "basic_clock"


def test_loader_unknown_type():
    with pytest.raises(KeyError):
        plugins.load("../etc")


@pytest.mark.parametrize(
    ("plugin_type", "message"),
    [("no_plugin", "has no PLUGIN"), ("wrong_type", "PLUGIN.type is 'other_name'")],
)
def test_loader_broken_plugins(plugin_type, message):
    with pytest.raises(PluginDefinitionError, match=message):
        plugins.load(plugin_type, "tests.fake_plugins")
