"""xkcd_comic: a random comic from xkcd.com, with its title and hover text."""

from __future__ import annotations

import io
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError
from pydantic import Field

from ... import webrequest
from ...plugin import Context, Plugin, PluginSettings, ready, setting
from .layouts import LAYOUTS

log = logging.getLogger(__name__)

SITE = "https://xkcd.com"
#: xkcd has no comic 404: its page answers "not found", as a joke.
MISSING = 404
#: The only server pictures are downloaded from.
PICTURES = "imgs.xkcd.com"
#: The only picture formats xkcd uses. Pillow's other formats are refused, to be safe.
FORMATS = ("PNG", "JPEG", "GIF")
SAMPLE = Path(__file__).parent / "sample" / "think_logically.png"
#: A small comic is enlarged to fill its space, at most this many times its own size.
MOST_ENLARGED = 2.0
#: Comics enlarged more than this come from xkcd's double-size picture, when it has one.
DOUBLE_FROM = 1.5
#: Seconds the double-size picture may take: it is not needed, so the normal one is shown
#: rather than letting a slow server use up the update's time.
DOUBLE_TIME = 10


class Settings(PluginSettings):
    comic: Literal["random", "newest"] = Field(
        "random",
        description="Which comic: a random one, or the newest one (a random one when the "
        "newest can't be shown)",
    )
    max_width: int = setting(
        800,
        group="Size limits",
        ge=1,
        le=4000,
        description="Comics wider than this many pixels are skipped",
    )
    max_height: int = setting(
        600,
        group="Size limits",
        ge=1,
        le=4000,
        description="Comics taller than this many pixels are skipped",
    )
    tries: int = setting(
        10,
        group="Size limits",
        ge=1,
        le=20,
        description="How many random comics to try before giving up, when they are too large "
        "or have no picture",
    )
    enlarge: bool = Field(
        True,
        description="Enlarge comics that are smaller than the space on the screen, at most "
        "to twice their size (else they keep their own size)",
    )


@dataclass(frozen=True)
class Comic:
    """What ``draw`` gets: one comic. ``image`` is the picture file's content, or a path.
    ``double`` means it is xkcd's double-size picture of the comic."""

    number: int
    title: str
    alt: str
    image: bytes | Path
    double: bool = False


class NoComicFound(ValueError):
    pass


def fetch(context: Context):
    """The newest or a random comic, ready to draw. When the newest can't be shown, a
    random one is shown instead, for this update only. Raises :class:`NoComicFound` when
    xkcd.com sends no number for its newest comic, or when no random comic in ``tries``
    tries can be shown (too large, or no picture)."""
    settings = context.settings
    space = _space(context) if settings.enlarge else None
    newest = _info(f"{SITE}/info.0.json")
    latest = _number(newest)
    if latest is None:
        raise NoComicFound("xkcd.com sent no number for its newest comic")
    if settings.comic == "newest":
        comic, why = _comic(latest, newest, settings, space)
        if comic:
            return ready(comic)
        log.info("can't show the newest xkcd comic (%d): %s; showing a random one", latest, why)
    numbers = [n for n in range(1, latest + 1) if n != MISSING]
    why = "none were tried"
    for _ in range(settings.tries):
        number = random.choice(numbers)
        info = _info(f"{SITE}/{number}/info.0.json")
        comic, why = _comic(number, info, settings, space)
        if comic:
            return ready(comic)
        log.info("skipping xkcd comic %d: %s", number, why)
    raise NoComicFound(f"no suitable xkcd comic in {settings.tries} tries (the last one: {why})")


def _space(context: Context) -> tuple[int, int]:
    """The size of the comic's space on the screen, in pixels."""
    layout = PLUGIN.layout(context.layout, context.settings)
    return layout.prepare(context.width, context.height, context.mode).content_size("comic")


def _info(url: str) -> dict:
    data = webrequest.get(url).json()
    return data if isinstance(data, dict) else {}


def _number(info: dict) -> int | None:
    number = info.get("num")
    return number if isinstance(number, int) and number > 0 else None


def _comic(
    number: int, info: dict, settings: Settings, space: tuple[int, int] | None = None
) -> tuple[Comic | None, str]:
    """The comic described by ``info`` (xkcd's JSON file for it), with its picture, or
    ``None`` and the reason it can't be shown. Network errors are raised: trying another
    comic would not help. With ``space`` (the comic's space on the screen), a comic that
    would be enlarged more than :data:`DOUBLE_FROM` times comes from xkcd's double-size
    picture, when there is one."""
    url = info.get("img")
    if not picture_address(url):
        return None, "it has no picture"  # e.g. an interactive comic
    body = webrequest.get(url).body
    try:
        width, height = _size(body)
    except _Unusable:
        return None, "its picture is not a PNG, JPEG or GIF file, or is damaged"
    if width > settings.max_width or height > settings.max_height:
        return None, f"it is {width}x{height} pixels, larger than the settings allow"
    title = str(info.get("safe_title") or info.get("title") or "")
    alt = str(info.get("alt") or "")
    if space and min(space[0] / width, space[1] / height) > DOUBLE_FROM:
        double = _double(url, width, height)
        if double:
            return Comic(number, title, alt, double, double=True), ""
    return Comic(number, title, alt, body), ""


