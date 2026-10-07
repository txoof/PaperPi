import tomllib
import urllib.request

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.web import auth
from paperpi.web.app import create_app
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
type = "virtual"

# the clock in the kitchen
[[plugin]]
name = "Clock"
type = "basic_clock"

[[plugin]]
name = "Weather"
type = "met_no"
lat = 52.52
lon = 13.40
enabled = false

[[plugin]]
name = "Broken"
type = "basic_clock"
refresh = 1
"""

# The test client opens the pages as a phone on the home network would: by IP address.
PI = "http://192.168.1.20:8080"


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def reloads():
    return []


@pytest.fixture
def editor(cfg, reloads):
    found = PluginEditor(cfg, lambda: reloads.append(1))
    found.loaded(CONFIG)
    return found


@pytest.fixture
def client(cfg, editor):
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=False))
    return TestClient(create_app(paperpi_auth, editor), follow_redirects=False, base_url=PI)


def blocks(cfg):
    return tomllib.loads(cfg.read_text()).get("plugin", [])


def names(cfg):
    return [b["name"] for b in blocks(cfg)]


def test_active_plugins_shows_every_block_with_its_state(client):
    page = client.get("/plugins")
    assert page.status_code == 200
    text = page.text
    assert text.index("Clock") < text.index("Weather") < text.index("Broken")
    assert "Needs settings: email" in text
    assert "Not used: has errors" in text and "refresh" in text
    assert text.count("Switch off") == 2  # Clock and Broken; Weather is off
    # Weather can't be switched on until its email is filled in.
    assert '<button type="submit" disabled>Switch on</button>' in text
    assert 'value="up" disabled' in text and 'value="down" disabled' in text


def test_moving_a_plugin_saves_and_applies_at_once(client, cfg, reloads):
    response = client.post("/plugins/0/move", data={"name": "Clock", "step": "down"})
    assert response.status_code == 303
    assert response.headers["location"].startswith("/plugins?done=saved")
    assert names(cfg) == ["Weather", "Clock", "Broken"]
    assert '# the clock in the kitchen\n[[plugin]]\nname = "Clock"' in cfg.read_text()
    assert reloads == [1]
    page = client.get(response.headers["location"])
    assert "Saved. PaperPi applies the change now." in page.text
    assert "hand edits" not in page.text
    client.post("/plugins/1/move", data={"name": "Clock", "step": "up"})
    assert names(cfg) == ["Clock", "Weather", "Broken"]


def test_switching_off_and_on(client, cfg):
    client.post("/plugins/0/enabled", data={"name": "Clock", "on": "0"})
    assert blocks(cfg)[0]["enabled"] is False
    client.post("/plugins/0/enabled", data={"name": "Clock", "on": "1"})
    assert "enabled" not in blocks(cfg)[0]


def test_a_plugin_with_missing_settings_cant_be_switched_on(client, cfg, reloads):
    response = client.post("/plugins/1/enabled", data={"name": "Weather", "on": "1"})
    assert response.status_code == 409
    assert "fill in these settings first: email" in response.text
    assert cfg.read_text() == CONFIG and not reloads


def test_removing_asks_first(client, cfg):
    page = client.get("/plugins/0/remove", params={"name": "Clock"})
    assert "Remove Clock?" in page.text and cfg.read_text() == CONFIG
    response = client.post("/plugins/0/remove", data={"name": "Clock"})
    assert response.headers["location"] == "/plugins?done=removed&name=Clock"
    assert names(cfg) == ["Weather", "Broken"]
    assert "kitchen" not in cfg.read_text()
    assert "Removed Clock." in client.get(response.headers["location"]).text


def test_a_list_changed_by_hand_meanwhile_is_not_changed(client, cfg, reloads):
    # The page showed Clock first, but it was removed by hand since then.
    cfg.write_text(CONFIG.replace('name = "Clock"', 'name = "Kitchen"'))
    response = client.post("/plugins/0/remove", data={"name": "Clock"})
    assert response.status_code == 409 and "changed meanwhile" in response.text
    assert names(cfg) == ["Kitchen", "Weather", "Broken"] and not reloads


def test_hand_edits_are_kept_and_the_page_says_so(client, cfg, editor):
    cfg.write_text(CONFIG + '\n[[plugin]]\nname = "Words"\ntype = "word_clock"\n')
    response = client.post("/plugins/0/move", data={"name": "Clock", "step": "down"})
    assert "hand=1" in response.headers["location"]
    assert names(cfg) == ["Weather", "Clock", "Broken", "Words"]
    page = client.get(response.headers["location"])
    assert "Your hand edits to the config file were applied too." in page.text
    # The next change, before PaperPi reloaded: the file holds only the web's own change.
    response = client.post("/plugins/1/move", data={"name": "Clock", "step": "up"})
    assert "hand=1" not in response.headers["location"]


def test_the_library_lists_plugins_to_add(client):
    page = client.get("/library").text
    assert "basic_clock" in page and "met_no" in page
    assert "debugging" not in page and "default</strong>" not in page
    assert "/library/basic_clock" in page


def test_adding_a_plugin(client, cfg, reloads):
    form = client.get("/library/word_clock").text
    assert 'value="Word clock"' in form  # a name that is not used yet
    response = client.post("/library/word_clock", data={"name": " Words "})
    assert response.headers["location"] == "/plugins?done=added&name=Words"
    assert blocks(cfg)[-1] == {"name": "Words", "type": "word_clock"}
    assert reloads == [1]
    # The next one gets another name.
    client.post("/library/word_clock", data={"name": "Word clock"})
    assert 'value="Word clock 2"' in client.get("/library/word_clock").text


def test_a_plugin_with_required_settings_is_added_switched_off(client, cfg):
    form = client.get("/library/met_no").text
    assert "real email address" in form and "added switched off" in form
    client.post("/library/met_no", data={"name": "Weather Rio"})
    assert blocks(cfg)[-1] == {"name": "Weather Rio", "type": "met_no", "enabled": False}
    assert config.parse(cfg.read_text()).plugin("Weather Rio").missing == ("lat", "lon", "email")


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("", "Give the plugin a name."),
        ("x" * 101, "at most 100 characters"),
        ("a\tb", "must not hold control characters"),
        ("clock!", "already used by another plugin"),
    ],
)
def test_names_that_cant_be_used(client, cfg, name, problem):
    response = client.post("/library/word_clock", data={"name": name})
    assert response.status_code == 400 and problem in response.text
    assert cfg.read_text() == CONFIG


def test_unknown_plugin_types(client):
    assert client.get("/library/nothing").status_code == 404
    assert client.post("/library/debugging", data={"name": "x"}).status_code == 404


def test_a_broken_file_is_shown_not_changed(client, cfg):
    cfg.write_text("[[plugin]\n")
    page = client.get("/plugins")
    assert page.status_code == 500 and "The config file is not valid TOML" in page.text
    assert client.post("/plugins/0/move", data={"name": "", "step": "up"}).status_code == 409
    assert cfg.read_text() == "[[plugin]\n"


def test_the_plugin_pages_need_a_log_in(cfg):
    paperpi_auth = auth.Auth(cfg, config.WebSettings())
    client = TestClient(create_app(paperpi_auth), follow_redirects=False, base_url=PI)
    for path in ["/plugins", "/library", "/library/basic_clock", "/plugins/0/remove"]:
        assert client.get(path).headers["location"] == "/setup"
    assert client.post("/plugins/0/remove", data={"name": "Clock"}).status_code == 303
    assert cfg.read_text() == CONFIG


def test_a_change_in_the_running_web_interface_reloads_paperpi(cfg, reloads):
    from paperpi.web import server

    # Port 0: any free port (not allowed in the config file, so made without its checks).
    settings = config.WebSettings.model_construct(
        **(config.WebSettings().model_dump() | {"address": "127.0.0.1", "port": 0, "login": False})
    )
    web = server.start(cfg, settings, reload=lambda: reloads.append(1), text=CONFIG)
    assert web is not None
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{web.port}/plugins/0/enabled",
            data=b"name=Clock&on=0",
            headers={"Origin": f"http://127.0.0.1:{web.port}"},
        )
        with urllib.request.urlopen(request, timeout=30) as page:
            assert "/plugins?done=saved" in page.url
    finally:
        web.stop()
    assert reloads == [1] and blocks(cfg)[0]["enabled"] is False
