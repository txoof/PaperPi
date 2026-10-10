"""Setting helpers on the settings page: the search box, the choices and Use (M5 part 3c)."""

import html
import json
import re
import threading

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from paperpi import config
from paperpi.helper import Found, Helper, HelperProblem, clean
from paperpi.plugin import Plugin, PluginSettings, ready, setting
from paperpi.runner import PluginFailed, PluginTimeout
from paperpi.web import auth
from paperpi.web import plugins as web_plugins
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


def make_client(cfg, search=None, searcher=None):
    editor = PluginEditor(cfg)
    editor.loaded(cfg.read_text())
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=False))
    searcher = searcher or (Searcher(search) if search else Searcher())
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
    # The search comes first, then the fields it fills.
    assert page.index('id="helper-text"') < page.index('id="field-text"')


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
    assert "The config file changed after this page was opened" in search(client, "x", id="o")
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
    "key, use, message",
    [
        ("text", "not json", "This choice can't be used"),
        ("text", "[1]", "This choice can't be used"),
        ("text", '{"text": "Morrison"}', "This choice can't be used"),
        ("text", "[" * 200_000, "This choice can't be used"),  # too long, and nested too deeply
        ("text", '{"id": ["other"]}', "nothing the form can fill in"),
        ("text", '{"refresh": ["60"]}', "nothing the form can fill in"),  # a shared setting
        ("delay", '{"text": ["x"]}', "The setting 'delay' has no search"),
    ],
)
def test_use_refuses_what_a_use_button_doesnt_send(cfg, key, use, message):
    sent = FORM | {"_use": use}
    page = html.unescape(make_client(cfg).post(f"/plugins/0/use/{key}", data=sent).text)
    assert message in page and "Filled in" not in page


def test_no_search_once_paperpi_stops(cfg):
    fake = FakeSearch([])
    searcher = Searcher(fake)
    client = make_client(cfg, searcher=searcher)
    searcher.stop()
    assert "PaperPi is stopping" in search(client, "x") and not fake.calls


class FinderSettings(PluginSettings):
    key: SecretStr = setting(SecretStr(""), description="API key")
    server: str = setting("", helper="servers", description="Music server")


FINDER = Plugin(
    type="finder",
    description="Finds servers",
    settings=FinderSettings,
    layouts={"one": {"column": [{"name": "t", "type": "text"}]}},
    fetch=lambda context: ready(None),
    draw=lambda data, context: {},
    sample=None,
    refresh=60,
    helpers={
        "servers": Helper(
            lambda query: [], "Finds the servers", "Find servers", typed=False, needs=("key",)
        )
    },
)


@pytest.fixture
def finder(cfg, monkeypatch):
    """A plugin block (place 1) whose helper needs no typed text but an API key first."""
    real_load, real_available = web_plugins.plugins.load, web_plugins.plugins.available
    monkeypatch.setattr(web_plugins.plugins, "available", lambda: [*real_available(), "finder"])
    monkeypatch.setattr(
        web_plugins.plugins, "load", lambda t: FINDER if t == "finder" else real_load(t)
    )
    cfg.write_text(CONFIG + '\n[[plugin]]\nid = "finder-1"\ntype = "finder"\n')
    return cfg


def find_servers(client, **form):
    sent = {"id": "finder-1", "_search": "typed by hand"} | form
    return html.unescape(client.post("/plugins/1/search/server", data=sent).text)


def test_a_helper_without_typed_text_has_only_a_button(finder):
    page = make_client(finder).get("/plugins/1/settings", params={"id": "finder-1"}).text
    box = page[page.index('id="helper-server"') :]
    assert "<p>Finds the servers</p>" in box and ">Find servers</button>" in box
    assert 'name="_search"' not in box


def test_settings_a_helper_needs_come_first(finder):
    fake = FakeSearch([])
    client = make_client(finder, fake)
    assert "Fill in these settings first: key." in find_servers(client)
    assert not fake.calls
    find_servers(client, key="TYPED")
    ((_, name, text, settings, _),) = fake.calls
    assert (name, text, settings.key.get_secret_value()) == ("servers", "", "TYPED")
    # An empty secret field keeps the saved key, which is enough.
    finder.write_text(finder.read_text() + 'key = "SAVED"\n')
    find_servers(client)
    assert fake.calls[-1][3].key.get_secret_value() == "SAVED"


def test_a_real_search_in_a_plugin_process(cfg):
    page = search(make_client(cfg), "hello world")
    assert "<strong>hello</strong>" in page and "Now: typed" in page
    assert uses(page) == [json.dumps({"text": ["hello"]}), json.dumps({"text": ["world"]})]


def test_what_a_search_left_out_goes_to_the_log(cfg, caplog):
    fake = FakeSearch([{"show": {"Word": "x"}, "wait": 5}])
    with caplog.at_level("INFO", logger="paperpi.web.helpers"):
        search(make_client(cfg, fake), "x")
    assert f"search of {ID} left out: choice kind 'wait'" in caplog.text
