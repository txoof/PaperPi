"""Example pictures in the Plugin Library (M5 part 3b-2)."""

import html
import itertools
import shutil
import time
from pathlib import Path

import pytest
from epdlib import ScreenMode
from fastapi.testclient import TestClient
from PIL import Image

from paperpi import config
from paperpi.plugin import State
from paperpi.runner import PluginFailed
from paperpi.web import auth
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


def started(folder, package, update, screen=SCREEN, wait=0.0):
    pictures = Pictures(folder, update, package=package, wait=wait)
    pictures.use(screen)
    return pictures


def drawn(pictures, *types):
    until(lambda: all(not pictures.shown(t).waiting for t in types))
    return [pictures.shown(t) for t in types]


def test_each_plugin_is_drawn_once_with_its_sample_data(tmp_path, package):
    update = FakeUpdate(State.READY, State.READY)
    pictures = started(tmp_path / "pics", package, update)
    fake, broken = drawn(pictures, "fake", "broken")
    assert fake.file.startswith("fake-") and fake.file.endswith(".png") and fake.screen == SCREEN
    image = Image.open(tmp_path / "pics" / fake.file)
    assert image.size == (300, 200)
    assert "broken" in broken.problem and not broken.file
    [(plugin_type, context, sample, time_limit)] = update.calls  # not default, not broken
    assert (plugin_type, sample, time_limit) == ("fake", True, 10.0)
    assert (context.width, context.height, context.mode) == (300, 200, SCREEN.mode)
    assert context.layout == "one" and context.settings.act == "ok"
    pictures.use(SCREEN)  # e.g. a config reload: nothing to draw again
    time.sleep(0.1)
    assert len(update.calls) == 1 and pictures.shown("fake") == fake
    assert sorted(p.name for p in (tmp_path / "pics").iterdir()) == [fake.file]
    pictures.stop()


def test_a_changed_plugin_or_screen_is_drawn_again(tmp_path, package, monkeypatch):
    update = FakeUpdate(*[State.READY] * 3)
    pictures = started(tmp_path / "pics", package, update)
    [first] = drawn(pictures, "fake")
    code = Path(__import__(package).__file__).parent / "fake" / "__init__.py"
    code.write_text(code.read_text() + "\n# changed\n")
    [second] = drawn(pictures, "fake")  # opening the page notices the change
    assert second.file != first.file
    other = Screen(200, 300, ScreenMode.bw())
    pictures.use(other)
    until(lambda: pictures.shown("fake").file not in ("", second.file))
    third = pictures.shown("fake")
    assert third.screen == other and Image.open(tmp_path / "pics" / third.file).size == (200, 300)
    until(lambda: [p.name for p in (tmp_path / "pics").iterdir()] == [third.file])
    assert len(update.calls) == 3
    pictures.stop()


def test_a_picture_that_fails_says_why_and_is_not_tried_again(tmp_path, package):
    update = FakeUpdate(PluginFailed("fake", "ValueError: no font"))
    pictures = started(tmp_path / "pics", package, update)
    [fake] = drawn(pictures, "fake")
    assert fake.problem == "Its sample data could not be drawn: ValueError: no font"
    pictures.use(SCREEN)
    time.sleep(0.1)
    assert len(update.calls) == 1 and pictures.shown("fake").problem == fake.problem
    pictures.stop()


def test_nothing_to_show_is_a_problem_too(tmp_path, package):
    pictures = started(tmp_path / "pics", package, FakeUpdate(State.NOTHING))
    assert drawn(pictures, "fake")[0].problem == "Its sample data gives no picture."
    pictures.stop()


def test_drawing_waits_after_the_start_unless_the_page_is_opened(tmp_path, package):
    update = FakeUpdate()
    pictures = started(tmp_path / "pics", package, update, wait=60)
    time.sleep(0.1)
    assert update.calls == []
    assert pictures.shown("fake").waiting  # the page is opened: start now
    until(lambda: pictures.shown("fake").file)
    pictures.stop()


def test_stopped_pictures_draw_nothing(tmp_path, package):
    update = FakeUpdate()
    pictures = started(tmp_path / "pics", package, update, wait=60)
    pictures.stop()
    pictures.shown("fake")
    time.sleep(0.1)
    assert update.calls == []


def test_no_folder_means_no_pictures(package):
    pictures = Pictures(None, FakeUpdate(), package=package)
    pictures.use(SCREEN)
    assert pictures.shown("fake") is None and pictures.path("fake-0123456789abcdef.png") is None


@pytest.mark.parametrize(
    "name",
    ["../paperpi.toml", "fake-0123456789abcdef.txt", "fake-0123.png", "-0123456789abcdef.png",
     "a/b-0123456789abcdef.png", "fake-0123456789ABCDEF.png", ".fake-0123456789abcdef.png.part"],
)  # fmt: skip
def test_only_picture_files_are_given_out(tmp_path, name):
    folder = tmp_path / "pics"
    (folder / "a").mkdir(parents=True)
    (folder / name).write_bytes(b"x")  # even when the file is there
    assert Pictures(folder).path(name) is None


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
    """Real plugins, one picture saved already (as if drawn), drawing not started yet."""
    pictures = Pictures(tmp_path / "pics", FakeUpdate(), wait=60)
    pictures.use(SCREEN)
    name = pictures.file_name("basic_clock", SCREEN)
    (tmp_path / "pics").mkdir()
    Image.new("L", (300, 200), 255).save(tmp_path / "pics" / name)
    yield pictures, name
    pictures.stop()


def test_the_library_shows_drawn_pictures_and_waits_for_the_others(tmp_path, ready_pictures):
    pictures, name = ready_pictures
    client = make_client(tmp_path, pictures)
    page = html.unescape(client.get("/library").text)
    assert f'<img src="/library/pictures/{name}" width="300"' in page
    assert "drawn at your screen's size with the plugin's sample data" in page
    assert 'hx-get="/library/word_clock/picture"' in page  # not drawn yet
    picture = client.get(f"/library/pictures/{name}")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert picture.headers["cache-control"] == "max-age=86400"
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
