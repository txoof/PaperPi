import tomllib

import pytest
from fastapi.testclient import TestClient
from markupsafe import Markup

from paperpi import config
from paperpi.plugin import PluginSettings, helper_of, is_required, setting
from paperpi.web import auth, forms, helpers
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
id = "Weather"
name = "Weather Berlin"
type = "met_no"
lat = 52.52
lon = 13.40
enabled = false

[[plugin]]
id = "Comic"
type = "xkcd_comic"
time_limit = 30
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
def client(cfg, reloads):
    editor = PluginEditor(cfg, lambda: reloads.append(1))
    editor.loaded(CONFIG)
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=False))
    return TestClient(create_app(paperpi_auth, editor), follow_redirects=False, base_url=PI)


def blocks(cfg):
    return tomllib.loads(cfg.read_text())["plugin"]


def test_active_plugins_link_to_each_settings_page(client):
    page = client.get("/plugins").text
    assert '<a href="/plugins/1/settings?id=Weather">Settings</a>' in page
    assert "type them into the config file" not in page


def test_the_page_shows_the_settings_in_their_groups(client):
    page = client.get("/plugins/1/settings", params={"id": "Weather"}).text
    assert "<h1>Weather Berlin</h1>" in page
    assert page.index('name="name"') < page.index("Settings of this plugin")
    assert page.index('name="lat"') < page.index("When and how it is shown")
    assert page.index('name="display_time"') < page.index("More settings")
    assert page.index("More settings") < page.index('name="storage_mb"')
    assert 'value="52.52"' in page and "(required)" in page
    assert "Not shown until these settings are filled in: email." in page
    assert "<details>\n    <summary>More settings" in page  # folded: all defaults
    assert "<code>Weather</code> (fixed; it names the storage folder)" in page
    assert "<code>plugins/weather/</code>" in page


def test_more_settings_open_by_themselves_when_one_is_not_the_default(client):
    page = client.get("/plugins/2/settings", params={"id": "Comic"}).text
    assert "<details open>\n    <summary>More settings" in page


def test_saving_changes_the_file_and_applies_at_once(client, cfg, reloads):
    form = {"id": "Weather", "email": "me@example.org", "lon": "13.5", "display_time": "120"}
    response = client.post("/plugins/1/settings", data=form)
    assert response.status_code == 303
    assert response.headers["location"] == "/plugins/1/settings?id=Weather&done=saved"
    assert blocks(cfg)[1] | {} == {
        "id": "Weather",
        "name": "Weather Berlin",
        "type": "met_no",
        "lat": 52.52,
        "lon": 13.5,
        "enabled": False,
        "email": "me@example.org",
    }
    assert reloads == [1]
    page = client.get(response.headers["location"]).text
    assert "Saved. PaperPi applies the change now." in page
    assert "Not shown until" not in page  # email is set now


def test_values_that_cant_be_used_save_nothing_and_are_shown_again(client, cfg, reloads):
    response = client.post(
        "/plugins/1/settings", data={"id": "Weather", "lat": "91", "temperature": "F"}
    )
    assert response.status_code == 400
    page = response.text
    assert "Nothing was saved" in page
    assert 'value="91"' in page and "Input should be less than or equal to 90" in page
    assert '<option value="F" selected>' in page
    assert cfg.read_text() == CONFIG and reloads == []


def test_check_boxes_go_on_and_off(client, cfg):
    page = client.get("/plugins/2/settings", params={"id": "Comic"}).text
    # A box that is off sends nothing, so the page sends "false" before it.
    assert '<input type="hidden" name="enlarge" value="false">' in page
    client.post("/plugins/2/settings", data={"id": "Comic", "enlarge": ["false", "true"]})
    assert blocks(cfg)[2]["enlarge"] is True
    client.post("/plugins/2/settings", data={"id": "Comic", "enlarge": ["false"]})
    assert "enlarge" not in blocks(cfg)[2]


def test_adding_from_the_library_opens_the_settings(client, cfg):
    response = client.post("/library/met_no", data={"name": "Weather Rio"})
    added = blocks(cfg)[-1]["id"]
    assert response.headers["location"] == f"/plugins/3/settings?id={added}&done=added"
    page = client.get(response.headers["location"]).text
    assert "Added. Fill in its settings here, then Save." in page
    assert "Not shown until these settings are filled in: lat, lon, email." in page
    assert "Then switch it on in" in page


def test_a_plugin_moved_meanwhile_shows_the_list(client, cfg):
    assert client.get("/plugins/0/settings", params={"id": "Weather"}).status_code == 409
    response = client.post("/plugins/0/settings", data={"id": "Weather", "lat": "1"})
    assert response.status_code == 409 and "changed after this page was opened" in response.text
    assert cfg.read_text() == CONFIG


def test_a_helper_is_shown_under_its_field(client, monkeypatch):
    monkeypatch.setattr(helpers, "HELPERS", {"test": lambda f: Markup(f"<p>help {f.key}</p>")})
    monkeypatch.setattr(
        forms,
        "helper_of",
        lambda info: "test" if (info.description or "").startswith("Latitude") else "nope",
    )
    page = client.get("/plugins/1/settings", params={"id": "Weather"}).text
    assert page.count("<p>help ") == 1 and "<p>help lat</p>" in page  # "nope" shows nothing


def test_setting_takes_a_helper_name():
    class Settings(PluginSettings):
        lat: float | None = setting(None, required=True, helper="location")
        lon: float | None = setting(None, helper="location")
        place: str = setting("")

    fields = Settings.model_fields
    assert [helper_of(fields[k]) for k in fields] == ["location", "location", None]
    assert [is_required(fields[k]) for k in fields] == [True, False, False]