class _Unusable(Exception):
    pass


def _size(body: bytes) -> tuple[int, int]:
    """The size of a picture file. Raises :class:`_Unusable` for a file that is not a PNG,
    JPEG or GIF picture, or is damaged."""
    try:
        with Image.open(io.BytesIO(body), formats=FORMATS) as picture:
            picture.load()  # decodes it all, so a damaged file is found here, not in draw
            return picture.size
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise _Unusable from None


def double_address(url: str) -> str:
    """The address of xkcd's double-size picture: ``name.png`` -> ``name_2x.png``."""
    base, dot, extension = url.rpartition(".")
    return f"{base}_2x.{extension}" if dot and "/" not in extension else f"{url}_2x"


def _double(url: str, width: int, height: int) -> bytes | None:
    """xkcd's double-size picture of a ``width`` x ``height`` comic, or ``None`` when it
    has none or it can't be used (not about twice the size, or damaged)."""
    address = double_address(url)
    if not picture_address(address):
        return None
    try:
        body = webrequest.get(address, total=DOUBLE_TIME).body
        double_width, double_height = _size(body)
        if _near(double_width, 2 * width) and _near(double_height, 2 * height):
            return body
    except (webrequest.WebError, _Unusable):
        pass
    log.debug("no double-size picture for %s", url)
    return None


def _near(value: int, wanted: int) -> bool:
    return abs(value - wanted) <= max(2, wanted * 0.02)


def picture_address(url) -> bool:
    """True for a picture file on xkcd's picture server, over https. Interactive comics
    have only the folder, ``https://imgs.xkcd.com/comics/``, which is refused."""
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.hostname == PICTURES
        and bool(parts.path.rsplit("/", 1)[-1])
    )


# --- Drawing ---------------------------------------------------------------------------------


def _open(image: bytes | Path) -> Image.Image:
    picture = Image.open(io.BytesIO(image) if isinstance(image, bytes) else image, formats=FORMATS)
    picture.load()
    return picture


def fit(picture: Image.Image, double: bool, width: int, height: int, most: float) -> Image.Image:
    """The comic for a ``width`` x ``height`` space: enlarged to fill it, but at most to
    ``most`` times its own size (half the pixel size of a ``double`` picture), in the
    middle of a white picture of exactly that size. A comic larger than the space is
    returned as it is; the layout shrinks it."""
    own = 2 if double else 1
    scale = min(own * width / picture.width, own * height / picture.height, most)
    if scale < 1:
        return picture
    size = (round(picture.width * scale / own), round(picture.height * scale / own))
    if size != picture.size:
        picture = picture.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    return keep_size(picture, width, height)


def keep_size(picture: Image.Image, width: int, height: int) -> Image.Image:
    """A comic smaller than the space (``width`` x ``height``) in the middle of a white
    picture of exactly that size, so the layout doesn't enlarge it. Larger comics are
    returned as they are; the layout shrinks them."""
    if picture.width > width or picture.height > height:
        return picture
    page = Image.new("RGB", (width, height), "white")
    rgba = picture.convert("RGBA")  # keeps transparent parts white
    page.paste(rgba, ((width - picture.width) // 2, (height - picture.height) // 2), rgba)
    return page


def draw(comic: Comic, context: Context) -> dict:
    settings = context.settings
    layout = PLUGIN.layout(context.layout, settings)
    picture = _open(comic.image)
    space = layout.prepare(context.width, context.height, context.mode).content_size("comic")
    picture = fit(picture, comic.double, *space, MOST_ENLARGED if settings.enlarge else 1)
    title = f"{comic.number}: {comic.title}" if comic.title else str(comic.number)
    values = {"comic": picture, "title": title, "alt": comic.alt}
    return {name: value for name, value in values.items() if name in layout.blocks}


PLUGIN = Plugin(
    type="xkcd_comic",
    title="xkcd",
    network="internet",
    description="A random comic from xkcd.com, with its title and hover text.",
    settings=Settings,
    layouts=LAYOUTS,
    layout_titles={
        "comic_title_alttext": "Comic, title and hover text",
        "comic_title": "Comic and title",
        "comic_only": "Comic only",
    },
    fetch=fetch,
    draw=draw,
    # "Think Logically" (xkcd 1112) by Randall Munroe, CC BY-NC 2.5: see sample/LICENSE.
    sample=Comic(
        1112,
        "Think Logically",
        "I've developed a more logical set of rules but the people on the chess community "
        "have a bunch of stupid emotional biases and won't reply to my posts.",
        SAMPLE,
    ),
    refresh=20 * 60,
)
