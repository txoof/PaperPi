"""The Preview button on a plugin's settings page (M5 part 3b-1)."""

import base64
import html
import io
import re
import threading

import pytest
from epdlib import ScreenMode
from fastapi.testclient import TestClient
from PIL import Image

from paperpi import config, limits
from paperpi.plugin import State
from paperpi.runner import PluginFailed, PluginTimeout, UpdateResult, run_update
from paperpi.web import auth
from paperpi.web.app import create_app
from paperpi.web.plugins import PluginEditor
from paperpi.web.preview import Previewer, PreviewFailed

from .test_web_settings import CONFIG, PI
from .test_web_settings import kinds as kinds  # a fixture


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
    client = TestClient(app, follow_redirects=False, base_url=PI)
    client.app_editor = editor
    return client


def preview(client, index, plugin_id, **form):
    response = client.post(f"/plugins/{index}/preview", data={"id": plugin_id, **form})
    assert response.status_code == 200  # htmx only shows answers with 200
    return html.unescape(response.text)


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
    preview(make_client(cfg, reloads, update), 2, "Comic", time_limit="20", layout="nope")
    assert "Fix these settings first" not in preview(
        make_client(cfg, reloads, update), 2, "Comic", time_limit="20"
    )
    assert [call[3] for call in update.calls] == [20]
    assert cfg.read_text() == CONFIG and reloads == []


