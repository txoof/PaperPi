"""The Preview button on a plugin's settings page (M5 part 3b-1)."""

import base64
import io
import re
import threading

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from paperpi import config, limits
from paperpi.plugin import State
from paperpi.runner import PluginFailed, PluginTimeout, UpdateResult, run_update
from paperpi.web import auth
from paperpi.web.app import create_app
from paperpi.web.plugins import PluginEditor
from paperpi.web.preview import Previewer

from .test_web_settings import CONFIG, PI


class FakeUpdate:
    """Stands in for the plugin process: answers each update from ``answers`` in turn (a
    State, or an error to raise) and notes what it was asked."""

    def __init__(self, *answers):
        self.answers = list(answers) or [State.READY]
        self.calls = []

    def __call__(self, plugin_type, context, *, sample, time_limit):
        self.calls.append((plugin_type, context, sample, time_limit))
        assert context.storage.is_dir() and not any(context.storage.iterdir())
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        image = Image.new("L", (context.width, context.height), 255 if sample else 0)
        return UpdateResult(answer, None if answer is State.NOTHING else image, 0.5)


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def reloads():
    return []


def make_client(cfg, reloads, update):
    editor = PluginEditor(cfg, lambda: reloads.append(1))
    editor.loaded(CONFIG)
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=False))
    app = create_app(paperpi_auth, editor, Previewer(update))
    return TestClient(app, follow_redirects=False, base_url=PI)


def preview(client, index, plugin_id, **form):
    response = client.post(f"/plugins/{index}/preview", data={"id": plugin_id, **form})
    assert response.status_code == 200  # htmx only shows answers with 200
    return response.text


def picture(page):
    found = re.search(r'src="data:image/png;base64,([^"]+)"', page)
    return Image.open(io.BytesIO(base64.b64decode(found.group(1))))


def test_the_settings_page_has_a_preview_button(cfg, reloads):
    page = make_client(cfg, reloads, FakeUpdate()).get("/plugins/0/settings?id=Clock").text
    assert 'hx-post="/plugins/0/preview"' in page and 'hx-target="#preview"' in page
    assert '<div id="preview"' in page


def test_a_preview_draws_real_data_at_the_screens_size(cfg, reloads):
    update = FakeUpdate(State.READY)
    page = preview(make_client(cfg, reloads, update), 0, "Clock")
    plugin_type, context, sample, time_limit = update.calls[0]
    width, height = config.parse(CONFIG).display.layout_size
    assert (plugin_type, sample, len(update.calls)) == ("basic_clock", False, 1)
    assert (context.width, context.height) == (width, height)
    assert not context.storage.exists()  # a new folder for each preview, deleted after
    assert picture(page).size == (width, height) and picture(page).getpixel((0, 0)) == 0
    assert "Real data." in page and "Sample data" not in page and "alert" not in page


def test_real_data_may_take_the_plugins_time_limit_but_at_most_45_s(cfg, reloads):
    update = FakeUpdate(State.READY, State.READY)
    client = make_client(cfg, reloads, update)
    preview(client, 0, "Clock")  # the default time limit, 60 s
    preview(client, 2, "Comic")  # time_limit = 30
    assert [call[3] for call in update.calls] == [limits.PREVIEW_LIVE, 30]


def test_the_preview_uses_the_form_not_the_file_and_saves_nothing(cfg, reloads):
    update = FakeUpdate(State.READY)
    preview(make_client(cfg, reloads, update), 2, "Comic", time_limit="20", name="New")
    assert update.calls[0][3] == 20
    assert cfg.read_text() == CONFIG and reloads == []


@pytest.mark.parametrize(
    ("error", "note"),
    [
        (PluginTimeout("xkcd_comic", "stopped"), "The real data took longer than 30 seconds."),
        (PluginFailed("xkcd_comic", "URLError: no network"), "could not be drawn: URLError"),
        (State.NOTHING, "It has nothing to show right now"),
    ],
)
def test_without_real_data_the_sample_is_drawn_and_says_why(cfg, reloads, error, note):
    update = FakeUpdate(error, State.READY)
    page = preview(make_client(cfg, reloads, update), 2, "Comic")
    assert [call[2] for call in update.calls] == [False, True]
    assert update.calls[1][3] == limits.PREVIEW_SAMPLE
    assert "Sample data, not real data." in page and note in page
    assert picture(page).getpixel((0, 0)) == 255


def test_without_a_required_setting_only_the_sample_is_drawn(cfg, reloads):
    update = FakeUpdate(State.READY)
    page = preview(make_client(cfg, reloads, update), 1, "Weather")
    assert [call[2] for call in update.calls] == [True]
    assert "Real data needs these settings first: email." in page


def test_a_typed_required_setting_is_used_before_saving(cfg, reloads):
    update = FakeUpdate(State.READY)
    preview(make_client(cfg, reloads, update), 1, "Weather", email="me@example.org")
    context = update.calls[0][1]
    assert update.calls[0][2] is False and context.settings.email == "me@example.org"


def test_an_alert_says_so(cfg, reloads):
    page = preview(make_client(cfg, reloads, FakeUpdate(State.ALERT)), 0, "Clock")
    assert "Shown as an alert." in page


def test_when_the_sample_fails_too_both_reasons_are_shown(cfg, reloads):
    update = FakeUpdate(PluginTimeout("basic_clock", "stopped"), PluginFailed("x", "Boom"))
    page = preview(make_client(cfg, reloads, update), 0, "Clock")
    assert "took longer than 45 seconds. Drawing the sample data failed too: Boom" in page
    assert "<img" not in page


def test_wrong_values_are_listed_and_nothing_is_drawn(cfg, reloads):
    update = FakeUpdate()
    page = preview(make_client(cfg, reloads, update), 1, "Weather", lat="200")
    assert "Fix these settings first" in page and "<code>lat</code>" in page
    assert update.calls == []


def test_a_block_that_changed_meanwhile_is_not_drawn(cfg, reloads):
    update = FakeUpdate()
    page = preview(make_client(cfg, reloads, update), 0, "Weather")
    assert 'class="problem"' in page and update.calls == []


def test_one_preview_at_a_time(cfg, reloads):
    started, go_on = threading.Event(), threading.Event()

    def slow(*args, **options):
        started.set()
        go_on.wait(5)
        return FakeUpdate()(*args, **options)

    client = make_client(cfg, reloads, slow)
    first = threading.Thread(target=preview, args=(client, 0, "Clock"))
    first.start()
    try:
        assert started.wait(5)
        assert "Another preview is being drawn" in preview(client, 0, "Clock")
    finally:
        go_on.set()
        first.join(5)
    assert "<img" in preview(client, 0, "Clock")


def test_pages_allow_pictures_sent_inside_the_page(cfg, reloads):
    response = make_client(cfg, reloads, FakeUpdate()).get("/plugins")
    assert "img-src 'self' data:;" in response.headers["Content-Security-Policy"]


def test_a_real_preview_of_a_clock(cfg, reloads):
    client = make_client(cfg, reloads, run_update)
    page = preview(client, 0, "Clock")
    assert "Real data." in page
    assert picture(page).size == config.parse(CONFIG).display.layout_size
