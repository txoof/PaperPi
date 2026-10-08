import re
import tomllib
import urllib.request

import pytest
from fastapi.testclient import TestClient

from paperpi import config, plugins
from paperpi.plugin import PluginDefinitionError, PluginEntry
from paperpi.web import auth
from paperpi.web import password as web_password
from paperpi.web import plugins as web_plugins
from paperpi.web.app import create_app
from paperpi.web.config_file import EditError
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
type = "virtual"

# the clock in the kitchen
[[plugin]]
id = "Clock"
type = "basic_clock"

[[plugin]]
id = "Weather"
type = "met_no"
lat = 52.52
lon = 13.40
enabled = false

[[plugin]]
id = "Broken"
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
    return [b["id"] for b in blocks(cfg)]


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
    response = client.post("/plugins/0/move", data={"id": "Clock", "step": "down"})
    assert response.status_code == 303
    assert response.headers["location"].startswith("/plugins?done=saved")
    assert names(cfg) == ["Weather", "Clock", "Broken"]
    assert '# the clock in the kitchen\n[[plugin]]\nid = "Clock"' in cfg.read_text()
    assert reloads == [1]
    page = client.get(response.headers["location"])
    assert "Saved. PaperPi applies the change now." in page.text
    assert "hand edits" not in page.text
    client.post("/plugins/1/move", data={"id": "Clock", "step": "up"})
    assert names(cfg) == ["Clock", "Weather", "Broken"]


def test_switching_off_and_on(client, cfg):
    client.post("/plugins/0/enabled", data={"id": "Clock", "on": "0"})
    assert blocks(cfg)[0]["enabled"] is False
    client.post("/plugins/0/enabled", data={"id": "Clock", "on": "1"})
    assert "enabled" not in blocks(cfg)[0]


def test_a_plugin_with_missing_settings_cant_be_switched_on(client, cfg, reloads):
    response = client.post("/plugins/1/enabled", data={"id": "Weather", "on": "1"})
    assert response.status_code == 409
    assert "Fill in these settings first: email." in response.text
    assert cfg.read_text() == CONFIG and not reloads


def test_removing_asks_first(client, cfg):
    page = client.get("/plugins/0/remove", params={"id": "Clock"})
    assert "Remove Clock?" in page.text and cfg.read_text() == CONFIG
    response = client.post("/plugins/0/remove", data={"id": "Clock"})
    assert response.headers["location"] == "/plugins?done=removed"
    assert names(cfg) == ["Weather", "Broken"]
    assert "kitchen" not in cfg.read_text()
    assert "Plugin removed." in client.get(response.headers["location"]).text


def test_a_list_changed_by_hand_meanwhile_is_not_changed(client, cfg, reloads):
    # The page showed Clock first, but it was removed by hand since then.
    cfg.write_text(CONFIG.replace('id = "Clock"', 'id = "Kitchen"'))
    response = client.post("/plugins/0/remove", data={"id": "Clock"})
    assert response.status_code == 409 and "changed after this page was opened" in response.text
    assert names(cfg) == ["Kitchen", "Weather", "Broken"] and not reloads


def test_hand_edits_are_kept_and_the_page_says_so(client, cfg, editor):
    cfg.write_text(CONFIG + '\n[[plugin]]\nid = "Words"\ntype = "word_clock"\n')
    response = client.post("/plugins/0/move", data={"id": "Clock", "step": "down"})
    assert "hand=1" in response.headers["location"]
    assert names(cfg) == ["Weather", "Clock", "Broken", "Words"]
    page = client.get(response.headers["location"])
    assert "Your hand edits to the config file were applied too." in page.text
    # The next change, before PaperPi reloaded: the file holds only the web's own change.
    response = client.post("/plugins/1/move", data={"id": "Clock", "step": "up"})
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
    added = blocks(cfg)[-1]
    assert re.fullmatch(r"word_clock-[0-9a-f]{8}", added["id"])
    assert added == {"id": added["id"], "name": "Words", "type": "word_clock"}
    assert response.headers["location"] == f"/plugins?done=added&id={added['id']}"
    assert "Added Words." in client.get(response.headers["location"]).text
    assert reloads == [1]
    # The next one gets another name.
    client.post("/library/word_clock", data={"name": "Word clock"})
    assert 'value="Word clock 2"' in client.get("/library/word_clock").text


def test_names_may_be_empty_or_the_same(client, cfg):
    client.post("/library/word_clock", data={"name": ""})
    client.post("/library/word_clock", data={"name": "Clock"})
    first, second = blocks(cfg)[-2:]
    assert "name" not in first and second["name"] == "Clock"
    assert first["id"] != second["id"]
    page = client.get("/plugins").text
    assert f"<strong>{first['id']}</strong>" in page  # without a name: the ID
    assert f"word_clock · {second['id']}" in page  # the ID tells the two Clocks apart


