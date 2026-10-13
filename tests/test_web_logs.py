"""The Full log page (paperpi.web.logs, /log in paperpi.web.app)."""

import logging

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.logbook import Logbook
from paperpi.web import auth, logs
from paperpi.web.app import create_app

PI = "http://192.168.1.20:8080"
HTMX = {"HX-Request": "true"}


def add(book: Logbook, level: str, text: str, source: str = "paperpi.scheduler") -> None:
    number = logging.getLevelName(level)
    record = logging.makeLogRecord({"name": source, "levelno": number, "levelname": level})
    book.add(record, text)


@pytest.fixture
def book(tmp_path):
    found = Logbook(tmp_path)
    add(found, "WARNING", "before the restart")
    found.close()
    book = Logbook(tmp_path)
    add(book, "DEBUG", "fine points")
    add(book, "INFO", "show now: 'Weather Berlin'")
    add(book, "WARNING", "plugin 'xkcd' failed: could not reach xkcd.com <timed out>")
    return book


def client(tmp_path, book=None):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text("config_version = 1\n")
    app = create_app(auth.Auth(cfg, config.WebSettings(login=False)), logbook=book)
    return TestClient(app, follow_redirects=False, base_url=PI)


def lines_on(page: str) -> int:
    return page.count('<div class="ln ')


def test_the_page_shows_info_and_up_with_the_restart_marked(tmp_path, book):
    page = client(tmp_path, book).get("/log")
    assert page.status_code == 200
    text = page.text
    assert 'aria-current="page">Warnings' in text  # in the menu
    assert "fine points" not in text
    assert lines_on(text) == 3
    assert (
        text.index("before the restart")
        < text.index("PaperPi started again")
        < text.index("show now")
    )
    # Texts are escaped.
    assert "xkcd.com &lt;timed out&gt;" in text
    assert "3 of 4 kept lines match." in text


@pytest.mark.parametrize(("level", "count"), [("DEBUG", 4), ("WARNING", 2), ("LOUD", 3)])
def test_the_level_filter(tmp_path, book, level, count):
    assert lines_on(client(tmp_path, book).get(f"/log?level={level}").text) == count


def test_search_marks_what_it_found_in_any_case(tmp_path, book):
    page = client(tmp_path, book).get("/log?q=XKCD", headers=HTMX)
    # htmx gets only the list part of the page.
    assert "<h1>" not in page.text
    assert lines_on(page.text) == 1
    assert "plugin &#39;<mark>xkcd</mark>&#39; failed: could not reach <mark>xkcd</mark>.com" in (
        page.text
    )


def test_a_search_with_no_match(tmp_path, book):
    page = client(tmp_path, book).get("/log?q=nothing+like+this")
    assert "No lines match." in page.text
    assert "0 of 4 kept lines match." in page.text


def test_new_lines_as_they_come(tmp_path, book):
    web = client(tmp_path, book)
    page = web.get("/log?follow=1").text
    assert 'hx-get="/log/new"' in page
    assert '"after": 3' in page
    assert web.get("/log/new?after=3&level=INFO").status_code == 204  # nothing new
    add(book, "DEBUG", "not at this level")
    assert web.get("/log/new?after=3&level=INFO").status_code == 204
    add(book, "ERROR", "the screen does not answer")
    new = web.get("/log/new?after=3&level=INFO").text
    assert lines_on(new) == 1
    assert "the screen does not answer" in new
    assert "before the restart" not in new
    # What asks for the next lines starts after the newest line, and the count is updated.
    assert '"after": 5' in new
    assert 'id="log-count" hx-swap-oob="true">4 of 6 kept lines match.' in new


def test_without_new_lines_as_they_come_nothing_asks_for_them(tmp_path, book):
    assert "/log/new" not in client(tmp_path, book).get("/log").text


def test_the_page_shows_only_the_newest_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "SHOWN", 2)
    book = Logbook(None)
    for number in range(5):
        add(book, "INFO", f"line {number}")
    page = client(tmp_path, book).get("/log").text
    assert lines_on(page) == 2
    assert "line 4" in page and "line 2" not in page
    assert "The newest 2 of 5 matching lines are shown (5 kept)." in page


def test_download_has_every_line(tmp_path, book):
    answer = client(tmp_path, book).get("/log/download")
    assert answer.headers["content-type"] == "text/plain; charset=utf-8"
    assert answer.headers["content-disposition"].startswith('attachment; filename="paperpi-log-')
    rows = answer.text.splitlines()
    assert len(rows) == 4
    assert rows[0].endswith("WARNING paperpi.scheduler: before the restart")
    assert rows[1].endswith("DEBUG paperpi.scheduler: fine points")


def test_without_paperpi_run_there_is_no_log(tmp_path):
    web = client(tmp_path)
    assert "The log is only kept while PaperPi shows the plugins" in web.get("/log").text
    assert web.get("/log/new?after=0").status_code == 204
    assert web.get("/log/download").text == ""


def test_parts_mark_every_match():
    assert logs._parts("Screen screen", "screen") == (
        ("Screen", True),
        (" ", False),
        ("screen", True),
    )
    # A letter whose lower-case form is longer marks nothing, rather than the wrong letters.
    assert logs._parts("Straße", "ss") == (("Straße", False),)
