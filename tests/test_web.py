import logging
import re
import socket
import urllib.request
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from paperpi import config
from paperpi.cli import main
from paperpi.web import auth, server
from paperpi.web import password as web_password
from paperpi.web.app import COOKIE, create_app
from paperpi.web.password import check_password, hash_password

CONFIG = (
    "config_version = 1\n"
    "# my screen\n"
    '[display]\ntype = "virtual"\n'
    "[[plugin]]\n"
    'id = "Clock"\ntype = "basic_clock"  # the first plugin\n'
)


# The test client opens the pages as a phone on the home network would: by IP address.
PI = "http://192.168.1.20:8080"


@pytest.fixture(autouse=True)
def cheap_scrypt(monkeypatch):
    # The real cost (2**14) takes a moment on a Pi 3.
    monkeypatch.setattr(web_password, "_N", 16)
    monkeypatch.setattr(web_password, "_R", 1)


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    path.chmod(0o640)
    return path


def make_client(cfg, **web):
    settings = config.WebSettings(**web)
    return TestClient(create_app(auth.Auth(cfg, settings)), follow_redirects=False, base_url=PI)


def set_up(client, password="correct horse"):
    return client.post("/setup", data={"password": password, "again": password})


def test_cookie_lasts_a_year_and_belongs_to_one_password():
    stored = hash_password("correct horse")
    cookie = auth.new_cookie(stored, now=1_000_000_000)
    assert auth.cookie_ok(cookie, stored, now=1_000_000_000)
    assert auth.cookie_ok(cookie, stored, now=1_000_000_000 + auth.COOKIE_SECONDS - 1)
    assert not auth.cookie_ok(cookie, stored, now=1_000_000_000 + auth.COOKIE_SECONDS)
    assert not auth.cookie_ok(cookie, stored, now=1_000_000_000 - 3600)  # made in the future
    # A new password logs out every browser.
    assert not auth.cookie_ok(cookie, hash_password("correct horse"), now=1_000_000_000)
    issued, signature = cookie.split(".")
    other_end = "1" if signature.endswith("0") else "0"
    for broken in [
        "",
        "1000000000",
        "1000000000.",
        "x.y",
        f"{issued}.{signature[:-1]}{other_end}",
        f"{issued}.{signature[:-1]}é",  # not plain text: no error, just "no"
        f"{issued}.{signature}0",
        "\u0661" * 10 + f".{signature}",  # digits, but not 0-9
        "9" * 20 + ".a",
    ]:
        assert not auth.cookie_ok(broken, stored, now=1_000_000_000)
    assert not auth.cookie_ok(cookie, None, now=1_000_000_000)


def test_first_visitor_sets_the_password(cfg):
    paperpi_auth = auth.Auth(cfg, config.WebSettings())
    client = TestClient(create_app(paperpi_auth), follow_redirects=False, base_url=PI)
    for page in ["/", "/login"]:
        assert client.get(page).headers["location"] == "/setup"
    assert "Set a password" in client.get("/setup").text
    response = set_up(client)
    assert response.status_code == 303 and response.headers["location"] == "/"
    stored = config.parse(cfg.read_text()).web.password_hash
    assert check_password("correct horse", stored)
    # Logged in at once, for a year.
    assert f"Max-Age={auth.COOKIE_SECONDS}" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    page = client.get("/")
    assert page.status_code == 200 and "Log out" in page.text
    # Once set, the set-up page is gone, also for a second visitor.
    assert client.get("/setup").headers["location"] == "/"
    other = TestClient(client.app, follow_redirects=False, base_url=PI)  # a second browser
    assert other.get("/setup").headers["location"] == "/"
    assert other.get("/").headers["location"] == "/login"
    response = set_up(other, "another password")
    assert response.status_code == 400 and "set already" in response.text
    assert config.parse(cfg.read_text()).web.password_hash == stored


@pytest.mark.parametrize(
    ("password", "again", "problem"),
    [("correct horse", "correct hors", "not the same"), ("short", "short", "at least 8")],
)
def test_a_wrong_new_password_is_not_saved(cfg, password, again, problem):
    client = make_client(cfg)
    response = client.post("/setup", data={"password": password, "again": again})
    assert response.status_code == 400 and problem in response.text
    assert cfg.read_text() == CONFIG
    assert COOKIE not in response.cookies