def test_a_new_id_is_never_one_in_use(client, cfg, monkeypatch):
    made = iter(["CLOCK", "_clock_", "word-clock_1"])  # "Clock" is used: the first 2 are too
    monkeypatch.setattr(web_plugins, "new_id", lambda plugin_type: next(made))
    client.post("/library/word_clock", data={"name": "Words"})
    assert blocks(cfg)[-1]["id"] == "word-clock_1"


def test_a_new_id_fits_also_for_a_long_type():
    made = web_plugins.new_id("a" * 50)
    assert len(made) == 40 and PluginEntry(id=made, type="x").id == made


def test_a_plugin_with_required_settings_is_added_switched_off(client, cfg):
    form = client.get("/library/met_no").text
    assert "real email address" in form and "added switched off" in form
    client.post("/library/met_no", data={"name": "Weather Rio"})
    added = blocks(cfg)[-1]
    assert added == {"id": added["id"], "name": "Weather Rio", "type": "met_no", "enabled": False}
    assert config.parse(cfg.read_text()).plugin(added["id"]).missing == ("lat", "lon", "email")


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("x" * 101, "at most 100 characters"),
        ("a\tb", "must not hold control characters"),
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
    assert client.post("/plugins/0/move", data={"id": "", "step": "up"}).status_code == 409
    assert cfg.read_text() == "[[plugin]\n"


def test_the_plugin_pages_need_a_log_in(cfg):
    paperpi_auth = auth.Auth(cfg, config.WebSettings())
    client = TestClient(create_app(paperpi_auth), follow_redirects=False, base_url=PI)
    for path in ["/plugins", "/library", "/library/basic_clock", "/plugins/0/remove"]:
        assert client.get(path).headers["location"] == "/setup"
    assert client.post("/plugins/0/remove", data={"id": "Clock"}).status_code == 303
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
            data=b"id=Clock&on=0",
            headers={"Origin": f"http://127.0.0.1:{web.port}"},
        )
        with urllib.request.urlopen(request, timeout=30) as page:
            assert "/plugins?done=saved" in page.url
    finally:
        web.stop()
    assert reloads == [1] and blocks(cfg)[0]["enabled"] is False


def test_a_reload_tells_the_web_interface_which_text_is_in_use(cfg, reloads):
    from paperpi.web import server

    settings = config.WebSettings.model_construct(
        **(config.WebSettings().model_dump() | {"address": "127.0.0.1", "port": 0})
    )
    web = server.start(cfg, settings)
    try:
        edited = CONFIG + "# a hand edit\n"
        cfg.write_text(edited)
        web.use(config.parse(edited))  # PaperPi reloaded the hand edit
        assert not web.editor.move(0, "Clock", 1)
    finally:
        web.stop()


def test_which_changes_count_as_hand_edits(cfg, editor):
    # Applied by a reload: not a hand edit any more.
    edited = CONFIG + "# a hand edit\n"
    cfg.write_text(edited)
    editor.loaded(edited)
    assert not editor.move(0, "Clock", 1)
    # After the web's own change was applied, a new hand edit is one.
    editor.loaded(cfg.read_text())
    cfg.write_text(cfg.read_text() + "# another one\n")
    assert editor.move(1, "Clock", -1)
    # A password saved by the web interface is not a hand edit.
    editor.loaded(cfg.read_text())
    web_password.save_password_hash(cfg, "scrypt:16:1:1:c2FsdA:" + "A" * 43)
    assert not editor.move(0, "Clock", 1)
    # An editor that doesn't know what PaperPi uses never says so.
    cfg.write_text(cfg.read_text() + "# and one more\n")
    assert not PluginEditor(cfg).move(1, "Clock", -1)


def test_a_broken_plugin_is_shown_but_cant_be_added(client, cfg, monkeypatch):
    real = plugins.load

    def load(plugin_type, *args):
        if plugin_type == "word_clock":
            raise PluginDefinitionError("plugin 'word_clock': needs at least one layout")
        return real(plugin_type, *args)

    monkeypatch.setattr(plugins, "load", load)
    assert "This plugin is broken: plugin &#39;word_clock&#39;" in client.get("/library").text
    assert client.get("/library/word_clock").status_code == 200
    response = client.post("/library/word_clock", data={"name": "Words"})
    assert response.status_code == 400 and "can&#39;t be added" in response.text
    assert cfg.read_text() == CONFIG


def test_a_repeated_name_shows_the_second_block_as_not_used(client, cfg):
    cfg.write_text(CONFIG + '\n[[plugin]]\nid = "Clock"\ntype = "word_clock"\n')
    page = client.get("/plugins").text
    assert page.count("Not used: has errors") == 2  # Broken and the second Clock
    assert "is already used by the plugin block" in page


