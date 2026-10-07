"""splash_screen: PaperPi's name, version and web address, shown once at start.

With ``[display] splash = true`` (the default), the scheduler shows this plugin first when
PaperPi starts, for :data:`~paperpi.limits.SPLASH_TIME` seconds, then the other plugins.
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

from ... import __version__
from ...plugin import Context, Plugin, PluginSettings, ready
from .layouts import ADDRESS_BLOCKS, LAYOUTS, PADDING

NAME = "PaperPi"
URL = "https://github.com/txoof/PaperPi"
#: The port of the web interface (docs/decisions/web-interface.md). M5 replaces this with
#: the port setting of the web interface.
WEB_PORT = 8080
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


class Settings(PluginSettings):
    pass


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
    try:
        return socket.gethostname() or None
    except OSError:
        return None


def fetch(context: Context):
    return ready(About(NAME, __version__, URL, ip_address(), hostname()))


def web_addresses(about: About) -> tuple[str, str] | None:
    """The web interface's address by IP and by host name; ``None`` without a network."""
    if about.ip is None:
        return None
    host = about.hostname or ""
    if host and "." not in host:
        host += ".local"  # the name the Pi announces on the home network
    by_name = f"http://{host}:{WEB_PORT}" if host else ""
    return f"http://{about.ip}:{WEB_PORT}", by_name


def line_breaks(address: str) -> list[str]:
    """Ways to write ``address``: on one line, then on two lines broken after a "/".

    epdlib only breaks lines at spaces (or, in a word that is too long, between letters),
    so the breaks after a "/" are put in here. The most even split comes first, e.g.
    "https://github.com/" and "txoof/PaperPi", as v1 showed it.
    """
    breaks = [
        i + 1
        for i, char in enumerate(address)
        if char == "/" and address[i + 1 : i + 2] not in ("/", "")
    ]
    breaks.sort(key=lambda i: max(i, len(address) - i))
    return [address] + [f"{address[:i]}\n{address[i:]}" for i in breaks]


def fit_address(address: str, font: str, size: int, width: int, height: int) -> str:
    """The way of writing ``address`` that fits whole at the largest font size.

    Tries every way at the block's own size, then at the smaller sizes its ``shrink``
    allows (epdlib picks the same size again when it draws). When none fits: the one-line
    form, which epdlib breaks between letters, so the address is still never cut off.
    """
    options = line_breaks(address)
    for step in text.SHRINK_STEPS:
        step_size = max(1, round(size * step))
        for option in options:
            lines = option.count("\n") + 1
            fit = text.fit_text(font, step_size, option, width, height, lines, False, "…")
            if fit.complete and len(fit.lines) == lines:
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
    addresses = web_addresses(about)
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
        font = layout.blocks[name].options["font"]
        width, height = box.width - 2 * edge, box.height - 2 * edge
        if value and width > 0 and height > 0:
            value = fit_address(value, font, prepared.font_sizes[name], width, height)
        values[name] = value
    return values


PLUGIN = Plugin(
    type="splash_screen",
    description="PaperPi's name, version and web address; shown once at start.",
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
