"""The plugin interface rules (paperpi.plugin) and the plugin loader."""

import pytest
from epdlib import ScreenMode
from pydantic import Field, SecretBytes, SecretStr

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
    is_required,
    is_set,
    ready,
    setting,
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


class RequiredWithValue(PluginSettings):
    email: str = setting("me@example.com", required=True)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"type": "Bad Name"}, "type must be lowercase"),
        ({"settings": NotSettings}, "subclass of PluginSettings"),
        ({"settings": Clash}, "names of shared settings: name, refresh"),
        ({"settings": NoDefault}, "every setting needs a default"),
        ({"settings": RequiredWithValue}, 'a required setting\'s default must be "not set"'),
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


def test_recolor_reaches_nested_blocks_and_keeps_the_original():
    from paperpi.plugin import _recolor

    layout = {
        "column": (
            {
                "row": [
                    {"name": "a", "rgb_support": True},
                    {"name": "b", "rgb_support": True, "inverse": True},
                ]
            },
            {"name": "c"},
        )
    }
    new = _recolor(layout, "yellow", "blue")
    a, b = new["column"][0]["row"]
    assert (a["fill"], a["background"]) == ("yellow", "blue")
    assert (b["fill"], b["background"]) == ("blue", "yellow")  # inverse swaps them back
    assert "fill" not in new["column"][1]
    assert isinstance(new["column"], tuple)
    assert "fill" not in layout["column"][0]["row"][0]  # the original is unchanged


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


class Needs(PluginSettings):
    place: str = setting("", required=True, max_length=10, description="Where")
    lat: float | None = setting(None, required=True, ge=-90, le=90)
    key: SecretStr = setting(SecretStr(""), required=True)
    word: str = setting("hi")


def test_setting_is_a_field_with_paperpis_options():
    fields = Needs.model_fields
    assert [k for k, info in fields.items() if is_required(info)] == ["place", "lat", "key"]
    assert not is_required(fields["word"])
    assert fields["place"].description == "Where"
    with pytest.raises(ValueError, match="at most 10 characters"):
        Needs(place="far too long a place")
    with pytest.raises(ValueError, match="less than or equal to 90"):
        Needs(lat=91)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("", False), ("  ", False), (SecretStr(""), False), (SecretStr(" "), False),
     (SecretBytes(b""), False), (b"", False), ("x", True), (0, True), (0.0, True),
     (SecretStr("k"), True), (False, True)],
)  # fmt: skip
def test_is_set(value, expected):
    assert is_set(value) is expected


def test_setting_keeps_other_schema_extras():
    class Extra(PluginSettings):
        word: str = setting("", required=True, json_schema_extra={"examples": ["hi"]})
        other: str = setting("", json_schema_extra={"paperpi": "wrong shape"})

    info = Extra.model_fields["word"]
    assert info.json_schema_extra == {"examples": ["hi"], "paperpi": {"required": True}}
    assert is_required(info)
    assert not is_required(Extra.model_fields["other"])  # no crash on a wrong shape


def test_setting_needs_a_default():
    with pytest.raises(TypeError):
        setting(description="no default")


def test_built_in_plugins_need_no_settings():
    # PaperPi runs these with their defaults (the screen shown when nothing else can be).
    for plugin_type in ("basic_clock", "default"):
        assert plugins.load(plugin_type).required == ()


def test_missing_lists_the_required_settings_that_are_not_set():
    plugin = make(settings=Needs)
    assert plugin.required == ("place", "lat", "key")
    assert plugin.missing(Needs()) == ("place", "lat", "key")
    assert plugin.missing(Needs(place="Rio", lat=0, key=SecretStr("k"))) == ()
    assert make().required == ()


@pytest.mark.parametrize("plugin_type", ["met_no", "moon_phase"])
def test_met_no_plugins_need_a_place_and_an_email_address(plugin_type):
    # met.no's terms of service ask for a real way to contact the user.
    assert plugins.load(plugin_type).required == ("lat", "lon", "email")
