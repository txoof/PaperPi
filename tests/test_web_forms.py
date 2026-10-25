from typing import Literal

import pytest
from pydantic import Field, SecretStr

from paperpi import plugins
from paperpi.plugin import Plugin, PluginSettings, ready, setting
from paperpi.web import forms

WEATHER = {"id": "w", "type": "met_no", "lat": 52.52, "display_time": 60}
T = {"id": "t", "type": "test"}


def by_key(found):
    return {f.key: f for f in found}


class Settings(PluginSettings):
    token: SecretStr = Field(SecretStr(""), description="API key")
    words: tuple[Literal["a", "b", "c"], ...] = Field(("a",), description="Words")
    part: dict[str, int] = Field({"x": 1}, description="A group of settings")
    loud: bool = Field(False, description="Loud")


TEST = Plugin(
    type="test",
    description="For the form tests",
    settings=Settings,
    layouts={"one": {"column": [{"name": "t", "type": "text"}]}},
    fetch=lambda context: ready(None),
    draw=lambda data, context: {},
    sample=None,
    refresh=60,
)


def test_fields_are_in_groups_in_the_agreed_order():
    found = forms.fields(plugins.load("met_no"), WEATHER)
    assert [f.key for f in found] == [
        "name",
        *["lat", "lon", "altitude", "place", "email", "temperature", "rain"],
        *["display_time", "refresh", "layout", "level"],
        *["time_limit", "alert_reminder", "alert_max_time", "storage_mb", "storage_days"],
    ]
    assert [f.group for f in found].count("more") == 5
    assert "id" not in by_key(found) and "enabled" not in by_key(found)


def test_fields_show_the_value_or_else_the_default():
    found = by_key(forms.fields(plugins.load("met_no"), WEATHER))
    assert (found["lat"].value, found["lat"].required) == ("52.52", True)
    assert (found["lat"].minimum, found["lat"].maximum, found["lat"].whole) == (-90, 90, False)
    assert found["lon"].value == ""  # not set, no default
    assert (found["display_time"].value, found["display_time"].default) == ("60", "120")
    assert found["refresh"].value == found["refresh"].default == "1800"  # the suggestion
    assert found["layout"].choices == tuple(plugins.load("met_no").layouts)
    # The layouts are shown by their titles; the default too.
    assert found["layout"].labels[:2] == ("Next 12 hours", "Small: right now")
    assert found["layout"].default == "Next 12 hours"
    assert found["temperature"].labels == ()
    assert found["temperature"].choices == ("C", "F")
    assert found["email"].max_length == 200
    assert found["storage_mb"].whole


def test_kinds_of_fields():
    found = by_key(forms.fields(TEST, {"token": "s3cret", "words": ["b", "c"]}))
    assert found["token"].kind == "secret" and found["token"].is_set
    assert found["token"].value == "" and found["token"].default == ""  # never on the page
    assert (found["words"].kind, found["words"].selected) == ("choices", ("b", "c"))
    assert (found["part"].kind, found["part"].value) == ("file", "{x = 1}")
    assert (found["loud"].kind, found["loud"].value) == ("check", "false")
    assert found["level"].kind == "choice"


def test_reading_a_form_gives_only_the_changes():
    found = forms.read(
        plugins.load("met_no"),
        WEATHER,
        {
            "name": ["Weather"],
            "lat": ["52.52"],  # the same
            "lon": [" 13.4 "],
            "temperature": ["F"],
            "display_time": ["120"],  # the default: out of the file
            "refresh": ["1800"],  # the suggestion: not set, as before
            "layout": ["small"],
        },
    )
    assert found.errors == {}
    assert found.changes == {
        "name": "Weather",
        "lon": 13.4,
        "temperature": "F",
        "display_time": None,
        "layout": "small",
    }


def test_an_empty_field_means_the_default():
    found = forms.read(plugins.load("met_no"), WEATHER, {"lat": [""], "display_time": [""]})
    assert found.changes == {"lat": None, "display_time": None}


def test_fields_left_out_of_the_form_stay_as_they_are():
    found = forms.read(plugins.load("met_no"), WEATHER, {})
    assert found.changes == {} and found.errors == {}


def test_choices_are_read_as_their_values():
    found = forms.read(
        plugins.load("basic_clock"), {"id": "c", "type": "basic_clock"}, {"hours": ["12"]}
    )
    assert found.changes == {"hours": 12}


@pytest.mark.parametrize(
    ("form", "errors"),
    [
        ({"lat": ["91"]}, {"lat": "Input should be less than or equal to 90"}),
        ({"lon": ["east"]}, {"lon": "enter a number"}),
        ({"storage_mb": ["1.5"]}, {"storage_mb": "enter a whole number"}),
        ({"temperature": ["K"]}, {"temperature": "choose one of: C, F"}),
        (
            {"layout": ["big"]},
            {"layout": "choose one of: " + ", ".join(plugins.load("met_no").layouts)},
        ),
        (
            {"email": ["not an address"]},
            {"email": "String should match pattern '^$|^[^@\\s]+@[^@\\s]+$'"},
        ),
        (
            {"name": ["a\tb"]},
            {"name": "must not hold control characters (such as tab or new line)"},
        ),
        (
            {"lat": ["91"], "lon": ["x"]},
            {"lat": "Input should be less than or equal to 90", "lon": "enter a number"},
        ),
    ],
)
def test_values_that_cant_be_used_give_an_error_each_and_no_changes(form, errors):
    found = forms.read(plugins.load("met_no"), WEATHER, form)
    assert found.errors == errors and found.changes == {}
    assert found.sent == form


