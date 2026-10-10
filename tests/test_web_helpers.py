"""Setting helpers on the settings page: the search box, the choices and Use (M5 part 3c)."""

import html
import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.helper import Found, HelperProblem, clean
from paperpi.runner import PluginFailed, PluginTimeout
from paperpi.web import auth
from paperpi.web.app import create_app
from paperpi.web.helpers import Searcher
from paperpi.web.plugins import PluginEditor

from .test_web_settings import PI

ID = "debugging-1a2b3c4d"
CONFIG = f"""\
config_version = 1
[display]
type = "virtual"

[[plugin]]
id = "{ID}"
type = "debugging"
"""
FORM = {"id": ID, "text": "typed"}


class FakeSearch:
    """Stands in for the plugin process: gives ``answer`` (a result, or an error to raise)
    and notes what it was asked."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, plugin_type, name, text, settings, *, time_limit):
        self.calls.append((plugin_type, name, text, settings, time_limit))
        if isinstance(self.answer, Exception):
            raise self.answer
        return clean(self.answer, ["text", "delay"])


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


def make_client(cfg, search=None):
    editor = PluginEditor(cfg)
    editor.loaded(CONFIG)
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=False))
    searcher = Searcher(search) if search else Searcher()
    app = create_app(paperpi_auth, editor, searcher=searcher)
    return TestClient(app, follow_redirects=False, base_url=PI)


def search(client, text, **form):
    """The page part a search gives."""
    sent = FORM | form | {"_search": text}
    return client.post("/plugins/0/search/text", data=sent).text


def uses(page):
    """What each Use button on ``page`` sends."""
    return [json.loads(v)["_use"] for v in re.findall(r"hx-vals='([^']*)'", page)]


def test_the_page_has_a_search_box_with_a_form_of_its_own(cfg):
    page = make_client(cfg).get("/plugins/0/settings", params={"id": ID}).text
    box = page[page.index('id="helper-text"') :]
    assert "Some words; each one becomes a choice" in box
    # Enter in the box searches (its own form) instead of saving the settings.
    assert 'name="_search" type="search" form="search-form-text"' in box
    assert '<form id="search-form-text" hx-post="/plugins/0/search/text"' in page
    assert 'hx-include="#settings-form"' in page and 'id="settings-form"' in page
    assert page.count('class="helper"') == 1  # only the setting that names a helper


def test_a_search_shows_the_choices_and_where_they_come_from(cfg):
    fake = FakeSearch(
        {
            "choices": [
                {
                    "fill": {"text": "Morrison"},
                    "show": {"Place": "Morrison", "Region": "Colorado <b>"},
                    "link": {"See on map": "https://www.openstreetmap.org/?mlat=39.65"},
                },
                {"show": {"Place": "Nothing to fill"}},
            ],
            "note": "2 places.",
        }
    )
    page = search(make_client(cfg, fake), "  Morrison, Colorado ")
    assert "<strong>Morrison</strong>" in page and "Region: Colorado &lt;b&gt;" in page
    assert '<a href="https://www.openstreetmap.org/?mlat=39.65" target="_blank"' in page
    assert "2 places." in page and "The debugging plugin" in page
    assert uses(page) == [json.dumps({"text": ["Morrison"]})]  # no Use without a fill
    plugin_type, name, text, settings, time_limit = fake.calls[0]
    assert (plugin_type, name, text, time_limit) == ("debugging", "words", "Morrison, Colorado", 30)
    assert settings.text == "typed"  # the form's values, as Save would write them


def test_nothing_found_and_more_than_shown(cfg):
    assert "Nothing found" in search(make_client(cfg, FakeSearch([])), "x")
    many = [{"show": {"Word": str(n)}} for n in range(12)]
    page = search(make_client(cfg, FakeSearch(many)), "x")
    assert page.count("<li>") == 10 and "Only the first 10 are shown" in page


@pytest.mark.parametrize(
    "answer, message",
    [
        (HelperProblem("The API key was not accepted."), "The API key was not accepted."),
        (PluginTimeout("debugging", "slow"), "The search took longer than 30 seconds"),
        (PluginFailed("debugging", "RuntimeError: boom"), "The search failed. PaperPi's log"),
        (RuntimeError("no process"), "The search failed. PaperPi's log"),
    ],
)
def test_a_failed_search_says_why(cfg, answer, message):
    page = search(make_client(cfg, FakeSearch(answer)), "x")
    page = html.unescape(page)
    assert message in page and "boom" not in page


def test_what_is_checked_before_searching(cfg):
    fake = FakeSearch([])
    client = make_client(cfg, fake)
    assert "Type what to search for first" in search(client, "   ")
    assert "at most 100 characters" in search(client, "x" * 101)
    page = search(client, "x", delay="soon")
    assert "Fix these settings first" in page and "<code>delay</code>" in page
    assert "has no search" in client.post("/plugins/0/search/delay", data=FORM).text
    assert "changed" in search(client, "x", id="other")
    assert not fake.calls


def test_one_search_at_a_time(cfg):
    started, go = threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        started.set()
        go.wait(5)
        return Found(())

    client = make_client(cfg, slow)
    first = threading.Thread(target=search, args=(client, "x"))
    first.start()
    try:
        assert started.wait(5)
        assert "Another search is running" in search(client, "y")
    finally:
        go.set()
        first.join()


def test_use_fills_in_the_fields_without_saving(cfg):
    client = make_client(cfg)
    page = client.post("/plugins/0/use/text", data=FORM | {"_use": '{"text": ["Morrison"]}'}).text
    assert "Filled in: text. Not saved yet" in page
    field = page[page.index('<div class="field"') :]
    assert 'id="field-text" hx-swap-oob="true"' in field
    assert 'name="text" type="text" value="Morrison"' in field
    assert cfg.read_text() == CONFIG


def test_use_shows_values_that_cant_be_used(cfg):
    client = make_client(cfg)
    page = client.post(
        "/plugins/0/use/text", data=FORM | {"_use": json.dumps({"text": ["x" * 101]})}
    )
    assert "some values can't be used" in page.text and 'class="problem"' in page.text


@pytest.mark.parametrize(
    "use",
    ["not json", "[1]", '{"text": "Morrison"}', '{"id": ["other"]}', '{"nope": ["x"]}'],
)
def test_use_refuses_what_a_use_button_doesnt_send(cfg, use):
    page = html.unescape(
        make_client(cfg).post("/plugins/0/use/text", data=FORM | {"_use": use}).text
    )
    assert "can't be used" in page or "nothing the form can fill in" in page
    assert "Filled in" not in page


def test_a_real_search_in_a_plugin_process(cfg):
    page = search(make_client(cfg), "hello world")
    assert "<strong>hello</strong>" in page and "Now: typed" in page
    assert uses(page) == [json.dumps({"text": ["hello"]}), json.dumps({"text": ["world"]})]
