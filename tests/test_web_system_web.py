"""The Web interface part of the Screen & system page (M5 part 5-3a), and
``paperpi web-defaults``."""

import socket
import tomllib

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.cli import main
from paperpi.web import auth, server, system
from paperpi.web.app import COOKIE, create_app
from paperpi.web.config_file import UnknownWebForm, set_web
from paperpi.web.password import hash_password
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
type = "virtual"

[web]
# The web interface's port
# port = 8080
login = false

[[plugin]]
id = "Clock"
type = "basic_clock"
"""

PI = "http://192.168.1.20:8080"
STARTED = config.WebSettings(login=False)


class Controls:
    summary = None

    def __init__(self):
        self.restarts = 0

    def restart(self):
        self.restarts += 1


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


def make_client(cfg, settings=STARTED, controls=None):
    editor = PluginEditor(cfg, lambda: None)
    editor.loaded(cfg.read_text())
    paperpi_auth = auth.Auth(cfg, settings)
    app = create_app(paperpi_auth, editor, controls=controls, state_dir=cfg.parent, web=settings)
    client = TestClient(app, follow_redirects=False, base_url=PI)
    client.auth_ = paperpi_auth
    return client


@pytest.fixture
def client(cfg):
    return make_client(cfg)


def web(cfg) -> dict:
    return tomllib.loads(cfg.read_text()).get("web", {})


def send(client, **values):
    """Save and apply with only the web settings (the display part is left out)."""
    form = {"port": "8080", "address": "0.0.0.0", "login": "false"} | values
    return client.post("/system", data=form)


@pytest.fixture
def taken():
    """A port another program uses."""
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        yield other.getsockname()[1]


@pytest.fixture
def free():
    with socket.socket() as probe:
        probe.bind(("0.0.0.0", 0))
        return probe.getsockname()[1]


def test_the_page_shows_the_web_settings(client):
    page = client.get("/system").text
    assert 'id="web"' in page and "Open it at <code>http://192.168.1.20:8080</code>" in page
    assert 'name="port" value="8080"' in page
    assert '<option value="0.0.0.0" selected>Every device on your home network' in page
    assert 'name="login" value="true">' in page  # not ticked
    assert "Change\n          password" not in page  # only with a password


def test_a_free_port_is_saved_for_the_next_start(client, cfg, free):
    response = send(client, port=str(free))
    assert response.headers["location"] == "/system?done=saved"
    assert web(cfg)["port"] == free
    assert "# The web interface's port\nport = " in cfg.read_text()  # in place of the comment
    page = client.get("/system").text
    assert "Saved, waiting for a restart" in page
    assert f"<code>http://192.168.1.20:{free}</code>" in page
    assert "paperpi web-defaults" in page


def test_a_port_in_use_is_refused(client, cfg, taken):
    response = send(client, port=str(taken), address="127.0.0.1")
    assert response.status_code == 400
    assert "is used by another program" in response.text
    assert "port" not in web(cfg) and "address" not in web(cfg)


def test_a_port_that_needs_rights_is_refused(client, cfg, monkeypatch):
    def refuse(address, port):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(server, "listen", refuse)
    response = send(client, port="80")
    assert response.status_code == 400 and "needs administrator rights" in response.text
    assert "port" not in web(cfg)


@pytest.mark.parametrize("port", ["", "port", "0", "70000"])
def test_a_port_that_isnt_a_port_is_refused(client, cfg, port):
    response = send(client, port=port)
    assert response.status_code == 400 and "from 1 to 65535" in response.text


def test_the_port_in_use_now_is_not_tried(client, cfg, monkeypatch):
    """PaperPi holds it itself; it is free again at the restart."""
    monkeypatch.setattr(server, "listen", pytest.fail)
    send(client, address="127.0.0.1")
    assert web(cfg)["address"] == "127.0.0.1"
    page = client.get("/system").text
    assert "<code>http://127.0.0.1:8080</code>" in page
    assert "only open the web interface on the Pi" in page


def test_a_port_below_1024_is_refused_even_with_rights(client, cfg, monkeypatch):
    """The service never has the rights, also when this PaperPi was started with sudo."""
    monkeypatch.setattr(server, "listen", pytest.fail)
    response = send(client, port="443")
    assert response.status_code == 400 and "needs administrator rights" in response.text


def test_the_port_in_use_now_is_tried_for_a_wider_address(cfg, taken):
    """PaperPi on 127.0.0.2 doesn't keep the port free on 127.0.0.1."""
    started = config.WebSettings(login=False, address="127.0.0.2", port=taken)
    cfg.write_text(
        CONFIG.replace("login = false", f'login = false\naddress = "127.0.0.2"\nport = {taken}')
    )
    client = make_client(cfg, started)
    response = send(client, port=str(taken), address="127.0.0.1")
    assert response.status_code == 400 and "used by another program" in response.text


def test_only_the_two_choices_or_the_address_of_the_file(client, cfg):
    assert send(client, address="10.0.0.9").status_code == 400
    cfg.write_text(CONFIG.replace("login = false", 'login = false\naddress = "127.0.0.2"'))
    assert send(client, address="127.0.0.2").status_code == 303


def test_the_port_is_checked_while_typing(client, taken, free):
    assert client.get("/system/port", params={"port": "8080"}).text == ""  # as saved
    found = client.get("/system/port", params={"port": str(free), "address": "0.0.0.0"})
    assert f"Port {free} is free on this Pi right now" in found.text
    found = client.get("/system/port", params={"port": str(taken), "address": "127.0.0.1"})
    assert "used by another program" in found.text
    assert "from 1 to 65535" in client.get("/system/port", params={"port": "x"}).text


