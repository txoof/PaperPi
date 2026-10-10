"""Example pictures in the Plugin Library (M5 part 3b-2)."""

import html
import itertools
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
from epdlib import ScreenMode
from fastapi.testclient import TestClient
from PIL import Image

from paperpi import config
from paperpi.plugin import State
from paperpi.runner import PluginFailed, PluginTimeout
from paperpi.web import auth, server
from paperpi.web.app import create_app
from paperpi.web.pictures import Pictures, Screen
from paperpi.web.plugins import PluginEditor
from paperpi.web.preview import Previewer

from .test_web_preview import FakeUpdate
from .test_web_settings import CONFIG, PI

FAKE = Path(__file__).parent / "fake_plugins" / "fake" / "__init__.py"
SCREEN = Screen(300, 200, ScreenMode.gray(16))
_names = itertools.count()


@pytest.fixture
def package(tmp_path, monkeypatch):
    """A new plugin package: ``fake`` (works), ``default`` (hidden from the Library) and
    ``broken`` (no PLUGIN). Each test gets its own name, so nothing is imported twice."""
    name = f"pictures_plugins_{next(_names)}"
    root = tmp_path / "code" / name
    for plugin_type in ("fake", "default"):
        (root / plugin_type).mkdir(parents=True)
        text = FAKE.read_text().replace('type="fake"', f'type="{plugin_type}"')
        (root / plugin_type / "__init__.py").write_text(text)
    (root / "broken").mkdir()
    (root / "broken" / "__init__.py").write_text("")
    (root / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path / "code"))
    return name


def until(check, seconds=5.0):
    end = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < end, "took too long"
        time.sleep(0.01)


@pytest.fixture
def make(tmp_path, package):
    """Starts pictures in ``tmp_path/pics`` for the test package; stopped at the end."""
    made = []

    def make(update, screen=SCREEN, wait=0.0):
        pictures = Pictures(tmp_path / "pics", update, package=package, wait=wait)
        pictures.use(screen)
        made.append(pictures)
        return pictures

    yield make
    for pictures in made:
        pictures.stop()


def drawn(pictures, *types):
    until(lambda: all(not pictures.shown(t).waiting for t in types))
    return [pictures.shown(t) for t in types]


def stale_gone(path):
    return lambda: not path.exists()


def round_done(pictures):
    """Wait until a whole new round has run: it deletes a picture that matches nothing."""
    for _ in range(2):  # the first may be a round that had started already
        stale = pictures.folder / "old-0000000000000000.png"
        pictures.folder.mkdir(exist_ok=True)
        stale.write_bytes(b"x")
        pictures.use(pictures._screen)  # e.g. a config reload
        until(stale_gone(stale))


def test_each_plugin_is_drawn_once_with_its_sample_data(tmp_path, make):
    update = FakeUpdate(State.READY, State.READY)
    pictures = make(update)
    fake, broken = drawn(pictures, "fake", "broken")
    assert fake.file.startswith("fake-") and fake.file.endswith(".png") and fake.screen == SCREEN
    image = Image.open(tmp_path / "pics" / fake.file)
    assert image.size == (300, 200)
    assert broken.problem.startswith("The plugin is broken:") and not broken.file
    [(plugin_type, context, sample, time_limit)] = update.calls  # not default, not broken
    assert (plugin_type, sample, time_limit) == ("fake", True, 10.0)
    assert (context.width, context.height, context.mode) == (300, 200, SCREEN.mode)
    assert context.layout == "one" and context.settings.act == "ok"
    round_done(pictures)  # nothing to draw again
    assert len(update.calls) == 1 and pictures.shown("fake") == fake
    assert sorted(p.name for p in (tmp_path / "pics").iterdir()) == [fake.file]


def test_a_changed_plugin_is_drawn_again(make, package):
    update = FakeUpdate(State.READY, State.READY)
    pictures = make(update)
    [first] = drawn(pictures, "fake")
    code = Path(__import__(package).__file__).parent / "fake" / "__init__.py"
    code.write_text(code.read_text() + "\n# changed\n")
    [second] = drawn(pictures, "fake")  # opening the page notices the change
    assert second.file != first.file and len(update.calls) == 2
    until(lambda: not (pictures.folder / first.file).exists())


def test_another_screen_is_drawn_again(make):
    update = FakeUpdate(State.READY, State.READY)
    pictures = make(update)
    [first] = drawn(pictures, "fake")
    other = Screen(200, 300, ScreenMode.bw())
    pictures.use(other)
    until(lambda: pictures.shown("fake").file not in ("", first.file))
    second = pictures.shown("fake")
    assert second.screen == other
    assert Image.open(pictures.folder / second.file).size == (200, 300)
    until(lambda: [p.name for p in pictures.folder.iterdir()] == [second.file])


