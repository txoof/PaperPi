"""Keep these settings: new web settings on trial after a restart (M5 part 5-3b)."""

import socket
import threading
import time
import tomllib
import urllib.request

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.cli import main
from paperpi.web import auth, keep, server
from paperpi.web.app import create_app
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
type = "virtual"

[web]
login = false
{web}
[[plugin]]
id = "Clock"
type = "basic_clock"
"""

PI = "http://192.168.1.20:8081"
NEW = config.WebSettings(login=False, port=8081)
OLD = config.WebSettings(login=False)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG.format(web="port = 8081\n"))
    return path


def make_client(cfg, keeper):
    editor = PluginEditor(cfg, lambda: None)
    editor.loaded(cfg.read_text())
    paperpi_auth = auth.Auth(cfg, keeper.used)
    app = create_app(paperpi_auth, editor, state_dir=cfg.parent, web=keeper.used, keeper=keeper)
    return TestClient(app, follow_redirects=False, base_url=PI)


@pytest.fixture
def on_trial(cfg):
    """A keeper with port 8081 on trial; the old port was 8080."""
    keep.remember(cfg.parent, OLD)
    keeper = keep.Keeper(NEW, cfg.parent)
    keeper.go_back = lambda why: None
    keeper.start_trial(OLD)
    yield keeper
    keeper.stop()


def web(cfg) -> dict:
    return tomllib.loads(cfg.read_text()).get("web", {})


# --- The kept file and the time ---


def test_the_old_address_is_kept_in_the_state_folder(tmp_path):
    assert keep.previous(tmp_path, NEW) is None
    keep.remember(tmp_path, config.WebSettings(address="127.0.0.1", port=9000))
    assert "PaperPi writes this" in (tmp_path / keep.PREVIOUS_FILE).read_text()
    old = keep.previous(tmp_path, NEW)
    assert (old.address, old.port, old.login) == ("127.0.0.1", 9000, False)  # the rest stays
    keep.forget(tmp_path)
    assert keep.previous(tmp_path, NEW) is None
    assert keep.previous(None, NEW) is None


@pytest.mark.parametrize("text", ["port = 'x'", "port = 70000", "nonsense ==", "port = 9000"])
def test_a_broken_kept_file_is_not_used(tmp_path, text):
    (tmp_path / keep.PREVIOUS_FILE).write_text(text)
    assert keep.previous(tmp_path, NEW) is None


def test_a_saved_address_keeps_the_one_in_use(tmp_path):
    keeper = keep.Keeper(OLD, tmp_path)
    keeper.saved(NEW)
    assert keep.previous(tmp_path, OLD).port == 8080
    keeper.saved(OLD)  # saved back, or Undo
    assert keep.previous(tmp_path, OLD) is None


def test_while_on_trial_the_old_address_stays_kept(cfg, on_trial):
    """The address in use is not known to work yet; the kept one is."""
    on_trial.saved(config.WebSettings(port=9000))
    on_trial.saved(NEW)
    assert keep.previous(cfg.parent, NEW).port == 8080


def test_nobody_keeping_goes_back_when_the_time_is_up(tmp_path):
    asked = threading.Event()
    keeper = keep.Keeper(NEW, tmp_path)
    keeper.go_back = lambda why: asked.set() if why == "time" else None
    keeper.start_trial(OLD, seconds=0.1)
    assert asked.wait(5)


def test_keep_stops_the_time(tmp_path):
    keep.remember(tmp_path, OLD)
    calls = []
    keeper = keep.Keeper(NEW, tmp_path)
    keeper.go_back = calls.append
    keeper.start_trial(OLD, seconds=1.0)
    assert keeper.seconds_left() == 1
    assert keeper.keep() and not keeper.on_trial
    assert keep.previous(tmp_path, NEW) is None
    time.sleep(1.2)
    assert calls == []
    assert not keeper.keep()  # nothing on trial any more


# --- The pages ---


@pytest.mark.parametrize("path", ["/", "/library", "/warnings", "/system", "/log"])
def test_every_page_shows_the_keep_box(cfg, on_trial, path):
    page = make_client(cfg, on_trial).get(path).text
    assert "New web address:" in page
    assert "<code>http://192.168.1.20:8081</code>" in page
    assert "goes back to <code>http://192.168.1.20:8080</code> by itself" in page
    assert 'data-left="300">5:00</span>' in page or 'data-left="299">4:59</span>' in page
    assert "Go back to port 8080 now" in page
    assert "/static/keep.js" in page


def test_no_keep_box_without_new_settings(cfg):
    page = make_client(cfg, keep.Keeper(NEW, cfg.parent)).get("/").text
    assert "New web address" not in page and "keep.js" not in page


def test_the_box_names_the_old_address_when_only_the_address_changed(cfg):
    keeper = keep.Keeper(config.WebSettings(login=False, address="127.0.0.1"), cfg.parent)
    keeper.start_trial(OLD)
    try:
        assert "Go back to the old address now" in make_client(cfg, keeper).get("/").text
    finally:
        keeper.stop()


def test_keep_these_settings(cfg, on_trial):
    client = make_client(cfg, on_trial)
    response = client.post("/system/web/keep")
    assert response.headers["location"] == "/system?done=web-kept"
    assert not on_trial.on_trial and keep.previous(cfg.parent, NEW) is None
    page = client.get("/system?done=web-kept").text
    assert "Kept. The web interface stays at this address." in page
    assert "New web address" not in page


def test_go_back_now(cfg, on_trial):
    asked = threading.Event()
    on_trial.go_back = lambda why: asked.set() if why == "asked" else None
    page = make_client(cfg, on_trial).post("/system/web/back").text
    assert "Going back" in page and "New web address" not in page
    assert 'content="5;url=http://192.168.1.20:8080/system"' in page
    assert asked.wait(5)


def test_keep_and_go_back_without_a_trial_do_nothing(cfg):
    client = make_client(cfg, keep.Keeper(NEW, cfg.parent))
    assert client.post("/system/web/keep").headers["location"] == "/system?done="
    assert client.post("/system/web/back").headers["location"] == "/system?done="


def test_saving_a_new_port_keeps_the_one_in_use(cfg):
    cfg.write_text(CONFIG.format(web=""))
    keeper = keep.Keeper(OLD, cfg.parent)
    client = make_client(cfg, keeper)
    form = {"port": str(free_port()), "address": "0.0.0.0", "login": "false"}
    assert client.post("/system", data=form).status_code == 303
    assert keep.previous(cfg.parent, OLD).port == 8080
    client.post("/system/web/undo")
    assert keep.previous(cfg.parent, OLD) is None


def test_warnings_say_the_web_interface_went_back(cfg):
    keeper = keep.Keeper(OLD, cfg.parent)
    keeper.note = keep.reason("time", OLD)
    client = make_client(cfg, keeper)
    page = client.get("/warnings").text
    assert "The web interface went back to its old address" in page
    assert "went back to port 8080, for every device on your home network: nobody pressed" in page
    assert 'action="/warnings/web-seen"' in page
    assert client.post("/warnings/web-seen").headers["location"] == "/warnings"
    assert keeper.note is None
    assert "went back to its old address" not in client.get("/warnings").text


# --- At the start, and going back for real ---


def started(cfg, new_port, old_port, **kwargs):
    cfg.write_text(CONFIG.format(web=f'port = {new_port}\naddress = "127.0.0.1"\n'))
    keep.remember(cfg.parent, config.WebSettings(address="127.0.0.1", port=old_port))
    settings = config.WebSettings(address="127.0.0.1", port=new_port, login=False)
    return server.start(cfg, settings, text=cfg.read_text(), state_dir=cfg.parent, **kwargs)


def answers(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10):
            return True
    except OSError:
        return False


def test_new_settings_are_on_trial_after_the_start(cfg):
    new, old = free_port(), free_port()
    web_server = started(cfg, new, old)
    try:
        assert web_server.port == new and web_server.keeper.on_trial
        assert web_server.keeper.old.port == old
    finally:
        web_server.stop()


def test_going_back_moves_the_web_interface(cfg, caplog):
    new, old = free_port(), free_port()
    web_server = started(cfg, new, old)
    try:
        assert answers(new)
        web_server.keeper.go_back("time")
        assert web_server.port == old and answers(old) and not answers(new)
        assert web(cfg)["port"] == old
        assert keep.previous(cfg.parent, web_server.settings) is None
        assert web_server.settings.port == old and web_server.keeper.used.port == old
        assert "nobody pressed Keep these settings within 5 minutes" in web_server.keeper.note
        assert "went back to port" in caplog.text
    finally:
        web_server.stop()


def test_a_new_port_that_cant_be_opened_goes_back_at_once(cfg):
    old = free_port()
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        web_server = started(cfg, other.getsockname()[1], old)
    try:
        assert web_server.port == old and not web_server.keeper.on_trial
        assert web(cfg)["port"] == old
        assert keep.previous(cfg.parent, web_server.settings) is None
        assert "the new address can't be used" in web_server.keeper.note
    finally:
        web_server.stop()


def test_a_kept_address_that_is_in_use_again_is_forgotten(cfg):
    port = free_port()
    web_server = started(cfg, port, port)
    try:
        assert not web_server.keeper.on_trial
        assert not (cfg.parent / keep.PREVIOUS_FILE).exists()
    finally:
        web_server.stop()


def test_web_defaults_forgets_the_kept_address(cfg, capsys):
    keep.remember(cfg.parent, config.WebSettings(port=9000))
    assert main(["web-defaults", "--config", str(cfg), "--state-dir", str(cfg.parent)]) == 0
    assert not (cfg.parent / keep.PREVIOUS_FILE).exists()