def test_undo_keeps_the_address_in_use(client, cfg, free):
    send(client, port=str(free), address="127.0.0.1")
    response = client.post("/system/web/undo")
    assert response.headers["location"] == "/system?done=web-undone"
    assert "port" not in web(cfg) and "address" not in web(cfg)
    assert "# port = 8080" in cfg.read_text()
    assert "waiting for a restart" not in client.get("/system").text


def test_restart_with_a_new_port_opens_the_new_address(cfg, free, monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "service")
    client = make_client(cfg, controls=Controls())
    send(client, port=str(free))
    page = client.post("/system/restart").text
    assert f'content="30;url=http://192.168.1.20:{free}/system"' in page
    assert "system.js" not in page  # it can't ask the new address whether PaperPi is back


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "localhost"])
def test_restart_to_this_pi_only_stays_on_the_page(cfg, free, monkeypatch, address):
    monkeypatch.setenv("INVOCATION_ID", "service")
    cfg.write_text(CONFIG.replace("login = false", f'login = false\naddress = "{address}"'))
    started = config.WebSettings(login=False)
    client = make_client(cfg, started, Controls())
    page = client.post("/system/restart").text
    assert "can\n  only be opened on the Pi itself" in page and "url=" not in page


def test_password_off_applies_at_once(cfg):
    stored = hash_password("correct horse")
    settings = config.WebSettings(login=True, password_hash=stored)
    cfg.write_text(CONFIG.replace("login = false", f'password_hash = "{stored}"'))
    client = make_client(cfg, settings)
    client.cookies.set(COOKIE, auth.new_cookie(stored))
    assert send(client, login="false").status_code == 303
    assert web(cfg)["login"] is False and not client.auth_.login
    client.cookies.clear()
    assert client.get("/system").status_code == 200  # no log-in needed any more


def test_password_on_again_asks_for_a_new_one(client, cfg):
    cfg.write_text(CONFIG.replace("login = false", 'login = false\npassword_hash = "scrypt:old"'))
    send(client, login="true")
    assert "login" not in web(cfg) and "password_hash" not in web(cfg)
    assert "password_hash" not in cfg.read_text()
    assert client.get("/system").headers["location"] == "/setup"


@pytest.fixture
def logged_in(cfg):
    stored = hash_password("correct horse")
    cfg.write_text(CONFIG.replace("login = false", f'password_hash = "{stored}"'))
    client = make_client(cfg, config.WebSettings(login=True, password_hash=stored))
    client.cookies.set(COOKIE, auth.new_cookie(stored))
    return client


def change(client, current="correct horse", password="battery staple", again=None):
    form = {"current": current, "password": password, "again": again or password}
    return client.post("/system/password", data=form)


def test_change_password(logged_in, cfg):
    old_cookie = logged_in.cookies.get(COOKIE)
    assert "Current password" in logged_in.get("/system/password").text
    response = change(logged_in)
    assert response.headers["location"] == "/system?done=password"
    stored = web(cfg)["password_hash"]
    assert logged_in.auth_.check("battery staple", stored)
    assert not logged_in.auth_.cookie_ok(old_cookie)  # other browsers are logged out
    assert logged_in.auth_.cookie_ok(response.cookies.get(COOKIE))  # this one stays


@pytest.mark.parametrize(
    "form, problem",
    [
        ({"current": "wrong"}, "not the current password"),
        ({"again": "something else"}, "not the same"),
        ({"password": "short"}, "at least 8 characters"),
    ],
)
def test_change_password_says_what_is_wrong(logged_in, cfg, form, problem):
    before = cfg.read_text()
    response = change(logged_in, **form)
    assert response.status_code == 400 and problem in response.text
    assert cfg.read_text() == before


def test_change_password_needs_a_log_in(logged_in):
    logged_in.cookies.clear()
    assert logged_in.get("/system/password").headers["location"] == "/login"
    assert change(logged_in).headers["location"] == "/login"


def test_change_password_needs_a_password_in_use(client):
    assert client.get("/system/password").headers["location"] == "/system#web"
    assert change(client).headers["location"] == "/system#web"


def test_set_web_adds_a_web_part():
    text = 'config_version = 1\n[display]\ntype = "virtual"'
    assert set_web(text, {"port": None}) == text  # nothing to take out
    new = set_web(text, {"port": 8081})
    assert new.endswith('type = "virtual"\n\n[web]\nport = 8081\n')
    with pytest.raises(UnknownWebForm):
        set_web("config_version = 1\nweb = { port = 8081 }\n", {"port": 8082})


def test_web_address_in_words():
    assert system.web_address("192.168.1.20", STARTED) == "http://192.168.1.20:8080"
    here = STARTED.model_copy(update={"address": "127.0.0.1", "port": 8081})
    assert system.web_address("192.168.1.20", here) == "http://127.0.0.1:8081"
    assert system.web_address("fe80::1", STARTED) == "http://[fe80::1]:8080"


def test_web_defaults_command(cfg, capsys):
    cfg.write_text(CONFIG.replace("login = false", 'login = false\nport = 80\naddress = "1.2.3.4"'))
    assert main(["web-defaults", "--config", str(cfg)]) == 0
    assert "back on port 8080, for every device" in capsys.readouterr().out
    assert web(cfg) == {"login": False}  # the password settings stay
    assert main(["web-defaults", "--config", str(cfg)]) == 0
    assert "already uses the defaults" in capsys.readouterr().out


def test_web_defaults_with_a_broken_file(tmp_path, capsys):
    assert main(["web-defaults", "--config", str(tmp_path / "nothing.toml")]) == 1
    assert "file not found" in capsys.readouterr().err
