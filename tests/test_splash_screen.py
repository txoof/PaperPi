"""The splash_screen plugin's own logic."""

from dataclasses import replace
from pathlib import Path

import pytest
import segno
from epdlib import ScreenMode, text

from paperpi import __version__
from paperpi.plugin import Context, State, draw_update
from paperpi.plugins import splash_screen
from paperpi.plugins.splash_screen import (
    NAME,
    NO_NETWORK,
    PLUGIN,
    URL,
    About,
    Settings,
    draw,
    fetch,
    fit_address,
    line_breaks,
    qr_code,
    web_addresses,
)
from paperpi.plugins.splash_screen.layouts import ADDRESS_BLOCKS, PADDING

SAMPLE = PLUGIN.sample
# The screens the image tests use, the smallest Waveshare screen, and upright screens.
SIZES = [(1200, 825), (250, 122), (122, 250), (480, 800)]


def context(width=800, height=480, mode=None):
    return Context(Settings(), width, height, mode or ScreenMode.bw(), Path("."), "splash")


def test_fetch_shows_this_paperpi(monkeypatch):
    monkeypatch.setattr(splash_screen, "ip_address", lambda: "192.0.2.20")
    monkeypatch.setattr(splash_screen, "hostname", lambda: "kitchen")
    fetched = fetch(context())
    assert fetched.state is State.READY
    assert fetched.data == About(NAME, __version__, URL, "192.0.2.20", "kitchen")


def test_sample_is_fixed_and_made_up():
    # A fixed version keeps the sample images the same from one release to the next, and
    # 192.0.2.x is set aside for examples, so no real Pi's address is ever shown.
    assert SAMPLE == About(NAME, "2.0.0", URL, "192.0.2.10", "paperpi")


@pytest.mark.parametrize(
    ("hostname", "by_name"),
    [
        ("paperpi", "http://paperpi.local:8080"),
        ("pi.example.org", "http://pi.example.org:8080"),  # a name with a dot stays as it is
        (None, ""),
    ],
)
def test_web_addresses(hostname, by_name):
    about = replace(SAMPLE, hostname=hostname)
    assert web_addresses(about) == ("http://192.0.2.10:8080", by_name)


def test_no_web_address_without_a_network():
    assert web_addresses(replace(SAMPLE, ip=None)) is None


def test_the_port_is_the_web_interface_port():
    # docs/decisions/web-interface.md: plain HTTP on port 8080.
    assert splash_screen.WEB_PORT == 8080


@pytest.mark.parametrize(
    ("address", "options"),
    [
        (
            "https://github.com/txoof/PaperPi",
            [
                "https://github.com/txoof/PaperPi",
                "https://github.com/\ntxoof/PaperPi",  # the most even split first, as v1
                "https://\ngithub.com/txoof/PaperPi",
                "https://github.com/txoof/\nPaperPi",
            ],
        ),
        ("http://192.0.2.10:8080", ["http://192.0.2.10:8080", "http://\n192.0.2.10:8080"]),
        # Never between the two slashes of "//", never after a "/" at the end.
        ("https://paperpi.example/", ["https://paperpi.example/", "https://\npaperpi.example/"]),
        ("paperpi", ["paperpi"]),
    ],
)
def test_line_breaks(address, options):
    assert line_breaks(address) == options


FONT = splash_screen.layouts.fonts.DOSIS_SEMIBOLD


def test_fit_address_keeps_one_line_when_it_fits():
    assert fit_address("http://192.0.2.10:8080", FONT, 20, 1000, 100) == "http://192.0.2.10:8080"


def test_fit_address_breaks_after_a_slash_when_needed():
    size = 40
    one_line = text.load_font(FONT, size).getlength("http://192.0.2.10:8080")
    fitted = fit_address("http://192.0.2.10:8080", FONT, size, int(one_line) - 10, 400)
    assert fitted == "http://\n192.0.2.10:8080"


def test_fit_address_falls_back_to_one_line():
    # Too narrow for any way of writing it: epdlib then breaks it between letters.
    assert fit_address("http://192.0.2.10:8080", FONT, 40, 30, 40) == "http://192.0.2.10:8080"


def test_qr_code_holds_the_address_with_whole_pixels_per_square():
    image = qr_code("http://192.0.2.10:8080", 200, 150)
    side = segno.make("http://192.0.2.10:8080", error="m").symbol_size(border=2)[0]
    assert image.width == image.height
    assert image.width % side == 0 and image.width <= 150
    assert {color for _, color in image.getcolors()} == {0, 255}  # only black and white, never gray
    # The top left corner of a QR code: a white border, then a black square.
    scale = image.width // side
    assert image.getpixel((0, 0)) == 255
    assert image.getpixel((2 * scale, 2 * scale)) == 0


def test_draw_fills_every_block_of_the_layout():
    values = draw(SAMPLE, context())
    layout = PLUGIN.layout("splash", Settings())
    assert set(layout.prepare(800, 480, ScreenMode.bw()).boxes) == set(values)
    assert values["name"] == "PaperPi"
    assert values["version"] == "2.0.0"
    assert values["ip"].replace("\n", "") == "http://192.0.2.10:8080"
    assert values["host"].replace("\n", "") == "http://paperpi.local:8080"
    assert values["github"].replace("\n", "") == URL
    assert values["qr"].size[0] > 0


def test_draw_without_a_network():
    values = draw(replace(SAMPLE, ip=None), context())
    assert values["ip"] == NO_NETWORK
    assert values["host"] == ""
    assert "qr" not in values


def _complete(values, width, height):
    """True when every address is drawn whole: epdlib's own text fitting cut nothing."""
    layout = PLUGIN.layout("splash", Settings())
    prepared = layout.prepare(width, height, ScreenMode.bw())
    edge = round(PADDING * min(width, height))
    for name in ADDRESS_BLOCKS:
        box = prepared.boxes[name]
        o = layout.blocks[name].options
        fit = text.fit_text(
            o["font"],
            prepared.font_sizes[name],
            values[name],
            box.width - 2 * edge,
            box.height - 2 * edge,
            o["max_lines"],
            o["shrink"],
            o["ellipsis"],
        )
        if not fit.complete:
            return False
    return True


@pytest.mark.parametrize(("width", "height"), SIZES)
@pytest.mark.parametrize(
    "about",
    [
        SAMPLE,
        replace(SAMPLE, ip="255.255.255.255", hostname="paperpi-living-room"),
    ],
    ids=["sample", "long-names"],
)
def test_addresses_always_appear_whole(about, width, height):
    values = draw(about, context(width, height))
    assert _complete(values, width, height)


def test_a_small_screen_draws(tmp_path):
    ctx = Context(Settings(), 250, 122, ScreenMode.bw(), tmp_path, "splash")
    state, image = draw_update(PLUGIN, ctx, sample=True)
    assert state is State.READY
    assert image.size == (250, 122)
    assert image.getextrema() == (0, 255)  # something is drawn