@pytest.mark.parametrize(
    ("error", "note"),
    [
        (PluginTimeout("xkcd_comic", "stopped"), "The real data took longer than 30 seconds."),
        (PluginFailed("xkcd_comic", "URLError: no network"), "drawn: URLError: no network."),
        (State.NOTHING, "The plugin has nothing to show right now"),
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
    update = FakeUpdate(PluginTimeout("basic_clock", "stopped"), PluginTimeout("x", "Late"))
    page = preview(make_client(cfg, reloads, update), 0, "Clock")
    assert "took longer than 45 seconds. The sample data could not be drawn either: Late." in page
    assert "<img" not in page


def test_a_sample_after_missing_settings_does_not_say_either(cfg, reloads):
    page = preview(make_client(cfg, reloads, FakeUpdate(PluginFailed("x", "Boom"))), 1, "Weather")
    assert "settings first: email. The sample data could not be drawn: Boom." in page


def test_a_sample_without_a_picture_says_so(cfg, reloads):
    def no_picture(plugin_type, context, *, sample, time_limit):
        return UpdateResult(State.READY, None, 0.1)

    page = preview(make_client(cfg, reloads, no_picture), 1, "Weather")
    assert "The sample data gives no picture." in page


def test_wrong_values_are_listed_and_nothing_is_drawn(cfg, reloads):
    update = FakeUpdate()
    page = preview(make_client(cfg, reloads, update), 1, "Weather", lat="200")
    assert "Fix these settings first" in page and "<code>lat</code>" in page
    assert update.calls == []


def test_a_block_that_changed_meanwhile_is_not_drawn(cfg, reloads):
    update = FakeUpdate()
    page = preview(make_client(cfg, reloads, update), 0, "Weather")
    assert "changed" in page and update.calls == []


def test_the_screen_size_and_type_come_from_the_display_settings(cfg, reloads):
    cfg.write_text(
        CONFIG.replace(
            'type = "virtual"',
            'type = "virtual"\nwidth = 800\nheight = 480\nrotation = 90\nmode = "gray4"',
        )
    )
    update = FakeUpdate()
    page = preview(make_client(cfg, reloads, update), 0, "Clock")
    context = update.calls[0][1]
    assert (context.width, context.height, context.mode) == (480, 800, ScreenMode.gray(4))
    assert picture(page).size == (480, 800)


def test_a_new_screen_size_waits_for_the_next_start(cfg, reloads):
    """Previews draw for the screen as it runs: a new size or mode applies at the next start."""
    update = FakeUpdate()
    client = make_client(cfg, reloads, update)
    client.app_editor.display = config.DisplaySettings(type="virtual", width=300, height=200)
    cfg.write_text(CONFIG.replace('type = "virtual"', 'type = "virtual"\nwidth = 800\nmode = "bw"'))
    preview(client, 0, "Clock")
    context = update.calls[0][1]
    assert (context.width, context.height, context.mode) == (300, 200, ScreenMode.gray(16))


def test_a_config_file_paperpi_cant_use_is_not_drawn(cfg, reloads):
    cfg.write_text(CONFIG.replace('type = "virtual"', 'type = "nope"'))
    update = FakeUpdate()
    page = preview(make_client(cfg, reloads, update), 0, "Clock")
    assert "must be fixed first" in page and update.calls == []


def test_of_two_blocks_with_the_same_id_the_right_one_is_drawn(cfg, reloads):
    # PaperPi leaves out the second one ("used twice"): it can't be drawn, and says why.
    cfg.write_text(CONFIG + '\n[[plugin]]\nid = "clock"\ntype = "word_clock"\n')
    update = FakeUpdate()
    page = preview(make_client(cfg, reloads, update), 3, "clock")
    assert (
        "This plugin can't be drawn" in page
        and "already used by the plugin block at line 5" in page
    )
    assert update.calls == []


def test_only_the_problems_of_this_block_are_listed(cfg, reloads):
    cfg.write_text(CONFIG + '\n[[plugin]]\nid = "Broken"\ntype = "no_such_type"\n')
    page = preview(make_client(cfg, reloads, FakeUpdate()), 0, "Clock")
    assert "<img" in page and "no_such_type" not in page


def test_an_empty_secret_field_keeps_the_saved_secret(cfg, reloads, kinds):
    update = FakeUpdate(State.READY, State.READY)
    client = make_client(cfg, reloads, update)
    preview(client, kinds, "Kinds", token="")
    preview(client, kinds, "Kinds", token="NEWKEY")
    tokens = [call[1].settings.token.get_secret_value() for call in update.calls]
    assert tokens == ["SAVEDKEY", "NEWKEY"] and "NEWKEY" not in cfg.read_text()


def test_a_wrong_form_never_shows_a_secret(cfg, reloads, kinds):
    page = preview(
        make_client(cfg, reloads, FakeUpdate()), kinds, "Kinds", token="NEWKEY", words="d"
    )
    assert "Fix these settings first" in page
    assert "NEWKEY" not in page and "SAVEDKEY" not in page


def test_one_preview_at_a_time(cfg, reloads):
    started, go_on = threading.Event(), threading.Event()

    def slow(*args, **options):
        started.set()
        go_on.wait(5)
        return FakeUpdate()(*args, **options)

    client = make_client(cfg, reloads, slow)
    pages = []
    first = threading.Thread(target=lambda: pages.append(preview(client, 0, "Clock")))
    first.start()
    try:
        assert started.wait(5)
        assert "Another preview is being drawn" in preview(client, 0, "Clock")
    finally:
        go_on.set()
        first.join(5)
    assert not first.is_alive() and "<img" in pages[0]
    assert "<img" in preview(client, 0, "Clock")


def test_after_an_error_the_next_preview_can_be_drawn(cfg, reloads):
    def broken(*args, **options):
        raise RuntimeError("no process could be started")

    update = FakeUpdate()
    previewer = Previewer(broken)
    job = PluginEditor(cfg).preview_job(0, "Clock", {})
    with pytest.raises(RuntimeError):
        previewer.draw(job)
    previewer._update = update
    assert previewer.draw(job).png and len(update.calls) == 1


def test_an_unexpected_error_is_shown_and_logged(cfg, reloads, caplog):
    def broken(*args, **options):
        raise OSError("no more processes")

    page = preview(make_client(cfg, reloads, broken), 0, "Clock")
    assert "could not be drawn. PaperPi's log has the details." in page
    assert "no more processes" in caplog.text and "no more processes" not in page


def test_no_preview_is_started_while_paperpi_stops(cfg, reloads):
    previewer = Previewer(FakeUpdate())
    previewer.stop()
    with pytest.raises(PreviewFailed, match="PaperPi is stopping"):
        previewer.draw(PluginEditor(cfg).preview_job(0, "Clock", {}))


def test_when_the_real_data_was_stopped_for_a_stop_no_sample_is_drawn(cfg, reloads):
    previewer = None

    def stopped(plugin_type, context, *, sample, time_limit):
        previewer.stop()  # what runner.stop_all and paperpi run do at a stop
        raise PluginFailed(plugin_type, "process ended without a result")

    previewer = Previewer(stopped)
    with pytest.raises(PreviewFailed, match="PaperPi is stopping"):
        previewer.draw(PluginEditor(cfg).preview_job(0, "Clock", {}))


def test_an_ended_log_in_opens_the_log_in_page_not_inside_the_preview(cfg, reloads):
    paperpi_auth = auth.Auth(cfg, config.WebSettings(login=True, password_hash="x" * 10))
    client = TestClient(create_app(paperpi_auth, PluginEditor(cfg)), base_url=PI)
    response = client.post(
        "/plugins/0/preview", data={"id": "Clock"}, headers={"HX-Request": "true"}
    )
    assert response.headers["HX-Redirect"] == "/login" and response.text == ""
    response = client.post("/plugins/0/preview", data={"id": "Clock"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_pages_allow_pictures_sent_inside_the_page(cfg, reloads):
    response = make_client(cfg, reloads, FakeUpdate()).get("/plugins")
    assert "img-src 'self' data:;" in response.headers["Content-Security-Policy"]


def test_a_real_preview_of_a_clock(cfg, reloads):
    client = make_client(cfg, reloads, run_update)
    page = preview(client, 0, "Clock")
    assert "Real data." in page
    assert picture(page).size == config.parse(CONFIG).display.layout_size