def test_a_form_with_errors_shows_what_was_sent():
    sent = {"lat": ["91"], "temperature": ["F"]}
    found = by_key(forms.fields(plugins.load("met_no"), WEATHER, sent, {"lat": "too far"}))
    assert (found["lat"].value, found["lat"].error) == ("91", "too far")
    assert found["temperature"].value == "F"
    assert found["display_time"].value == "60"  # not sent: as in the file


def test_an_empty_secret_keeps_the_saved_one():
    assert forms.read(TEST, T | {"token": "s3cret"}, {"token": [""]}).changes == {}
    assert forms.read(TEST, T | {"token": "s3cret"}, {"token": ["new"]}).changes == {"token": "new"}


def test_check_boxes_and_lists_with_the_empty_value_the_page_sends():
    # The page sends "false" before each check box and "" before each list.
    block = T | {"loud": True, "words": ["b"]}
    found = forms.read(TEST, block, {"loud": ["false"], "words": ["", "a"]})
    assert found.changes == {"loud": None, "words": None}  # both back to their defaults
    found = forms.read(TEST, T, {"loud": ["false", "true"], "words": ["", "b", "c"]})
    assert found.changes == {"loud": True, "words": ("b", "c")}
    assert forms.read(TEST, block, {"words": [""]}).changes == {"words": ()}  # none
    assert forms.read(TEST, T, {"words": ["d"]}).errors == {"words": "choose from: a, b, c"}


def test_settings_of_a_kind_the_form_cant_show_are_never_changed():
    assert forms.read(TEST, T | {"part": {"x": 2}}, {"part": ["{x = 3}"]}).changes == {}


def test_required_settings_can_be_left_empty():
    # The plugin then waits for them (see paperpi.plugin.setting); the form says so.
    class Needs(PluginSettings):
        key: str = setting("", required=True, description="Key")

    plugin = Plugin(**{**TEST.__dict__, "settings": Needs})
    found = forms.read(plugin, T | {"key": "abc"}, {"key": [""]})
    assert found.errors == {} and found.changes == {"key": None}


def test_defaults_include_the_plugins_suggestions():
    weather = plugins.load("met_no")
    shown = forms.defaults(weather)
    assert shown["refresh"] == weather.refresh and shown["layout"] == weather.default_layout
    assert shown["display_time"] == 120 and shown["lat"] is None


def test_level_shows_and_keeps_the_plugins_suggestion():
    music = plugins.load("lms_client")
    block = {"id": "music", "type": "lms_client"}
    level = next(f for f in forms.fields(music, block) if f.key == "level")
    assert level.value == level.default == "interrupt" and not level.changed
    assert forms.read(music, block, {"level": ["interrupt"]}).changes == {}
    assert forms.read(music, block, {"level": ["rotation"]}).changes == {"level": "rotation"}
    assert forms.read(music, block | {"level": "rotation"}, {"level": [""]}).changes == {
        "level": None
    }


def test_unchanged_values_are_no_change():
    # The file gives a list and whole numbers; the form a tuple and text.
    block = T | {"words": ["b", "c"], "loud": True}
    form = {"words": ["", "b", "c"], "loud": ["false", "true"], "display_time": ["60"]}
    assert forms.read(TEST, block | {"display_time": 60.0}, form).changes == {}


def test_a_list_picks_each_choice_once():
    found = forms.read(TEST, T, {"words": ["", "c", "a", "c", "a"]})
    assert found.changes == {"words": ("a", "c")}


@pytest.mark.parametrize(
    "text", ["1_0", "nan", "inf", "1e3", "\N{ARABIC-INDIC DIGIT ONE}", "1" * 19, "0x10"]
)
def test_numbers_are_plain_digits(text):
    found = forms.read(plugins.load("met_no"), WEATHER, {"display_time": [text]})
    assert found.errors == {"display_time": "enter a number"}


def test_a_form_shown_again_keeps_check_boxes_and_lists_as_sent():
    sent = {"loud": ["false"], "words": ["", "c"]}
    found = by_key(forms.fields(TEST, T | {"loud": True}, sent, {"words": "x"}))
    assert found["loud"].value == "false"
    assert found["words"].selected == ("c",)
    found = by_key(forms.fields(TEST, T | {"loud": True}, {"words": [""]}, {"words": "x"}))
    assert found["loud"].value == "true"  # not sent: as saved
    assert found["words"].selected == ()


def test_a_secret_is_not_sent_back_with_errors():
    found = forms.read(TEST, T, {"token": ["NEWSECRET"], "words": ["d"]})
    assert found.errors and "token" not in found.sent
    assert "NEWSECRET" not in repr(found)