def test_log_in_and_log_out(cfg):
    stored = hash_password("correct horse")
    client = make_client(cfg, password_hash=stored)
    assert client.get("/").headers["location"] == "/login"
    page = client.get("/login")
    assert "Forgot the password?" in page.text and "paperpi reset-password" in page.text
    wrong = client.post("/login", data={"password": "wrong"})
    assert wrong.status_code == 401 and "Wrong password" in wrong.text
    assert client.get("/").status_code == 303
    right = client.post("/login", data={"password": "correct horse"})
    assert right.headers["location"] == "/"
    assert client.get("/").status_code == 200
    out = client.post("/logout")
    assert out.headers["location"] == "/login"
    assert client.get("/").headers["location"] == "/login"


def test_a_cookie_made_up_by_hand_is_refused(cfg):
    client = make_client(cfg, password_hash=hash_password("correct horse"))
    client.cookies.set(COOKIE, auth.new_cookie(hash_password("correct horse")))
    assert client.get("/").headers["location"] == "/login"


def test_reset_password_and_reload(cfg, capsys):
    """The steps on the log-in page: paperpi reset-password, reload, set a new password."""
    paperpi_auth = auth.Auth(cfg, config.WebSettings())
    client = TestClient(create_app(paperpi_auth), follow_redirects=False, base_url=PI)
    set_up(client)
    assert main(["reset-password", "--config", str(cfg)]) == 0
    assert "removed the web password" in capsys.readouterr().out
    assert config.parse(cfg.read_text()).web.password_hash is None
    # Until the reload, the old password still works.
    assert client.get("/").status_code == 200
    paperpi_auth.use(config.parse(cfg.read_text()).web)  # what a reload does
    assert client.get("/").headers["location"] == "/setup"
    set_up(client, "a new password")
    assert check_password("a new password", config.parse(cfg.read_text()).web.password_hash)
    assert main(["reset-password", "--config", str(cfg)]) == 0
    assert main(["reset-password", "--config", str(cfg)]) == 0
    assert "no web password is set" in capsys.readouterr().out


def test_log_in_switched_off(cfg):
    client = make_client(cfg, login=False)
    page = client.get("/")
    assert page.status_code == 200
    assert "Log-in is switched off" in page.text and "Log out" not in page.text
    for path in ["/setup", "/login"]:
        assert client.get(path).headers["location"] == "/"
        assert client.post(path, data={"password": "x", "again": "x"}).status_code == 303
    assert cfg.read_text() == CONFIG  # no password is saved


def test_forms_from_other_websites_are_refused(cfg):
    client = make_client(cfg)
    for headers in [{"origin": "http://evil.example"}, {"sec-fetch-site": "cross-site"}]:
        response = client.post(
            "/setup", data={"password": "x" * 8, "again": "x" * 8}, headers=headers
        )
        assert response.status_code == 403
    assert cfg.read_text() == CONFIG
    # The web interface's own pages send their own address.
    assert set_up(client).status_code == 303


def test_pages_may_not_be_shown_inside_other_websites(cfg):
    response = make_client(cfg).get("/setup")
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_htmx_and_style_are_served_without_log_in(cfg):
    client = make_client(cfg, password_hash=hash_password("correct horse"))
    assert "htmx" in client.get("/static/htmx.min.js").text
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/nothing.js").status_code == 404


def test_the_icon_is_served_without_log_in(cfg):
    client = make_client(cfg, password_hash=hash_password("correct horse"))
    icon = client.get("/static/icon.svg")
    assert icon.status_code == 200 and icon.headers["content-type"] == "image/svg+xml"
    for name in ("favicon-32.png", "apple-touch-icon.png"):
        assert client.get(f"/static/{name}").headers["content-type"] == "image/png"
    assert 'rel="icon" href="/static/icon.svg"' in client.get("/login").text


def test_server_runs_in_a_thread(cfg, caplog):
    settings = config.WebSettings.model_construct(
        **(config.WebSettings().model_dump() | {"address": "127.0.0.1", "port": 0})
    )
    web = server.start(cfg, settings)
    assert web is not None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{web.port}/", timeout=30) as page:
            assert page.url.endswith("/setup")
        # A reload with a new port: it applies at the next start.
        with caplog.at_level(logging.WARNING):
            loaded = config.parse(cfg.read_text())
            web.use(replace(loaded, web=config.WebSettings(port=9000, login=False)))
        assert "[web] address, port: changes apply at the next start" in caplog.text
        assert not web.auth.login  # log-in changes apply at once
    finally:
        web.stop()


