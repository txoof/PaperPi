"""The splash_screen plugin's own logic."""

from dataclasses import replace
from pathlib import Path

import pytest
import segno
from epdlib import ScreenMode, text
from pydantic import ValidationError

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


class FakeSocket:
    def __init__(self, address=None, error=None):
        self.address, self.error = address, error

    def __call__(self, *args):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def connect(self, target):
        if self.error:
            raise self.error

    def getsockname(self):
        return (self.address, 50000)


@pytest.mark.parametrize(
    ("fake", "expected"),
    [
        (FakeSocket("192.0.2.30"), "192.0.2.30"),
        (FakeSocket(error=OSError("Network is unreachable")), None),
        (FakeSocket("0.0.0.0"), None),
        (FakeSocket("127.0.1.1"), None),  # only this Pi itself
    ],
)
def test_ip_address(monkeypatch, fake, expected):
    monkeypatch.setattr(splash_screen.socket, "socket", fake)
    assert splash_screen.ip_address() == expected


@pytest.mark.parametrize(("name", "expected"), [("kitchen", "kitchen"), ("", None)])
def test_hostname(monkeypatch, name, expected):
    monkeypatch.setattr(splash_screen.socket, "gethostname", lambda: name)
    assert splash_screen.hostname() == expected


def test_hostname_error(monkeypatch):
    def broken():
        raise OSError("no name")

    monkeypatch.setattr(splash_screen.socket, "gethostname", broken)
    assert splash_screen.hostname() is None


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
    assert web_addresses(about, 8080) == ("http://192.0.2.10:8080", by_name)


def test_no_web_address_without_a_network():
    assert web_addresses(replace(SAMPLE, ip=None), 8080) is None


def test_the_default_port_is_the_web_interface_default():
    from paperpi.config import WebSettings

    assert Settings().port == WebSettings().port == 8080


@pytest.mark.parametrize("port", [0, 65536, "9000"])
def test_port_must_be_a_real_port_number(port):
    with pytest.raises(ValidationError):
        Settings(port=port)


def test_addresses_and_qr_code_use_the_port():
    ctx = replace(context(), settings=Settings(port=9000))
    values = draw(SAMPLE, ctx)
    assert values["ip"].replace("\n", "") == "http://192.0.2.10:9000"
    assert values["host"].replace("\n", "") == "http://paperpi.local:9000"
    box = PLUGIN.layout("splash", Settings()).prepare(800, 480, ScreenMode.bw()).boxes["qr"]
    expected = qr_code("http://192.0.2.10:9000", box.width, box.height)
    assert values["qr"].tobytes() == expected.tobytes()


def test_line_breaks_after_a_slash_come_first_most_even_first():
    options = line_breaks("https://github.com/txoof/PaperPi")
    assert options[:4] == [
        "https://github.com/txoof/PaperPi",
        "https://github.com/\ntxoof/PaperPi",  # as v1
        "https://\ngithub.com/txoof/PaperPi",
        "https://github.com/txoof/\nPaperPi",
    ]
    # Then after a "." (or "-" or ":"), then on three lines.
    assert options[4] == "https://github.\ncom/txoof/PaperPi"
    assert options[-1].count("\n") == 2


def test_line_breaks_never_inside_the_double_slash_or_at_the_end():
    for option in line_breaks("https://paperpi.example/"):
        assert ":/\n/" not in option and not option.endswith("\n")
    assert line_breaks("paperpi") == ["paperpi"]


def test_line_breaks_tries_few_three_line_splits():
    # A long name has hundreds; each one is measured, which is slow.
    options = line_breaks("http://" + "pi-" * 20 + "x.local:8080")
    assert sum(1 for o in options if o.count("\n") == 2) == 10


FONT = splash_screen.layouts.fonts.DOSIS_SEMIBOLD


def fit(address, size, width, height):
    return fit_address(address, FONT, size, width, height, 2, "…")


def test_fit_address_keeps_one_line_when_it_fits():
    assert fit("http://192.0.2.10:8080", 20, 1000, 100) == "http://192.0.2.10:8080"


def test_fit_address_breaks_after_a_slash_when_needed():
    size = 40
    one_line = text.load_font(FONT, size).getlength("http://192.0.2.10:8080")
    fitted = fit("http://192.0.2.10:8080", size, int(one_line) - 10, 400)
    assert fitted == "http://\n192.0.2.10:8080"


def test_fit_address_uses_a_smaller_size_for_the_broken_form():
    # Two lines are too wide at the block's own size, but fit at a smaller one; one line
    # would need breaks between letters at every size.
    size = 40
    longest = text.load_font(FONT, size).getlength("192.0.2.10:8080")
    fitted = fit("http://192.0.2.10:8080", size, int(0.9 * longest), 200)
    assert fitted == "http://\n192.0.2.10:8080"


def test_fit_address_falls_back_to_one_line():
    # Too narrow for any way of writing it: epdlib then breaks it between letters.
    assert fit("http://192.0.2.10:8080", 40, 30, 40) == "http://192.0.2.10:8080"


def test_long_host_name_is_broken_after_a_dash_not_inside_a_word():
    values = draw(replace(SAMPLE, hostname="paperpi-living-room-kitchen-shelf"), context(480, 800))
    host = values["host"]
    assert host.replace("\n", "") == "http://paperpi-living-room-kitchen-shelf.local:8080"
    assert "\n" in host
    assert all(line[-1] in "/.-:" for line in host.split("\n")[:-1])


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
    box = PLUGIN.layout("splash", Settings()).prepare(800, 480, ScreenMode.bw()).boxes["qr"]
    # The QR code holds the IP address, never the host name (some phones can't open it).
    expected = qr_code("http://192.0.2.10:8080", box.width, box.height)
    assert values["qr"].tobytes() == expected.tobytes()


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
        # Whole, and drawn with exactly the line breaks draw() chose (none inside a word).
        if not fit.complete or fit.lines != values[name].split("\n"):
            return False
    return True


@pytest.mark.parametrize(("width", "height"), SIZES)
@pytest.mark.parametrize(
    "about",
    [
        SAMPLE,
        replace(SAMPLE, ip="255.255.255.255", hostname="paperpi-living-room"),
        replace(SAMPLE, hostname="paperpi-living-room-kitchen"),
    ],
    ids=["sample", "long-names", "longer-name"],
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
