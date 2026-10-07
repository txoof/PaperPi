"""splash_screen: PaperPi's name, version and web address, shown at start and while no
plugin is switched on.

The scheduler shows this plugin first when PaperPi starts, for ``[display] splash_time``
seconds (default 60), then the other plugins. With no plugin switched on (e.g. the first
start after installing), it stays on screen until one is.
It is a plugin like any other so start-up needs no special drawing code; a ``[[plugin]]``
block can also put it in the rotation, but that is not what it is meant for.

It shows the address of PaperPi's web interface, as an IP address and as a host name, and
a QR code with the IP address, so a phone can open the web interface at once.
"""

import socket
from dataclasses import dataclass

import segno
from epdlib import text
from PIL import Image
from pydantic import Field

from ... import __version__
from ...plugin import Context, Plugin, PluginSettings, ready
from .layouts import ADDRESS_BLOCKS, LAYOUTS, PADDING

NAME = "PaperPi"
URL = "https://github.com/txoof/PaperPi"
NO_NETWORK = "No network"


@dataclass(frozen=True)
class About:
    """What the splash screen shows."""

    name: str
    version: str
    url: str
    ip: str | None
    """This Pi's address on the network; ``None`` without a network."""
    hostname: str | None
    """This Pi's name on the network (without ``.local``); ``None`` when unknown."""


class Settings(PluginSettings):
    port: int = Field(
        8080,
        ge=1,
        le=65535,
        strict=True,
        description="The web interface's port. The splash at start always uses [web] port",
    )


def ip_address() -> str | None:
    """The address other computers on the network reach this one at.

    Asks the system which address it would use to reach an outside address. No data is
    sent: "connecting" a UDP socket only picks the route.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # an address set aside for examples
            address = sock.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith(("0.", "127.")) else address


def hostname() -> str | None:
    """This Pi's name, e.g. ``paperpi``; ``None`` when the system doesn't say."""
    try:
        return socket.gethostname() or None
    except OSError:
        return None


def fetch(context: Context):
    return ready(About(NAME, __version__, URL, ip_address(), hostname()))


def web_addresses(about: About, port: int) -> tuple[str, str] | None:
    """The web interface's address by IP and by host name; ``None`` without a network."""
    if about.ip is None:
        return None
    host = about.hostname or ""
    if host and "." not in host:
        host += ".local"  # the name the Pi announces on the home network
    by_name = f"http://{host}:{port}" if host else ""
    return f"http://{about.ip}:{port}", by_name


def line_breaks(address: str) -> list[str]:
    """Ways to write ``address``: on one line, then broken after a "/", then (for a long
    host name) also after a ".", "-" or ":".

    epdlib only breaks lines at spaces (or, in a word that is too long, between letters),
    so these breaks are put in here. Within each kind the most even split comes first, e.g.
    "https://github.com/" and "txoof/PaperPi", as v1 showed it.
    """

    def after(chars: str) -> list[int]:
        return [
            i + 1
            for i, char in enumerate(address)
            if char in chars and address[i + 1 : i + 2] not in ("/", "")
        ]

    def split(points: tuple[int, ...]) -> str:
        edges = (0, *points, len(address))
        return "\n".join(address[a:b] for a, b in zip(edges, edges[1:], strict=False))

    def longest(points: tuple[int, ...]) -> int:
        edges = (0, *points, len(address))
        return max(b - a for a, b in zip(edges, edges[1:], strict=False))

    slashes, others = after("/"), after(".-:")
    two = sorted(((i,) for i in slashes), key=longest)
    two += sorted(((i,) for i in others), key=longest)
    points = sorted(slashes + others)
    # Only the most even three-line splits: a long name has hundreds, each one tried.
    three = sorted(((a, b) for a in points for b in points if a < b), key=longest)[:10]
    return [address] + [split(p) for p in two + three]


def fit_address(
    address: str, font: str, size: int, width: int, height: int, max_lines: int, ellipsis: str
) -> str:
    """The first way of writing ``address`` that epdlib draws exactly as given: whole, and
    with no other line breaks (checked the way epdlib will draw the block, with its
    ``shrink`` sizes). When none does: the one-line form, which epdlib breaks between
    letters.
    """
    smallest = text.load_font(font, max(1, round(size * text.SHRINK_STEPS[-1])))
    for option in line_breaks(address):
        lines = option.split("\n")
        # Quick check first: exact measuring is slow, and a line that is too wide even at
        # the smallest size can never be drawn as given.
        if any(smallest.getlength(line) > width for line in lines):
            continue
        fit = text.fit_text(font, size, option, width, height, max_lines, True, ellipsis)
        if fit.complete and fit.lines == lines:
            return option
    return address


def qr_code(address: str, width: int, height: int) -> Image.Image:
    """A QR code for ``address``, as large as fits, with whole pixels per square so it
    stays sharp (it is never scaled again: the block uses ``fit = "none"``)."""
    code = segno.make(address, error="m")
    border = 2  # white squares around the code, so phones find its edge
    rows = [[0] * border + list(row) + [0] * border for row in code.matrix]
    blank = [[0] * len(rows[0]) for _ in range(border)]
    rows = blank + rows + blank
    side = len(rows)
    small = Image.new("L", (side, side))
    small.putdata([0 if dark else 255 for row in rows for dark in row])
    scale = max(1, min(width, height) // side)
    return small.resize((side * scale, side * scale), Image.Resampling.NEAREST)


def draw(about: About, context: Context) -> dict:
    layout = PLUGIN.layout(context.layout, context.settings)
    prepared = layout.prepare(context.width, context.height, context.mode)
    short_side = min(context.width, context.height)
    values = {"name": about.name, "version": about.version}
    addresses = web_addresses(about, context.settings.port)
    texts = {"github": about.url}
    if addresses is None:
        texts["ip"] = NO_NETWORK
    else:
        texts["ip"], texts["host"] = addresses
        box = prepared.boxes["qr"]
        if box.width > 0 and box.height > 0:
            values["qr"] = qr_code(addresses[0], box.width, box.height)
    edge = round(PADDING * short_side)
    for name in ADDRESS_BLOCKS:
        value = texts.get(name, "")
        box = prepared.boxes[name]
        o = layout.blocks[name].options
        width, height = box.width - 2 * edge, box.height - 2 * edge
        if value and width > 0 and height > 0:
            size = prepared.font_sizes[name]
            value = fit_address(
                value, o["font"], size, width, height, o["max_lines"], o["ellipsis"]
            )
        values[name] = value
    return values


PLUGIN = Plugin(
    type="splash_screen",
    description="PaperPi's name, version and web address; shown at start, and while no plugin "
    "is switched on.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    # A fixed version and made-up addresses, so the sample images never change by
    # themselves and never show a real Pi's address.
    sample=About(NAME, "2.0.0", URL, "192.0.2.10", "paperpi"),
    # Nothing changes while PaperPi runs, except perhaps the IP address.
    refresh=3600,
)