def test_server_that_cant_start_is_logged(cfg, caplog):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        settings = config.WebSettings(address="127.0.0.1", port=port)
        with caplog.at_level(logging.ERROR):
            assert server.start(cfg, settings) is None
    assert f"the web interface can't start on 127.0.0.1 port {port}" in caplog.text


@pytest.mark.parametrize(
    "host",
    ["192.168.1.20:8080", "192.168.1.20", "10.0.0.5:80", "[::1]:8080", "localhost:8080"],
)
def test_pages_open_by_ip_address(cfg, host):
    response = make_client(cfg).get("/setup", headers={"host": host})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example:8080", "paperpi.local:8080", "192.168.1.20.evil.example", ""]
)
def test_pages_opened_by_a_name_are_refused(cfg, host):
    """A website could point a name of its own at the Pi (DNS rebinding) and set the
    first password itself."""
    client = make_client(cfg)
    headers = {"host": host, "origin": f"http://{host}", "sec-fetch-site": "same-origin"}
    response = client.post("/setup", data={"password": "x" * 8, "again": "x" * 8}, headers=headers)
    assert response.status_code == 400
    assert "Open PaperPi by its IP address" in response.text
    assert response.headers["x-frame-options"] == "DENY"
    assert cfg.read_text() == CONFIG
    assert client.get("/", headers={"host": host}).status_code == 400


@pytest.mark.parametrize("path", ["/setup2", "/login/", "/static", "/staticx/htmx.min.js"])
def test_only_the_log_in_pages_are_open(cfg, path):
    client = make_client(cfg, password_hash=hash_password("correct horse"))
    assert client.get(path).headers["location"] == "/login"


def test_security_headers_also_on_redirects(cfg):
    client = make_client(cfg, password_hash=hash_password("correct horse"))
    response = client.get("/")
    assert response.status_code == 303
    policy = response.headers["content-security-policy"]
    assert "form-action 'self'" in policy and "base-uri 'none'" in policy
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["cache-control"] == "no-store"
    # The style sheet and htmx may be kept by the browser.
    assert "cache-control" not in client.get("/static/style.css").headers


MENU = [("/", "Home"), ("/library", "Plugin Library")]


def menu_marks(html: str) -> list[str]:
    """The menu entries marked as the current page (once in the bar, once in the phone menu)."""
    return re.findall(r'<a href="([^"]*)" aria-current="page">', html)


@pytest.mark.parametrize(
    "path, current",
    [
        ("/", "/"),
        ("/plugins/0/settings?id=Clock", "/"),
        ("/plugins/0/remove?id=Clock", "/"),
        ("/library", "/library"),
        ("/library/basic_clock", "/library"),
    ],
)
def test_every_page_has_the_menu_with_its_own_entry_marked(cfg, path, current):
    client = make_client(cfg, login=False)
    html = client.get(path).text
    header = html[html.index("<header") : html.index("</header>")]
    for href, label in MENU:
        # In the menu bar, and in the folded menu for phones.
        assert header.count(f'<a href="{href}"') == 2 and header.count(f">{label}</a>") == 2
    assert menu_marks(header) == [current, current]
    assert '<details class="fold">' in header
    assert "Log out" not in html  # log-in is switched off


def test_logged_in_pages_have_log_out_in_both_menus(cfg):
    client = make_client(cfg)
    set_up(client)
    for path in ["/", "/library"]:
        header = client.get(path).text.split("</header>")[0]
        assert header.count(">Log out</button>") == 2


def test_pages_one_step_down_say_how_to_go_back(cfg):
    client = make_client(cfg, login=False)
    crumbs = '<p class="crumbs"><a href="/">Home</a> › Clock</p>'
    assert crumbs in client.get("/plugins/0/settings?id=Clock").text
    assert crumbs in client.get("/plugins/0/remove?id=Clock").text
    assert (
        '<p class="crumbs"><a href="/library">Plugin Library</a> › Clock</p>'
        in client.get("/library/basic_clock").text
    )


