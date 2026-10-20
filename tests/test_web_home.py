import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from paperpi import config
from paperpi.scheduler import PluginSummary, Summary
from paperpi.web import auth
from paperpi.web import password as web_password
from paperpi.web.app import create_app
from paperpi.web.home import CARD_PICTURE, Snapshots, in_about
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
type = "virtual"

[[plugin]]
id = "Clock"
type = "basic_clock"

[[plugin]]
id = "Words"
type = "word_clock"

[[plugin]]
id = "Comic"
type = "xkcd_comic"

[[plugin]]
id = "Weather"
type = "met_no"
lat = 52.52
lon = 13.40
enabled = false
"""
PI = "http://192.168.1.20:8080"
NOW = datetime.now()


@dataclass
class FakeScheduler:
    """Stands in for the scheduler: a summary to show, and the requests it got."""

    summary: Summary = field(default_factory=Summary)
    asked: list = field(default_factory=list)

    def show_now(self, plugin_id):
        self.asked.append(("show_now", plugin_id))

    def skip(self):
        self.asked.append(("skip",))

    def refresh(self):
        self.asked.append(("refresh",))

    def try_again(self, plugin_id=None):
        self.asked.append(("try_again", plugin_id))

    def dismiss(self, plugin_id):
        self.asked.append(("dismiss", plugin_id))


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def scheduler():
    return FakeScheduler()


@pytest.fixture
def client(cfg, scheduler):
    editor = PluginEditor(cfg)
    editor.loaded(CONFIG)
    app = create_app(auth.Auth(cfg, config.WebSettings(login=False)), editor, controls=scheduler)
    return TestClient(app, follow_redirects=False, base_url=PI)


def picture(shade=255, size=(400, 300)):
    return Image.new("L", size, shade)


def on_screen(**changes):
    """Clock on screen, Words next in 5 minutes (counted from now: the page uses the clock)."""
    soon = datetime.now() + timedelta(minutes=5, seconds=20)
    screen = picture(0)
    plugins = (
        PluginSummary("Clock", "on_screen", picture=screen, drawn_at=NOW),
        PluginSummary("Words", "next", shows_at=soon),
        PluginSummary(
            "Comic",
            "paused",
            error="The website did not answer.",
            paused_until=datetime(2026, 10, 11, 14, 5),
        ),
        PluginSummary("Weather", "needs_settings", missing=("email",)),
    )
    values = dict(
        on_screen="Clock",
        since=datetime(2026, 10, 11, 13, 50),
        picture=screen,
        next="Words",
        next_at=soon,
        screen="ok",
        plugins=plugins,
    )
    return Summary(**(values | changes))


def test_the_home_page_shows_the_screen_and_a_card_per_plugin(client, scheduler):
    scheduler.summary = on_screen()
    page = client.get("/").text
    now = page[page.index('<section class="now"') : page.index("</section>")]
    assert "<h2>Clock</h2>" in now and '<div class="type">Clock</div>' in now
    assert "<dd>13:50</dd>" in now and "<dd>Words, in about 5 minutes</dd>" in now
    assert 'hx-get="/now" hx-trigger="every 3s"' in now
    assert 'src="/screen/picture?v=' in now and 'width="400" height="300"' in now
    assert "Skip to next" in now and "Refresh" in now and "Dismiss alert" not in now
    cards = page[page.index('<ol class="cards"') :]
    assert "▶ On screen now" in cards and "→ Next" in cards and "Shows in about 5 minutes" in cards
    assert "⏸ Paused due to errors" in cards
    assert "The website did not answer. PaperPi tries again at 14:05." in cards
    assert "! Configuration Required" in cards
    # Show now for the plugins that take turns, Try again now for the paused one.
    assert cards.count(">Show now</button>") == 2  # Words and Comic
    assert cards.count(">Try again now</button>") == 1
    # The Clock card has its latest picture; the others have none yet.
    assert 'src="/screen/picture?id=Clock&amp;v=' in cards
    assert cards.count("No picture yet") == 3


def test_the_screen_buttons_ask_the_scheduler(client, scheduler):
    scheduler.summary = on_screen(alert=True)
    assert "Dismiss alert" in client.get("/").text
    # Without JavaScript: a form, and back to the home page with a message.
    response = client.post("/screen/skip")
    assert response.status_code == 303 and response.headers["location"] == "/?done=skip"
    assert "Asked PaperPi to show the next plugin." in client.get("/?done=skip").text
    # With htmx: the screen part comes back at once, with the message.
    htmx = {"hx-request": "true"}
    part = client.post("/screen/refresh", headers=htmx)
    assert part.status_code == 200
    assert '<section class="now"' in part.text and "fetch new data" in part.text
    client.post("/screen/dismiss", data={"id": "Clock"}, headers=htmx)
    client.post("/screen/show", data={"id": "Words"}, headers=htmx)
    client.post("/screen/try-again", data={"id": "Comic"}, headers=htmx)
    client.post("/screen/try-again", headers=htmx)
    assert scheduler.asked == [
        ("skip",),
        ("refresh",),
        ("dismiss", "Clock"),
        ("show_now", "Words"),
        ("try_again", "Comic"),
        ("try_again", None),
    ]


def test_the_screen_part_brings_the_cards_states_along(client, scheduler):
    scheduler.summary = on_screen()
    part = client.get("/now").text
    assert part.count('hx-swap-oob="true"') == 8  # a state and a picture per card
    scheduler.summary = on_screen(on_screen="Words", since=None, next=None)
    part = client.get("/now").text
    assert "<h2>Words</h2>" in part and "Nothing else to show" in part


def test_the_screen_part_is_sent_again_only_when_it_changed(client, scheduler):
    scheduler.summary = on_screen()
    seen = re.search(r'"seen": "(\w+)"', client.get("/").text).group(1)
    assert client.get("/now", params={"seen": seen}).status_code == 204
    scheduler.summary = on_screen(on_screen="Words")
    part = client.get("/now", params={"seen": seen})
    assert part.status_code == 200 and "<h2>Words</h2>" in part.text


def test_a_move_after_the_log_in_ran_out_saves_nothing(cfg):
    stored = web_password.hash_password("correct horse")
    app = create_app(auth.Auth(cfg, config.WebSettings(password_hash=stored)), PluginEditor(cfg))
    client = TestClient(app, follow_redirects=False, base_url=PI)
    data = {"id": "Weather", "to": "0"}
    response = client.post("/plugins/3/move", data=data, headers={"hx-request": "true"})
    # home.js opens the log-in page instead of showing the move as saved.
    assert response.status_code == 204 and response.headers["hx-redirect"] == "/login"
    assert cfg.read_text() == CONFIG


def test_pictures_are_kept_by_the_browser_until_they_change(client, scheduler):
    scheduler.summary = on_screen()
    page = client.get("/").text
    first = page.split('src="/screen/picture?v=')[1].split('"')[0]
    response = client.get(f"/screen/picture?v={first}")
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, max-age=86400"
    assert Image.open(io.BytesIO(response.content)).size == (400, 300)
    # A new picture gets a new number; the old address still gets a picture, not kept.
    scheduler.summary = on_screen(picture=picture(128))
    page = client.get("/").text
    second = page.split('src="/screen/picture?v=')[1].split('"')[0]
    assert second != first
    assert client.get(f"/screen/picture?v={first}").headers["cache-control"] == "no-store"
    assert client.get("/screen/picture?id=Nobody").status_code == 404


def test_built_in_plugins_and_the_screen_state(client, scheduler):
    scheduler.summary = Summary(
        on_screen="built-in-splash",
        picture=picture(),
        screen="paused",
        screen_retry_at=datetime(2026, 10, 11, 9, 30),
    )
    page = client.get("/").text
    assert "<h2>Splash Screen</h2>" in page
    assert "The screen is not answering. PaperPi tries again at 09:30." in page
    assert 'action="/screen/try-again"' in page
    # Before the first picture.
    scheduler.summary = Summary()
    assert "<h2>Starting</h2>" in client.get("/").text


def test_without_a_scheduler_the_page_shows_the_config_file(cfg):
    app = create_app(auth.Auth(cfg, config.WebSettings(login=False)), PluginEditor(cfg))
    client = TestClient(app, follow_redirects=False, base_url=PI)
    page = client.get("/").text
    assert "every 3s" not in page and "Skip to next" not in page and "Show now" not in page
    assert page.count("↻ On") == 3 and "○ Off" not in page  # Weather needs settings
    assert client.post("/screen/skip").status_code == 409


def test_a_change_of_a_moment_ago_is_shown_as_loading(client, scheduler, cfg):
    # Weather has its settings now, and is on; the scheduler has not loaded the file yet.
    cfg.write_text(CONFIG.replace("enabled = false", 'email = "me@example.org"'))
    scheduler.summary = on_screen()
    assert "PaperPi is loading the change." in client.get("/").text


def test_moving_a_card_to_any_place(client, cfg):
    htmx = {"hx-request": "true"}
    response = client.post("/plugins/3/move", data={"id": "Weather", "to": "0"}, headers=htmx)
    assert response.status_code == 204
    assert "Weather" in cfg.read_text().split("[[plugin]]")[1]
    # A card that moved meanwhile: the page is told why, as plain text.
    response = client.post("/plugins/3/move", data={"id": "Weather", "to": "1"}, headers=htmx)
    assert response.status_code == 409 and "changed after this page was opened" in response.text
    assert response.headers["content-type"].startswith("text/plain")
    # Only plain numbers ("²" counts as a digit in Python).
    response = client.post("/plugins/0/move", data={"id": "Weather", "to": "²"}, headers=htmx)
    assert response.status_code == 400
    # Without JavaScript, the arrows: back to the home page.
    response = client.post("/plugins/0/move", data={"id": "Weather", "step": "down"})
    assert response.headers["location"] == "/?done=saved"


def test_the_library_example_stands_in_before_the_first_picture(client, monkeypatch):
    from paperpi.web.pictures import Pictures, Shown

    monkeypatch.setattr(
        Pictures, "shown", lambda self, plugin_type: Shown(file=f"{plugin_type}-0123.png")
    )
    page = client.get("/").text
    assert '<img src="/library/pictures/word_clock-0123.png" alt="">' in page
    assert page.count("<span>Example</span>") == 4


def test_snapshots():
    snapshots = Snapshots()
    image = picture(size=(1200, 825))
    first = snapshots.version("Clock", image)
    assert snapshots.version("Clock", image) == first
    assert snapshots.version("", image) != first
    number, png = snapshots.png("Clock")
    assert number == first
    assert max(Image.open(io.BytesIO(png)).size) == CARD_PICTURE
    assert max(Image.open(io.BytesIO(snapshots.png("")[1])).size) == 1200
    assert snapshots.version("Clock", picture()) == first + 2
    snapshots.keep_only(set())
    assert snapshots.png("Clock") is None and snapshots.png("") is not None
    # Two-colour and palette pictures are made smaller smoothly (as gray or colour).
    for mode in ["1", "P"]:
        snapshots.version("x", Image.new(mode, (1300, 100)))
        assert snapshots.png("x") is not None


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (10, "in less than a minute"),
        (60, "in about 1 minute"),
        (25 * 60, "in about 25 minutes"),
        (3 * 3600, "in about 3 hours"),
    ],
)
def test_in_about(seconds, said):
    assert in_about(NOW + timedelta(seconds=seconds), NOW) == said