def test_a_change_is_refused_while_paperpi_cant_use_the_file(client, cfg, reloads):
    broken = CONFIG.replace('type = "virtual"', 'type = "nothing"')
    cfg.write_text(broken)
    page = client.get("/plugins")
    assert "unknown screen type" in page.text and "Unknown" in page.text
    response = client.post("/plugins/0/move", data={"id": "Clock", "step": "down"})
    assert response.status_code == 409 and "must be fixed first" in response.text
    assert cfg.read_text() == broken and not reloads


def test_every_change_needs_a_log_in_and_a_form_from_paperpi(cfg):
    forms = {
        "/plugins/0/move": {"id": "Clock", "step": "down"},
        "/plugins/0/enabled": {"id": "Clock", "on": "0"},
        "/plugins/0/remove": {"id": "Clock"},
        "/library/word_clock": {"name": "Words"},
    }
    stored = web_password.hash_password("correct horse")
    paperpi_auth = auth.Auth(cfg, config.WebSettings(password_hash=stored))
    client = TestClient(create_app(paperpi_auth), follow_redirects=False, base_url=PI)
    for path, form in forms.items():
        assert client.post(path, data=form).headers["location"] == "/login"
    open_client = TestClient(
        create_app(auth.Auth(cfg, config.WebSettings(login=False))),
        follow_redirects=False,
        base_url=PI,
    )
    for path, form in forms.items():
        other_site = {"origin": "http://evil.example", "sec-fetch-site": "cross-site"}
        assert open_client.post(path, data=form, headers=other_site).status_code == 403
    assert cfg.read_text() == CONFIG


def test_odd_requests(client, cfg):
    response = client.post("/plugins/0/move", data={"id": "Clock", "step": "sideways"})
    assert response.status_code == 400 and cfg.read_text() == CONFIG
    assert client.get("/plugins/0/remove", params={"id": "Kitchen"}).status_code == 409
    # Only the ID of a plugin in the list is taken from the address, not text to show.
    page = client.get("/plugins", params={"done": "added", "name": "Your password was reset"})
    assert "Your password was reset" not in page.text and "Plugin added." in page.text
    page = client.get("/plugins", params={"done": "added", "id": "Your password was reset"})
    assert "Your password was reset" not in page.text and "Plugin added." in page.text
    page = client.get("/plugins", params={"done": "added", "id": "Clock"})
    assert "Added Clock." in page.text


def test_the_file_keeps_its_permissions(client, cfg):
    cfg.chmod(0o640)
    client.post("/plugins/0/move", data={"id": "Clock", "step": "down"})
    assert cfg.stat().st_mode & 0o777 == 0o640


# --- Settings ---------------------------------------------------------------------------------


def test_saving_settings_changes_only_what_changed_and_applies_at_once(editor, cfg, reloads):
    plugin, block = editor.settings(1, "Weather")
    assert plugin.type == "met_no" and block["lat"] == 52.52
    form = {"lat": ["52.52"], "lon": ["13.5"], "email": ["me@example.org"], "display_time": [""]}
    assert editor.save_settings(1, "Weather", form) is False  # no hand edits
    assert blocks(cfg)[1] == {
        "id": "Weather",
        "type": "met_no",
        "lat": 52.52,
        "lon": 13.5,
        "enabled": False,
        "email": "me@example.org",
    }
    assert reloads == [1]
    assert "# the clock in the kitchen" in cfg.read_text()


def test_settings_with_errors_save_nothing(editor, cfg, reloads):
    with pytest.raises(web_plugins.FormErrors) as raised:
        editor.save_settings(1, "Weather", {"lat": ["91"], "lon": ["13.5"]})
    assert raised.value.found.errors == {"lat": "Input should be less than or equal to 90"}
    assert raised.value.found.sent == {"lat": ["91"], "lon": ["13.5"]}
    assert cfg.read_text() == CONFIG and reloads == []


def test_settings_of_a_block_moved_meanwhile_are_not_saved(editor, cfg):
    with pytest.raises(EditError, match="changed"):
        editor.save_settings(0, "Weather", {"lat": ["1"]})
    with pytest.raises(EditError, match="changed"):
        editor.settings(5, "Weather")
    assert cfg.read_text() == CONFIG


def test_settings_of_an_unknown_plugin_type_cant_be_changed(editor, cfg):
    cfg.write_text(CONFIG.replace('type = "basic_clock"\n\n', 'type = "nothing"\n\n', 1))
    with pytest.raises(EditError, match="its plugin type 'nothing' can't be used"):
        editor.settings(0, "Clock")
