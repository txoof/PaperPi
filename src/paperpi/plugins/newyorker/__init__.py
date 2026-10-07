"""newyorker: a random cartoon from The New Yorker's Daily Cartoon feed, with its caption."""

from __future__ import annotations

import hashlib
import html
import io
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError
from pydantic import Field

from ... import webrequest
from ...files import write_atomic
from ...plugin import Context, Plugin, PluginSettings, ready
from .layouts import LAYOUTS

log = logging.getLogger(__name__)

FEED = "https://www.newyorker.com/feed/cartoons/daily-cartoon"
#: The feed's pictures are in this XML namespace (Media RSS): <media:thumbnail url="...">.
MEDIA = "{http://search.yahoo.com/mrss/}"
#: The feed's pictures are JPEG files; PNG is allowed too. Other formats are refused.
FORMATS = ("JPEG", "PNG")
#: Saved pictures end with this, so the plugin removes only its own files.
SUFFIX = ".picture"
SAMPLE = Path(__file__).parent / "sample" / "island.png"


class Settings(PluginSettings):
    day_range: int = Field(
        5,
        ge=1,
        le=50,
        description="Pick a random cartoon from this many of the newest ones (1: always the "
        "newest)",
    )


@dataclass(frozen=True)
class Entry:
    """One cartoon in the feed: its id, caption and picture address."""

    id: str
    caption: str
    url: str


@dataclass(frozen=True)
class Cartoon:
    """What ``draw`` gets. ``image`` is the picture file's content, or a path to it;
    ``time`` is when it was fetched (shown in the corner, as in v1)."""

    caption: str
    image: bytes | Path
    time: datetime


class FeedError(ValueError):
    """The feed or the cartoon's picture can't be read."""


def fetch(context: Context):
    """A random cartoon from the newest ``day_range`` ones in the feed. Its picture is
    saved in storage, so it is downloaded only once; pictures of cartoons no longer among
    the newest ``day_range`` are removed."""
    day_range = context.settings.day_range
    entries = parse_feed(webrequest.get(FEED).body)
    if not entries:
        raise FeedError("The New Yorker's cartoon feed has no cartoons with a picture")
    if day_range > len(entries):
        log.info("the feed has only %d cartoons; picking from those", len(entries))
    newest = entries[:day_range]
    entry = random.choice(newest)
    image = picture(entry, context)
    forget_old(context.storage, newest)
    return ready(Cartoon(entry.caption, image, datetime.now()))


def parse_feed(body: bytes) -> list[Entry]:
    """The cartoons in the feed (an RSS file), newest first. Cartoons without a picture
    on https are left out."""
    import xml.etree.ElementTree as ElementTree  # only needed here: keeps imports quick

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as error:
        raise FeedError(f"The New Yorker's cartoon feed can't be read: {error}") from None
    entries = []
    for item in root.iter("item"):
        thumbnail = item.find(f"{MEDIA}thumbnail")
        url = thumbnail.get("url", "") if thumbnail is not None else ""
        if urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
            continue
        guid = item.findtext("guid") or url
        entries.append(Entry(guid.strip(), plain_text(item.findtext("description")), url))
    return entries


def plain_text(text: str | None) -> str:
    """The caption without HTML tags and entities (``&amp;``), on one line."""
    text = html.unescape(re.sub(r"<[^>]*>", " ", text or ""))
    return " ".join(text.split())


def saved_name(entry: Entry) -> str:
    """The file name for the cartoon's saved picture. Made from the id, so the feed can't
    choose a path."""
    return hashlib.sha256(entry.id.encode()).hexdigest()[:24] + SUFFIX


def picture(entry: Entry, context: Context) -> bytes | Path:
    """The saved picture, or a new download (saved for next time unless the disk is
    nearly full). Raises :class:`FeedError` when the download is not a usable picture."""
    path = context.storage / saved_name(entry)
    if path.is_file() and _usable(path.read_bytes()):
        return path
    body = webrequest.get(entry.url).body
    if not _usable(body):
        raise FeedError("the cartoon's picture is not a JPEG or PNG file, or is damaged")
    if not context.low_disk:
        try:
            write_atomic(path, body, durable=False)
        except OSError as error:
            log.warning("can't save the cartoon's picture, showing it anyway: %s", error)
    return body


def _usable(body: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(body), formats=FORMATS) as image:
            image.load()  # decodes it all, so a damaged file is found here, not in draw
        return True
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return False


def forget_old(storage: Path, keep: list[Entry]) -> None:
    """Removes saved pictures of cartoons that are not in ``keep``."""
    wanted = {saved_name(entry) for entry in keep}
    for path in storage.glob(f"*{SUFFIX}"):
        if path.name not in wanted:
            try:
                path.unlink()
            except OSError as error:
                log.warning("can't remove an old cartoon picture: %s", error)


# --- Drawing ---------------------------------------------------------------------------------


def draw(cartoon: Cartoon, context: Context) -> dict:
    image = cartoon.image
    with Image.open(io.BytesIO(image) if isinstance(image, bytes) else image) as picture:
        picture.load()
    return {"comic": picture, "caption": cartoon.caption, "time": f"{cartoon.time:%H:%M}"}


PLUGIN = Plugin(
    type="newyorker",
    description="A random cartoon from The New Yorker's Daily Cartoon, with its caption.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    # A made-up cartoon drawn for PaperPi (not a New Yorker cartoon), with the caption
    # text the feed currently gives every cartoon.
    sample=Cartoon(
        "A drawing that riffs on the latest news and happenings.",
        SAMPLE,
        datetime(2026, 10, 5, 10, 42),
    ),
    refresh=120,
)