def test_the_log_in_pages_have_no_menu(cfg):
    client = make_client(cfg)
    assert 'aria-label="Main"' not in client.get("/setup").text
    set_up(client)
    client.post("/logout")
    html = client.get("/login").text
    assert "Log in" in html and 'aria-label="Main"' not in html and "fold" not in html
    # Opened by a name instead of the IP address: no menu either, but the look still loads.
    by_name = {"host": "paperpi.local:8080"}
    html = client.get("/", headers=by_name).text
    assert "Open PaperPi by its IP address" in html and 'aria-label="Main"' not in html
    for name in ["style.css", "theme.js"]:
        assert client.get(f"/static/{name}", headers=by_name).status_code == 200


def test_the_look_works_within_the_pages_own_rules(cfg):
    # The Content-Security-Policy allows only PaperPi's own files: no inline scripts or
    # styles, nothing from other servers (no web fonts), so the pages work without internet.
    client = make_client(cfg, login=False)
    home = ["/static/Sortable.min.js", "/static/home.js"]
    for path in ["/", "/plugins/0/settings?id=Clock", "/library"]:
        html = client.get(path).text
        assert " style=" not in html and "<style" not in html
        scripts = re.findall(r'<script\b[^>]*\bsrc="([^"]*)"[^>]*></script>', html)
        assert scripts == [
            "/static/theme.js",
            "/static/htmx.min.js",
            *(home if path == "/" else []),
            *(["/static/library.js"] if path == "/library" else []),
        ]
        assert html.count("<script") == len(scripts)  # no inline scripts
        assert "http://" not in html.replace(PI, "") and "https://" not in html
    theme = client.get("/static/theme.js")  # served (what it does is checked in a browser)
    assert theme.status_code == 200 and "paperpi-theme" in theme.text
    css = client.get("/static/style.css").text
    # The dark look follows the device, and the button can override it both ways.
    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root:not([data-theme="light"])' in css and ':root[data-theme="dark"]' in css
    # Without JavaScript the button stays hidden (theme.js shows it).
    buttons = re.findall(r"<button[^>]*data-theme-toggle[^>]*>", client.get("/").text)
    assert len(buttons) == 2 and all(re.search(r"\bhidden\b", b) for b in buttons)


def test_log_in_cookie_is_strict(cfg):
    response = set_up(make_client(cfg))
    assert "SameSite=strict" in response.headers["set-cookie"]


def test_a_reload_just_before_the_first_password_does_not_forget_it(cfg):
    paperpi_auth = auth.Auth(cfg, config.WebSettings())
    old = config.parse(cfg.read_text()).web  # read by a reload, just before the save
    client = TestClient(create_app(paperpi_auth), follow_redirects=False, base_url=PI)
    set_up(client)
    paperpi_auth.use(old)
    assert paperpi_auth.password_hash is not None
    response = set_up(client, "another password")
    assert response.status_code == 400 and "set already" in response.text


def test_server_listens_on_its_address_only(cfg):
    settings = config.WebSettings.model_construct(
        **(config.WebSettings().model_dump() | {"address": "127.0.0.1", "port": 0})
    )
    web = server.start(cfg, settings)
    try:
        assert web._socket.getsockname()[0] == "127.0.0.1"
    finally:
        web.stop()


def test_a_slow_browser_does_not_hold_up_the_stop(cfg):
    import time

    settings = config.WebSettings.model_construct(
        **(config.WebSettings().model_dump() | {"address": "127.0.0.1", "port": 0})
    )
    web = server.start(cfg, settings)
    with socket.create_connection(("127.0.0.1", web.port)) as slow:
        # Says 100 bytes follow, sends 4, and waits.
        slow.sendall(b"POST /setup HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 100\r\n\r\nabcd")
        time.sleep(0.5)
        start = time.monotonic()
        web.stop()
        assert time.monotonic() - start < server.STOP_SECONDS
    assert not web.running


def test_a_web_interface_that_crashes_is_logged(cfg, caplog, monkeypatch):
    settings = config.WebSettings.model_construct(
        **(config.WebSettings().model_dump() | {"address": "127.0.0.1", "port": 0})
    )

    def broken(self, sockets=None):
        raise RuntimeError("broken on purpose")

    monkeypatch.setattr(server.uvicorn.Server, "run", broken)
    with caplog.at_level(logging.ERROR):
        web = server.start(cfg, settings)
        web._thread.join(5)
    assert not web.running
    assert "the web interface stopped because of an error" in caplog.text
    web.stop()
