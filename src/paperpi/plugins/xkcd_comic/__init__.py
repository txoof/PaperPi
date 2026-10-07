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
from ...plugin import Context, Plugin, PluginSettings, ready
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


class Settings(PluginSettings):
    comic: Literal["random", "newest"] = Field(
        "random",
        description="Which comic: a random one, or the newest one (a random one when the "
        "newest can't be shown)",
    )
    max_width: int = Field(
        800, ge=1, le=4000, description="Comics wider than this many pixels are skipped"
    )
    max_height: int = Field(
        600, ge=1, le=4000, description="Comics taller than this many pixels are skipped"
    )
    tries: int = Field(
        10,
        ge=1,
        le=20,
        description="How many random comics to try before giving up, when they are too large "
        "or have no picture",
    )
    enlarge: bool = Field(
        False,
        description="Enlarge comics that are smaller than the space on the screen (else they "
        "keep their own size)",
    )


@dataclass(frozen=True)
class Comic:
    """What ``draw`` gets: one comic. ``image`` is the picture file's content, or a path."""

    number: int
    title: str
    alt: str
    image: bytes | Path


class NoComicFound(ValueError):
    pass


def fetch(context: Context):
    """The newest or a random comic, ready to draw. When the newest can't be shown, a
    random one is shown instead, for this update only. Raises :class:`NoComicFound` when
    xkcd.com sends no number for its newest comic, or when no random comic in ``tries``
    tries can be shown (too large, or no picture)."""
    settings = context.settings
    newest = _info(f"{SITE}/info.0.json")
    latest = _number(newest)
    if latest is None:
        raise NoComicFound("xkcd.com sent no number for its newest comic")
    if settings.comic == "newest":
        comic, why = _comic(latest, newest, settings)
        if comic:
            return ready(comic)
        log.info("can't show the newest xkcd comic (%d): %s; showing a random one", latest, why)
    numbers = [n for n in range(1, latest + 1) if n != MISSING]
    why = "none were tried"
    for _ in range(settings.tries):
        number = random.choice(numbers)
        comic, why = _comic(number, _info(f"{SITE}/{number}/info.0.json"), settings)
        if comic:
            return ready(comic)
        log.info("skipping xkcd comic %d: %s", number, why)
    raise NoComicFound(f"no suitable xkcd comic in {settings.tries} tries (the last one: {why})")


def _info(url: str) -> dict:
    data = webrequest.get(url).json()
    return data if isinstance(data, dict) else {}


def _number(info: dict) -> int | None:
    number = info.get("num")
    return number if isinstance(number, int) and number > 0 else None


def _comic(number: int, info: dict, settings: Settings) -> tuple[Comic | None, str]:
    """The comic described by ``info`` (xkcd's JSON file for it), with its picture, or
    ``None`` and the reason it can't be shown. Network errors are raised: trying another
    comic would not help."""
    url = info.get("img")
    if not picture_address(url):
        return None, "it has no picture"  # e.g. an interactive comic
    body = webrequest.get(url).body
    try:
        with Image.open(io.BytesIO(body), formats=FORMATS) as picture:  # reads only the size
            width, height = picture.size
            if width > settings.max_width or height > settings.max_height:
                return None, f"it is {width}x{height} pixels, larger than the settings allow"
            picture.load()  # decodes it all, so a damaged file is found here, not in draw
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return None, "its picture is not a PNG, JPEG or GIF file, or is damaged"
    title = info.get("safe_title") or info.get("title") or ""
    alt = info.get("alt") or ""
    return Comic(number, str(title), str(alt), body), ""


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
    if not settings.enlarge:
        prepared = layout.prepare(context.width, context.height, context.mode)
        picture = keep_size(picture, *prepared.content_size("comic"))
    title = f"{comic.number}: {comic.title}" if comic.title else str(comic.number)
    values = {"comic": picture, "title": title, "alt": comic.alt}
    return {name: value for name, value in values.items() if name in layout.blocks}


PLUGIN = Plugin(
    type="xkcd_comic",
    description="A random comic from xkcd.com, with its title and hover text.",
    settings=Settings,
    layouts=LAYOUTS,
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