def test_only_old_pictures_and_parts_are_deleted(make):
    pictures = make(FakeUpdate(State.READY), wait=60)
    pictures.folder.mkdir()
    for name in ("notes.txt", "old-0123456789abcdef.png", ".old-0123456789abcdef.png.part"):
        (pictures.folder / name).write_text("x")
    [fake] = drawn(pictures, "fake")
    round_done(pictures)
    assert sorted(p.name for p in pictures.folder.iterdir()) == [fake.file, "notes.txt"]


def test_a_picture_that_fails_says_why_and_is_not_tried_again(make):
    update = FakeUpdate(PluginFailed("fake", "ValueError: no font"))
    pictures = make(update)
    [fake] = drawn(pictures, "fake")
    assert fake.problem == "Its sample data could not be drawn: ValueError: no font"
    round_done(pictures)
    assert len(update.calls) == 1 and pictures.shown("fake").problem == fake.problem


def test_a_slow_plugin_is_tried_three_times(make):
    slow = PluginTimeout("fake", "no result within 10 s; stopped")
    update = FakeUpdate(slow, slow, slow)
    pictures = make(update)
    [fake] = drawn(pictures, "fake")  # each look at the page tries again
    assert fake.problem == "Its sample data could not be drawn: no result within 10 s; stopped"
    assert len(update.calls) == 3
    update = FakeUpdate(slow, State.READY)
    assert drawn(make(update), "fake")[0].file  # the second try worked


def test_any_error_is_shown_and_the_others_are_still_drawn(make, package):
    root = Path(__import__(package).__file__).parent
    shutil.copytree(root / "fake", root / "zfake")
    text = (root / "zfake" / "__init__.py").read_text()
    (root / "zfake" / "__init__.py").write_text(text.replace('type="fake"', 'type="zfake"'))
    pictures = make(FakeUpdate(RuntimeError("no process"), State.READY))
    fake, zfake = drawn(pictures, "fake", "zfake")
    assert fake.problem == "It could not be drawn: no process" and zfake.file


def test_nothing_to_show_is_a_problem_too(make):
    pictures = make(FakeUpdate(State.NOTHING))
    assert drawn(pictures, "fake")[0].problem == "Its sample data gives no picture."


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write anywhere")
def test_a_folder_that_cant_be_written_says_so(tmp_path, make):
    (tmp_path / "pics").mkdir(mode=0o500)
    try:
        pictures = make(FakeUpdate(State.READY))
        [fake] = drawn(pictures, "fake")
        assert fake.problem == "It could not be saved: Permission denied."
        assert list(pictures.folder.iterdir()) == []  # no part left
    finally:
        (tmp_path / "pics").chmod(0o700)
    (tmp_path / "pics").rmdir()
    (tmp_path / "pics").write_text("not a folder")
    pictures = make(FakeUpdate(State.READY))
    until(lambda: pictures.shown("fake").problem.startswith("Pictures can't be saved:"))


def test_a_plugin_whose_files_cant_be_read_says_so(make, monkeypatch):
    pictures = make(FakeUpdate(), wait=60)

    def unreadable(plugin_type, screen):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(pictures, "file_name", unreadable)
    assert pictures.shown("fake").problem == "Its files can't be read: Permission denied."


def test_drawing_waits_after_the_start_unless_the_page_is_opened(make):
    update = FakeUpdate()
    pictures = make(update, wait=60)
    time.sleep(0.1)
    assert update.calls == []
    assert pictures.shown("fake").waiting  # the page is opened: start now
    until(lambda: pictures.shown("fake").file)


def test_stop_ends_drawing(make, package):
    root = Path(__import__(package).__file__).parent
    shutil.copytree(root / "fake", root / "zfake")
    text = (root / "zfake" / "__init__.py").read_text()
    (root / "zfake" / "__init__.py").write_text(text.replace('type="fake"', 'type="zfake"'))
    update = FakeUpdate(State.READY, State.READY)
    pictures = make(update)
    real = update.__call__

    def stop_after_first(*args, **kwargs):
        pictures.stop()
        return real(*args, **kwargs)

    pictures._update = stop_after_first
    until(lambda: (pictures.folder / pictures.file_name("fake", SCREEN)).exists())
    time.sleep(0.1)
    assert len(update.calls) == 1 and not pictures._thread.is_alive()


def test_no_folder_means_no_pictures(package):
    pictures = Pictures(None, FakeUpdate(), package=package)
    pictures.use(SCREEN)
    assert pictures.shown("fake") is None and pictures.path("fake-0123456789abcdef.png") is None


