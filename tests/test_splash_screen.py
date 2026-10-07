"""The splash_screen plugin's own logic."""

from dataclasses import replace
from pathlib import Path

import pytest
from epdlib import ScreenMode

from paperpi import __version__
from paperpi.plugin import Context, State, draw_update
from paperpi.plugins.splash_screen import NAME, PLUGIN, URL, About, Settings, draw, fetch, split_url


def context(width=800, height=480, mode=None):
    return Context(Settings(), width, height, mode or ScreenMode.bw(), Path("."), "splash")


def test_fetch_shows_this_paperpi():
    fetched = fetch(context())
    assert fetched.state is State.READY
    assert fetched.data == About("PaperPi", __version__, "https://github.com/txoof/PaperPi")


def test_sample_is_fixed():
    # A fixed version keeps the sample images the same from one release to the next.
    assert PLUGIN.sample == About(NAME, "2.0.0", URL)


@pytest.mark.parametrize(
    ("url", "split"),
    [
        ("https://github.com/txoof/PaperPi", "https://github.com/\ntxoof/PaperPi"),
        ("http://192.0.2.10/paperpi", "http://192.0.2.10/\npaperpi"),
        ("paperpi.example/about", "paperpi.example/\nabout"),
        # Nothing after the server name: nothing to break.
        ("https://paperpi.example/", "https://paperpi.example/"),
        ("https://paperpi.example", "https://paperpi.example"),
        ("paperpi", "paperpi"),
    ],
)
def test_split_url_breaks_after_the_server_name(url, split):
    assert split_url(url) == split


def test_draw_fills_every_block_of_the_layout():
    values = draw(PLUGIN.sample, context())
    assert values == {
        "name": "PaperPi",
        "version": "2.0.0",
        "url": "https://github.com/\ntxoof/PaperPi",
    }
    layout = PLUGIN.layout("splash", Settings())
    assert set(layout.prepare(800, 480, ScreenMode.bw()).boxes) == set(values)


def test_a_long_version_draws_on_a_small_screen(tmp_path):
    plugin = replace(PLUGIN, sample=About(NAME, "2.10.11.dev12", URL))
    ctx = Context(Settings(), 250, 122, ScreenMode.bw(), tmp_path, "splash")
    state, image = draw_update(plugin, ctx, sample=True)
    assert state is State.READY
    assert image.size == (250, 122)
    assert image.getextrema() == (0, 255)  # something is drawn
