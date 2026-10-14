"""The Warnings tab (paperpi.web.warnings, /warnings in paperpi.web.app)."""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.logbook import Logbook
from paperpi.scheduler import PluginSummary, Summary
from paperpi.web import auth, warnings
from paperpi.web.app import create_app
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
type = "virtual"

[[plugin]]
id = "Clock"
type = "basic_clock"

[[plugin]]
id = "Comic"
type = "xkcd_comic"

[[plugin]]
id = "Weather"
type = "met_no"
lat = 52.52
lon = 13.40

[[plugin]]
id = "Rio"
type = "met_no"
lat = "far south"
lon = -43.2
email = "someone@example.com"
"""
PI = "http://192.168.1.20:8080"
HTMX = {"HX-Request": "true"}
TODAY = date(2026, 10, 14)


@dataclass
class FakeScheduler:
    summary: Summary = field(default_factory=Summary)
    asked: list = field(default_factory=list)

    def try_again(self, plugin_id=None):
        self.asked.append(("try_again", plugin_id))

    def reload(self):
        self.asked.append(("reload",))


def add(book, level, text, when=None, source="paperpi.scheduler"):
    record = logging.makeLogRecord(
        {"name": source, "levelno": logging.getLevelName(level), "levelname": level}
    )
    if when is not None:
        record.created = when.timestamp()
    book.add(record, text)


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def scheduler():
    return FakeScheduler()


@pytest.fixture
def book(tmp_path):
    book = Logbook(None)
    add(book, "INFO", "show now: 'Clock'")
    add(book, "WARNING", "plugin 'Comic' failed: could not reach xkcd.com <timed out>")
    add(book, "ERROR", "screen write failed: busy pin")
    return book


def client(cfg, scheduler=None, book=None):
    app = create_app(
        auth.Auth(cfg, config.WebSettings(login=False)),
        PluginEditor(cfg),
        controls=scheduler,
        logbook=book,
    )
    return TestClient(app, follow_redirects=False, base_url=PI)


def rows(cfg):
    return PluginEditor(cfg).plugin_list().rows


def paused_comic(**changes):
    plugins = (
        PluginSummary("Clock", "on_screen"),
        PluginSummary(
            "Comic",
            "paused",
            error="The website did not answer.",
            paused_until=datetime(2026, 10, 14, 14, 30),
        ),
        PluginSummary("Weather", "needs_settings", missing=("email",)),
    )
    return Summary(on_screen="Clock", screen="ok", plugins=plugins, **changes)


def test_nothing_needs_attention_when_all_is_well(cfg):
    good = cfg.read_text().split('[[plugin]]\nid = "Weather"')[0]
    cfg.write_text(good)
    summary = Summary(screen="ok", plugins=(PluginSummary("Clock", "on_screen"),))
    assert warnings.needs_attention(summary, rows(cfg), [], datetime.now()) == []


def test_the_plugins_that_need_attention_in_config_order(cfg):
    items = warnings.needs_attention(paused_comic(), rows(cfg), [], datetime.now())
    titles = [item.title for item in items]
    assert titles == [
        "Comic: paused due to errors",
        "Weather: Configuration Required",
        "Rio: not used, has errors",
    ]
    comic, weather, rio = items
    assert comic.text == "The website did not answer. PaperPi tries again at 14:30."
    assert comic.again == "Comic" and comic.settings == "/plugins/1/settings?id=Comic"
    assert weather.text == "Fill in: email" and weather.again is None
    assert "lat" in rio.text and rio.settings == "/plugins/3/settings?id=Rio"


def test_a_config_file_paperpi_could_not_use_comes_first(cfg):
    summary = paused_comic(config_errors=("paperpi.toml line 3: not valid TOML",))
    first = warnings.needs_attention(summary, rows(cfg), [], datetime.now())[0]
    assert first.title == "The config file has a mistake" and first.style == "bad"
    assert first.lines == ("paperpi.toml line 3: not valid TOML",) and first.reload
    # Without a scheduler, the file's own problems are shown, without a button.
    found = warnings.needs_attention(None, [], ["paperpi.toml line 9: oops"], datetime.now())
    assert found[0].lines == ("paperpi.toml line 9: oops",) and not found[0].reload


def test_a_screen_that_does_not_answer(cfg):
    summary = Summary(screen="paused", screen_retry_at=datetime(2026, 10, 14, 14, 20))
    item = warnings.needs_attention(summary, [], [], datetime.now())[0]
    assert item.title == "The screen is not answering" and item.again == ""
    assert item.text == "The screen is not answering. PaperPi tries again at 14:20."


def test_recent_is_the_newest_warnings_and_errors_by_day(monkeypatch):
    book = Logbook(None)
    add(book, "WARNING", "old one", datetime(2025, 12, 31, 23, 0))
    add(book, "ERROR", "monday", datetime(2026, 10, 12, 7, 0))
    add(book, "WARNING", "yesterday", datetime(2026, 10, 13, 22, 4))
    add(book, "INFO", "not a warning", datetime(2026, 10, 14, 9, 0))
    add(
        book,
        "CRITICAL",
        "crash\nTraceback (most recent call last):\n  KeyError",
        datetime(2026, 10, 14, 9, 1),
    )
    days = warnings.recent(book, "all", TODAY)
    assert [day.label for day in days] == ["Today", "Yesterday", "Mon 12 Oct", "Wed 31 Dec 2025"]
    crash = days[0].entries[0]
    assert (
        crash.first == "crash" and crash.more.startswith("Traceback") and crash.chip[1] == "Crash"
    )
    errors = warnings.recent(book, "errors", TODAY)
    assert [e.first for day in errors for e in day.entries] == ["crash", "monday"]
    only = warnings.recent(book, "warnings", TODAY)
    assert [e.first for day in only for e in day.entries] == ["yesterday", "old one"]
    monkeypatch.setattr(warnings, "RECENT", 2)
    assert [e.first for day in warnings.recent(book, "all", TODAY) for e in day.entries] == [
        "crash",
        "yesterday",
    ]


def test_an_unknown_filter_shows_all():
    assert warnings.filter_of("errors") == "errors"
    assert warnings.filter_of("<b>") == "all" and warnings.filter_of(None) == "all"


def test_the_warnings_tab(cfg, scheduler, book):
    scheduler.summary = paused_comic()
    page = client(cfg, scheduler, book).get("/warnings")
    assert page.status_code == 200
    text = page.text
    assert 'href="/warnings" aria-current="page">Warnings' in text
    assert re.search(r'id="menu-count"[^>]*>3<', text) and re.search(
        r'id="fold-count"[^>]*>3<', text
    )
    assert '<a href="/log">Full log</a>' in text
    assert "<h3>Comic: paused due to errors</h3>" in text
    assert text.count(">Try again now</button>") == 1 and 'name="back" value="warnings"' in text
    assert 'href="/plugins/2/settings?id=Weather">Settings</a>' in text
    assert "Load the file again" not in text
    recent = text[text.index('<ol class="recent">') :]
    # As in the log, the newest first; the INFO line is not there; the text is escaped.
    assert recent.index("screen write failed") < recent.index("could not reach")
    assert "show now" not in recent and "&lt;timed out&gt;" in recent
    assert '<li class="day">Today</li>' in recent and "✕ Error" in recent and "⚠ Warning" in recent
    assert 'hx-trigger="every 10s"' in text


def test_the_filter_and_an_empty_list(cfg, scheduler, book):
    page = client(cfg, scheduler, book).get("/warnings?show=warnings").text
    assert 'value="warnings" checked' in page
    assert "could not reach" in page and "screen write failed" not in page
    empty = client(cfg, scheduler, Logbook(None)).get("/warnings").text
    assert "No warnings or errors of this kind." in empty


def test_without_the_scheduler_or_the_log(cfg):
    page = client(cfg).get("/warnings").text
    assert "The log is only kept while PaperPi shows the plugins" in page
    # Weather misses a setting, Rio has an error: both are in the config file itself.
    assert "Weather: Configuration Required" in page and "Rio: not used, has errors" in page
    assert ">Try again now</button>" not in page


def test_other_pages_show_the_count_in_the_menu(cfg, scheduler):
    scheduler.summary = paused_comic()
    page = client(cfg, scheduler).get("/library").text
    assert '<a href="/warnings">Warnings<span class="count" id="menu-count"' in page
    assert re.search(r'id="menu-count"[^>]*>3<', page)
    cfg.write_text(cfg.read_text().split('[[plugin]]\nid = "Comic"')[0])
    scheduler.summary = Summary(screen="ok")
    calm = client(cfg, scheduler).get("/library").text
    assert re.search(r'id="menu-count" hidden', calm)


def test_the_tab_asks_again_and_answers_only_a_change(cfg, scheduler, book):
    scheduler.summary = paused_comic()
    web = client(cfg, scheduler, book)
    page = web.get("/warnings").text
    seen = re.search(r"seen=(\w+)", page).group(1)
    assert web.get(f"/warnings?seen={seen}", headers=HTMX).status_code == 204
    add(book, "WARNING", "something new")
    part = web.get(f"/warnings?seen={seen}", headers=HTMX)
    assert part.status_code == 200 and "something new" in part.text
    assert '<div id="warnings-part"' in part.text
    assert "<html" not in part.text
    assert re.search(r'id="menu-count" hx-swap-oob="true"[^>]*>3<', part.text)


def test_load_the_file_again(cfg, scheduler):
    scheduler.summary = paused_comic(config_errors=("paperpi.toml line 3: not valid TOML",))
    web = client(cfg, scheduler)
    page = web.get("/warnings").text
    assert "<code>paperpi.toml line 3: not valid TOML</code>" in page
    assert '<form method="post" action="/warnings/reload">' in page
    answer = web.post("/warnings/reload")
    assert answer.status_code == 303 and answer.headers["location"] == "/warnings?done=reload"
    assert scheduler.asked == [("reload",)]
    assert "Asked PaperPi to load the config file again." in web.get("/warnings?done=reload").text
    assert client(cfg).post("/warnings/reload").status_code == 409


def test_try_again_from_the_tab_opens_the_tab_again(cfg, scheduler):
    web = client(cfg, scheduler)
    answer = web.post("/screen/try-again", data={"id": "Comic", "back": "warnings"})
    assert answer.headers["location"] == "/warnings?done=again"
    assert (
        web.post("/screen/try-again", data={"back": "elsewhere"}).headers["location"]
        == "/?done=again"
    )
    assert scheduler.asked == [("try_again", "Comic"), ("try_again", None)]
    assert "Asked PaperPi to try again now." in web.get("/warnings?done=again").text
    # Only the messages of this tab.
    assert '<p class="saved">' not in web.get("/warnings?done=removed").text


def test_the_full_log_has_the_warnings_tab_too(cfg, book):
    page = client(cfg, book=book).get("/log").text
    assert '<a href="/warnings">Warnings</a>' in page and 'href="/log" aria-current="page"' in page


def test_old_lines_say_their_date(cfg):
    book = Logbook(None)
    add(book, "WARNING", "long ago", datetime.now() - timedelta(days=3))
    page = client(cfg, book=book).get("/warnings").text
    assert '<li class="day">Today</li>' not in page and "long ago" in page


def test_a_file_the_web_interface_cant_change_is_no_mistake(cfg, scheduler):
    # PaperPi uses this file; only the web interface can't change it safely.
    cfg.write_text(
        'config_version = 1\n[display]\ntype = "virtual"\n\n'
        '[["plugin"]]\nid = "Clock"\ntype = "basic_clock"\n'
    )
    assert PluginEditor(cfg).plugin_list().problems  # the web interface's own problem
    page = client(cfg, scheduler).get("/warnings").text
    assert "Nothing needs your attention." in page
    assert re.search(r'id="menu-count" hidden', page)