def test_a_default_written_in_the_file_stays_until_it_is_changed():
    block = WEATHER | {"display_time": 120}
    assert forms.read(plugins.load("met_no"), block, {"display_time": ["120"]}).changes == {}


class GroupSettings(PluginSettings):
    stop_1: str = setting("", group="Stop 1", description="Stop 1")
    walk_1: int = setting(0, group="Stop 1", description="Walk to stop 1")
    days_1: tuple[Literal["mon", "tue"], ...] = setting(
        ("mon", "tue"), group="Stop 1", description="Days"
    )
    key: SecretStr = setting(SecretStr(""), group="Key", description="API key")
    loud: bool = Field(False, description="Loud")
    stop_2: str = setting("", group="Stop 2", description="Stop 2")
    late: bool = setting(True, group="Stop 2", description="Show late ones")


GROUPED = Plugin(
    type="grouped",
    description="For the section tests",
    settings=GroupSettings,
    layouts={"one": {"column": [{"name": "t", "type": "text"}]}},
    fetch=lambda context: ready(None),
    draw=lambda data, context: {},
    sample=None,
    refresh=60,
)
G = {"id": "g", "type": "grouped"}


def grouped(block=G, sent=None, errors=None):
    return forms.sections(forms.fields(GROUPED, block, sent, errors))


def test_a_plugin_without_groups_keeps_the_plain_page():
    assert forms.sections(forms.fields(TEST, T)) is None


def test_the_weather_and_moon_plugins_group_the_place():
    _, own = forms.sections(forms.fields(plugins.load("met_no"), WEATHER))
    assert [f.key for f in own.fields] == ["email"]
    assert [s.title for s in own.subs] == ["Place", "Units"]
    _, own = forms.sections(
        forms.fields(plugins.load("moon_phase"), {"id": "m", "type": "moon_phase"})
    )
    assert [f.key for f in own.fields] == ["email"]
    assert [s.title for s in own.subs] == ["Place"]


def test_the_lms_plugin_keeps_server_and_player_in_view():
    _, own = forms.sections(
        forms.fields(plugins.load("lms_client"), {"id": "l", "type": "lms_client"})
    )
    assert [f.key for f in own.fields] == ["server", "player", "idle_timeout"]
    assert [s.title for s in own.subs] == ["Login"]


def test_sections_general_then_plugin_settings_with_a_sub_section_per_group():
    general, own = grouped()
    assert general.title == "General" and own.title == "Plugin settings"
    assert [f.key for f in general.fields] == ["name", "display_time", "refresh", "layout", "level"]
    (more,) = general.subs
    assert more.title == "Time limit, alerts, storage"
    assert [f.key for f in more.fields][:2] == ["time_limit", "alert_reminder"]
    # Settings without a group sit directly under the heading; groups in the code's order.
    assert [f.key for f in own.fields] == ["loud"]
    assert [s.title for s in own.subs] == ["Stop 1", "Key", "Stop 2"]
    assert [f.key for f in own.subs[0].fields] == ["stop_1", "walk_1", "days_1"]


def test_folded_headings_say_what_is_filled_in():
    block = G | {"name": "Home", "stop_1": "31001118", "walk_1": 6, "days_1": ["mon"]}
    general, own = grouped(block | {"key": "s3cret", "late": False, "loud": True})
    stop_1, key, stop_2 = own.subs
    assert (stop_1.mark, stop_1.line) == ("●", "31001118 · walk 6 · days: mon")
    assert (key.state, key.line) == ("set", "key set")  # never the secret itself
    assert stop_2.line == "no late"
    assert (own.state, own.line) == ("set", "loud · 3 of 3 parts set")
    assert general.line == "Home"
    assert "s3cret" not in str(grouped(block | {"key": "s3cret"}))


def test_a_heading_with_nothing_changed_says_empty_or_defaults():
    general, own = grouped()
    stop_1, key, stop_2 = own.subs
    # Every day ticked is no filter, so stop 1 is empty; stop 2 shows late ones by default.
    assert (stop_1.mark, stop_1.line) == ("○", "empty")
    assert (key.line, stop_2.line) == ("empty", "defaults")
    assert (own.state, own.line) == ("empty", "0 of 3 parts set")
    assert (general.state, general.line) == ("empty", "defaults")


def test_an_error_marks_its_section_and_the_one_around_it():
    sent = {"walk_1": ["x"], "stop_2": ["  "]}
    general, own = grouped(sent=sent, errors={"walk_1": "enter a whole number"})
    stop_1 = own.subs[0]
    assert (stop_1.errors, stop_1.mark, stop_1.line) == (1, "❗", "1 error · walk x")
    assert (own.state, own.line) == ("error", "1 error · 1 of 3 parts set")
    assert general.errors == 0
    # A field sent empty (or only spaces) is the default, so it is not filled in.
    assert not by_key(own.subs[2].fields)["stop_2"].changed


def test_the_layout_is_named_by_its_title_in_a_heading():
    weather = forms.fields(plugins.load("met_no"), WEATHER | {"layout": "steps_3h"})
    assert forms.summary(by_key(weather)["layout"]) == "Every 3 hours"
