import tomllib
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.scheduler import Summary
from paperpi.web import auth, system
from paperpi.web.app import create_app
from paperpi.web.config_file import UnknownScreenForm, set_display
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
# The kind of screen
type = "virtual"
# Turn the picture, in degrees
# rotation = 0
max_refresh = 6  # a bit more often

[[plugin]]
id = "Clock"
type = "basic_clock"
"""

PI = "http://192.168.1.20:8080"


class Controls:
    def __init__(self, summary: Summary):
        self.summary = summary


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def reloads():
    return []


def make_client(cfg, reloads, display=None, controls=None):
    editor = PluginEditor(cfg, lambda: reloads.append(1))
    editor.loaded(cfg.read_text())
    editor.display = display
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=False))
    app = create_app(paperpi_auth, editor, controls=controls, state_dir=cfg.parent)
    return TestClient(app, follow_redirects=False, base_url=PI)


@pytest.fixture
def client(cfg, reloads):
    return make_client(cfg, reloads)


#: Every field of the form, as a browser sends it with nothing changed.
FORM = {
    "next": "",
    "rotation": "0",
    "max_refresh": "6",
    "clean_every": "1",
    "clean_unit": "hours",
    "clean_never": "false",
    "on_exit": "clear",
    "splash_time": "60",
    "fallback_clock": "true",
}


def display(cfg):
    return tomllib.loads(cfg.read_text())["display"]


def test_the_menu_links_to_the_page(client):
    assert '<a href="/system"' in client.get("/").text


def test_the_page_shows_the_settings_of_the_file(client):
    page = client.get("/system").text
    assert "<h1>Screen &amp; system</h1>" in page
    assert 'name="max_refresh" value="6"' in page
    assert 'value="0" checked' in page  # rotation
    assert "Virtual screen (writes PNG files)" in page
    assert "1200 × 825, 16 grays" in page
    assert "Save and apply" in page and "/static/system.js" in page


def test_the_page_shows_the_screen_paperpi_uses_now(cfg, reloads):
    started = config.DisplaySettings(type="it8951", model="9.7", vcom=-1.9)
    summary = Summary(screen="paused")
    page = make_client(cfg, reloads, started, Controls(summary)).get("/system").text
    assert "Waveshare IT8951 board" in page and "9.7 inch, 1200 × 825, 16 grays" in page
    assert "−1.90 V" in page
    assert "Paused: it does not answer" in page


def test_colour_is_offered_only_on_a_colour_screen(cfg, reloads):
    page = make_client(cfg, reloads).get("/system").text
    assert 'name="color" value="true"' not in page
    assert "This screen shows 16 grays, so plugins" in page
    colour = config.DisplaySettings(type="virtual", mode="7color")
    page = make_client(cfg, reloads, colour).get("/system").text
    assert 'name="color" value="true" checked' in page


def test_save_and_apply_writes_only_what_differs_from_the_defaults(client, cfg, reloads):
    sent = FORM | {"rotation": "90", "max_refresh": "4", "clean_every": "30"}
    sent |= {"clean_unit": "minutes", "on_exit": "keep", "fallback_clock": "false"}
    response = client.post("/system", data=sent)
    assert response.status_code == 303
    assert response.headers["location"] == "/system?done=saved"
    assert display(cfg) == {
        "type": "virtual",
        "rotation": 90,
        "clean_every": 1800,
        "on_exit": "keep",
        "fallback_clock": False,
    }
    text = cfg.read_text()
    # A setting takes the place of its comment, so the help text above it stays.
    assert "# Turn the picture, in degrees\nrotation = 90\n" in text
    # Back to the default: the line becomes the default as a comment.
    assert "# max_refresh = 4\n" in text
    assert reloads == [1]
    assert "Saved. PaperPi applies the changes now." in client.get("/system?done=saved").text


def test_nothing_changed_saves_nothing(client, cfg, reloads):
    assert client.post("/system", data=FORM).status_code == 303
    assert cfg.read_text() == CONFIG and reloads == []


@pytest.mark.parametrize(
    ("sent", "seconds"),
    [
        ({"clean_never": "true", "clean_every": "", "clean_unit": "minutes"}, 0),
        ({"clean_every": "2", "clean_unit": "hours"}, 7200),
        ({"clean_every": "12,5", "clean_unit": "minutes"}, 750),
    ],
)
def test_clean_every_in_minutes_hours_or_never(client, cfg, sent, seconds):
    client.post("/system", data=FORM | sent)
    assert display(cfg)["clean_every"] == seconds
    page = client.get("/system").text
    if seconds == 0:
        assert 'name="clean_never" value="true" checked' in page
    if seconds == 7200:
        assert 'name="clean_every" value="2"' in page and "<option selected>hours" in page


def test_wrong_values_save_nothing_and_say_why(client, cfg, reloads):
    sent = FORM | {"max_refresh": "many", "clean_every": "5", "clean_unit": "minutes"}
    response = client.post("/system", data=sent | {"rotation": "90", "splash_time": "9999"})
    assert response.status_code == 400
    page = response.text
    assert "Some values can&#39;t be used. Nothing was saved." in page
    assert "Must be a whole number" in page
    assert "Must be at least 10 minutes, or Never" in page
    assert "less than or equal to 3600" in page
    # The sent values stay on the page, so they can be fixed.
    assert 'name="max_refresh" value="many"' in page and 'value="90" checked' in page
    assert cfg.read_text() == CONFIG and reloads == []


def test_save_and_apply_then_go_opens_the_page_asked_for(client, cfg):
    response = client.post("/system", data=FORM | {"rotation": "180", "next": "/library"})
    assert response.headers["location"] == "/library"
    assert display(cfg)["rotation"] == 180


@pytest.mark.parametrize("next_page", ["https://evil.example/", "//evil.example/", "/\\evil"])
def test_then_go_only_opens_paperpis_own_pages(client, next_page):
    response = client.post("/system", data=FORM | {"rotation": "180", "next": next_page})
    assert response.headers["location"] == "/system?done=saved"


def test_a_broken_display_part_is_not_changed(client, cfg):
    cfg.write_text(CONFIG.replace('type = "virtual"', 'type = "virtual"\nmode = "sepia"'))
    response = client.post("/system", data=FORM | {"max_refresh": "5"})
    assert response.status_code == 409
    assert "[display] mode in the config file can&#39;t be used" in response.text


def test_the_pi_part_has_the_facts(cfg, reloads):
    written = Summary(written_at=datetime.now().replace(hour=14, minute=2))
    part = make_client(cfg, reloads, controls=Controls(written)).get("/system/pi").text
    assert 'hx-trigger="every 30s"' in part
    assert "PaperPi version" in part and "14:02" in part and "MB" in part


def test_set_display_keeps_the_rest_of_the_file():
    text = '[display]\ntype = "virtual"\n\n[web]\nport = 8081\n'
    new = set_display(text, {"rotation": 270, "color": None}, {"color": True})
    assert new == '[display]\ntype = "virtual"\nrotation = 270\n\n[web]\nport = 8081\n'


def test_set_display_refuses_a_file_it_cant_change_safely():
    with pytest.raises(UnknownScreenForm):
        set_display('display.type = "virtual"\n', {"rotation": 90})
    with pytest.raises(UnknownScreenForm):
        set_display('[display]\ntype = "virtual"\nrotation = [\n  90]\n', {"rotation": 180})


@pytest.mark.parametrize(
    ("seconds", "shown"),
    [(30, "0 min"), (3 * 3600 + 120, "3 h 2 min"), (2 * 86400 + 7200, "2 d 2 h")],
)
def test_running_time_in_words(seconds, shown):
    assert system._duration(seconds) == shown