def test_the_screen_is_turned_with_the_display():
    display = config.DisplaySettings(type="virtual", width=300, height=200, rotation=90)
    assert Screen.of(display) == Screen(200, 300, display.screen_mode)


def test_a_reload_keeps_the_screen_size_until_the_next_start(tmp_path):
    used = []
    pictures = Pictures(tmp_path / "pics")
    pictures.use = used.append
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(CONFIG)
    settings = config.WebSettings()
    editor = PluginEditor(cfg)
    web = server.WebServer(auth.Auth(cfg, settings), settings, socket.socket(), editor, pictures)
    try:
        start = config.DisplaySettings(type="virtual", width=300, height=200)
        web.use_display(start)
        # As in the scheduler: size and mode wait for the next start, rotation does not.
        web.use_display(start.model_copy(update={"width": 800, "mode": "bw", "rotation": 90}))
        assert used == [Screen(300, 200, start.screen_mode), Screen(200, 300, start.screen_mode)]
    finally:
        web._socket.close()


@pytest.mark.parametrize(
    "name",
    ["../paperpi.toml", "fake-0123456789abcdef.txt", "fake-0123.png", "-0123456789abcdef.png",
     "fake-0123456789ABCDEF.png", ".fake-0123456789abcdef.png.part"],
)  # fmt: skip
def test_only_picture_files_are_given_out(tmp_path, name):
    folder = tmp_path / "pics"
    folder.mkdir()
    (folder / name).write_bytes(b"x")  # even when the file is there
    assert Pictures(folder).path(name) is None


def test_links_are_not_given_out(tmp_path):
    folder = tmp_path / "pics"
    folder.mkdir()
    (tmp_path / "paperpi.toml").write_text("secret")
    (folder / "fake-0123456789abcdef.png").symlink_to(tmp_path / "paperpi.toml")
    assert Pictures(folder).path("fake-0123456789abcdef.png") is None


# The Library page.


def make_client(tmp_path, pictures):
    cfg = tmp_path / "paperpi.toml"
    cfg.write_text(CONFIG)
    editor = PluginEditor(cfg)
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=False))
    app = create_app(paperpi_auth, editor, Previewer(FakeUpdate()), pictures)
    return TestClient(app, follow_redirects=False, base_url=PI)


@pytest.fixture
def ready_pictures(tmp_path):
    """Real plugins, one picture saved already (as if drawn); drawing the others waits
    until the test ends, so they stay "being drawn"."""
    release = threading.Event()

    def update(plugin_type, context, *, sample, time_limit):
        release.wait(10)
        raise PluginFailed(plugin_type, "test ended")

    pictures = Pictures(tmp_path / "pics", update, wait=60)
    pictures.use(SCREEN)
    name = pictures.file_name("basic_clock", SCREEN)
    (tmp_path / "pics").mkdir()
    Image.new("L", (300, 200), 255).save(tmp_path / "pics" / name)
    yield pictures, name
    pictures.stop()
    release.set()


def test_the_library_shows_drawn_pictures_and_waits_for_the_others(tmp_path, ready_pictures):
    pictures, name = ready_pictures
    client = make_client(tmp_path, pictures)
    page = html.unescape(client.get("/library").text)
    assert f'<img src="/library/pictures/{name}" width="300"' in page
    assert "drawn at your screen's size with the plugin's\nsample data" in page
    assert 'hx-get="/library/word_clock/picture"' in page  # not drawn yet
    picture = client.get(f"/library/pictures/{name}")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert picture.headers["cache-control"] == "private, max-age=86400"
    assert client.get("/library/basic_clock/picture").text.count(f"/library/pictures/{name}") == 1


def test_the_picture_part_asks_again_until_the_picture_is_there(tmp_path, ready_pictures):
    pictures, _ = ready_pictures
    client = make_client(tmp_path, pictures)
    part = client.get("/library/word_clock/picture")
    assert part.status_code == 200 and 'hx-trigger="load delay:3s"' in part.text
    name = pictures.file_name("word_clock", SCREEN)
    shutil.copy(next((tmp_path / "pics").iterdir()), tmp_path / "pics" / name)
    part = client.get("/library/word_clock/picture").text
    assert f"/library/pictures/{name}" in part and "hx-get" not in part


def test_unknown_pictures_are_not_found(tmp_path, ready_pictures):
    client = make_client(tmp_path, ready_pictures[0])
    assert client.get("/library/pictures/word_clock-0123456789abcdef.png").status_code == 404
    assert client.get("/library/pictures/paperpi.toml").status_code == 404
    assert client.get("/library/nothing/picture").text.strip() == ""


def test_without_pictures_the_library_has_none(tmp_path):
    page = make_client(tmp_path, None).get("/library").text
    assert "/library/pictures/" not in page and "hx-get" not in page
    assert "sample data" not in page
