"""Setting helpers: the plugin's side (paperpi.helper, the plugin check, run_helper)."""

import pytest
from pydantic import SecretStr

from paperpi import limits, plugins, runner
from paperpi.helper import Found, Helper, HelperProblem, clean
from paperpi.plugin import PluginDefinitionError, PluginSettings, setting
from paperpi.runner import PluginFailed, PluginTimeout, run_helper

from .test_plugin import make as make_plugin

SETTINGS = ["lat", "lon", "place"]


def choice(**kinds):
    return {"show": {"Place": "Morrison"}} | kinds


def test_a_list_of_choices_is_checked():
    found = clean(
        [
            choice(
                fill={"lat": 39.6536, "lon": -105.1911}, link={"See on map": "https://osm.org/"}
            ),
            {"show": {"Place": "Morrison", "Region": "Illinois"}},
        ],
        SETTINGS,
    )
    first, second = found.choices
    assert first.heading == "Morrison" and first.fill == {"lat": 39.6536, "lon": -105.1911}
    assert first.links == (("See on map", "https://osm.org/"),)
    assert second.show == (("Place", "Morrison"), ("Region", "Illinois")) and not second.fill
    assert found == Found(found.choices)  # no note, no more, nothing left out


def test_a_result_can_have_a_note_and_only_the_first_choices_are_kept():
    many = [choice(fill={"place": str(n)}) for n in range(limits.HELPER_CHOICES + 2)]
    found = clean({"choices": many, "note": "Many places."}, SETTINGS)
    assert len(found.choices) == limits.HELPER_CHOICES and found.more
    assert found.note == "Many places."
    assert clean({"note": "Nothing here."}, SETTINGS) == Found((), "Nothing here.")


def test_unknown_kinds_and_other_links_are_left_out_and_noted():
    found = clean(
        {
            "choices": [choice(add={"stops": "3104"}, link={"Bad": "javascript:alert(1)"})],
            "wait": 5,
        },
        SETTINGS,
    )
    assert found.choices[0].links == ()
    assert found.left_out == (
        "result kind 'wait'",
        "choice kind 'add'",
        "link 'javascript:alert(1)' (only http and https)",
    )


def test_texts_are_made_short_and_on_one_line():
    found = clean([{"show": {"Place": "Morrison\n  Colorado", "Long": "x" * 500}}], SETTINGS)
    (_, place), (_, long) = found.choices[0].show
    assert place == "Morrison Colorado" and len(long) == 200 and long.endswith("…")


@pytest.mark.parametrize(
    "result, message",
    [
        ("Morrison", "list of choices"),
        ([["Morrison"]], "choice 1 is not a dictionary"),
        ([{"fill": {"lat": 1}}], "choice 1 has nothing to show"),
        ([choice(fill={"altitude": 1757})], "fills settings it doesn't have: altitude"),
        ([choice(fill=[1])], "fill must be a dictionary"),
        ([choice(link="https://osm.org/")], "link must be a dictionary"),
        ({"choices": [], "note": 5}, "note must be text"),
    ],
)
def test_a_result_that_breaks_the_rules_is_a_bug_in_the_plugin(result, message):
    with pytest.raises(TypeError, match=message):
        clean(result, SETTINGS)


class PlaceSettings(PluginSettings):
    lat: float | None = setting(None, helper="location")
    key: SecretStr = setting(SecretStr(""))


def find(query):
    return []


@pytest.mark.parametrize(
    "helpers, message",
    [
        ({}, "setting 'lat' names helper 'location', which it doesn't have"),
        ({"location": find}, "helper 'location' must be a Helper"),
        (
            {"location": Helper(find, "Place", needs=("api_key",))},
            "needs settings it doesn't have: \\['api_key'\\]",
        ),
        (
            {"location": Helper(find, "Place", source_link="ftp://x")},
            "source_link must start with http or https",
        ),
        ([], "helpers must be a dictionary"),
    ],
)
def test_the_plugin_check_catches_wrong_helpers(helpers, message):
    with pytest.raises(PluginDefinitionError, match=message):
        make_plugin(settings=PlaceSettings, helpers=helpers)


def test_a_plugin_finds_the_helper_of_a_setting():
    helper = Helper(find, "Place", needs=("key",), source_link="https://open-meteo.com/")
    plugin = make_plugin(settings=PlaceSettings, helpers={"location": helper})
    assert plugin.helper("lat") is helper
    assert plugin.helper("key") is None and plugin.helper("nope") is None


# --- In a real plugin process, with the debugging plugin's "words" helper -------------------


@pytest.fixture
def words():
    return plugins.load("debugging").settings(text="now")


def test_run_helper_returns_the_checked_choices(words):
    found = run_helper("debugging", "words", "hello world", words)
    assert [c.heading for c in found.choices] == ["hello", "world"]
    assert found.choices[0].fill == {"text": "hello"}
    assert dict(found.choices[0].show)["Now"] == "now"  # the form's settings reached it
    assert found.note == "2 words."


def test_run_helper_reports_a_problem_an_error_and_a_hang(words):
    with pytest.raises(HelperProblem, match="A problem, as asked"):
        run_helper("debugging", "words", "problem", words)
    with pytest.raises(PluginFailed, match="RuntimeError: crash, as asked"):
        run_helper("debugging", "words", "crash", words)
    with pytest.raises(PluginTimeout):
        run_helper("debugging", "words", "hang", words, time_limit=1)


def test_run_helper_hides_secret_settings_in_its_messages(monkeypatch):
    class Secret(PluginSettings):
        key: SecretStr = setting(SecretStr(""))

    def leak(query):
        raise HelperProblem(f"key {query.settings.key.get_secret_value()} refused")

    plugin = make_plugin(settings=Secret, helpers={"leak": Helper(leak, "Key")})
    settings = Secret(key=SecretStr("TOPSECRET"))
    # In this process (the fake plugin can't be imported in another one), as the child would.
    sender = Sender()
    monkeypatch.setattr(plugins, "load", lambda plugin_type, package: plugin)
    monkeypatch.setattr(runner.os, "setpgrp", lambda: None)
    runner._helper_child(sender, "fake", "tests", "leak", "", settings.model_dump())
    assert sender.sent == [("problem", "key **** refused")]


class Sender:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)

    def close(self):
        pass
