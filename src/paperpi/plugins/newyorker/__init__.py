"""newyorker: a random cartoon from The New Yorker's Daily Cartoon, with its caption."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import random
import re
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
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
#: The cartoonist's name: <dc:creator>.
DC = "{http://purl.org/dc/elements/1.1/}"
#: The feed's pictures are JPEG files; PNG is allowed too. Other formats are refused.
FORMATS = ("JPEG", "PNG")
#: Saved files end with these, so the plugin removes only its own files.
PICTURE, TEXTS = ".picture", ".json"
#: Longer "captions" are not a caption: the page has changed.
MAX_CAPTION = 400
SAMPLE = Path(__file__).parent / "sample" / "island.png"


class Settings(PluginSettings):
    day_range: int = Field(
        5,
        ge=1,
        le=20,
        description="Pick a random cartoon from this many of the newest ones (1: always the "
        "newest)",
    )


@dataclass(frozen=True)
class Entry:
    """One cartoon in the feed."""

    id: str
    title: str  # "Daily Cartoon: Monday, October 5th"
    creator: str  # the cartoonist, "Chris Gural"
    date: str  # "Monday, October 5", or "" when the feed has none
    url: str  # the picture
    link: str  # the cartoon's page, with its caption; "" when missing or not allowed


@dataclass(frozen=True)
class Texts:
    """The texts shown with a cartoon; saved next to its picture."""

    caption: str
    credit: str  # "Cartoon by Chris Gural"
    date: str


@dataclass(frozen=True)
class Cartoon:
    """What ``draw`` gets. ``image`` is the picture file's content, or a path to it."""

    texts: Texts
    image: bytes | Path


class FeedError(ValueError):
    """The feed or the cartoon's picture can't be read, or is not on newyorker.com."""


def fetch(context: Context):
    """A random cartoon from the newest ``day_range`` ones in the feed. Its picture and
    texts are saved in storage, so each cartoon is downloaded only once; those of cartoons
    no longer among the newest ``day_range`` are removed. When no new cartoon can be had,
    a saved one is shown; without one, the error is raised."""
    try:
        entries = parse_feed(get(FEED).body)
        if not entries:
            raise FeedError("The New Yorker's cartoon feed has no cartoons with a picture")
        newest = entries[: context.settings.day_range]
        cartoon = cartoon_for(random.choice(newest), context)
    except (webrequest.WebError, FeedError) as error:
        saved = saved_cartoon(context.storage)
        if saved is None:
            raise
        log.warning("can't get a new cartoon, showing a saved one: %s", error)
        return ready(saved)
    forget_old(context.storage, newest)
    return ready(cartoon)


def allowed(url: str) -> bool:
    """True for an address on newyorker.com (or one of its servers), over https."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and (host == "newyorker.com" or host.endswith(".newyorker.com"))


def get(url: str) -> webrequest.Answer:
    """``webrequest.get``, only from newyorker.com, also after redirects."""
    if not allowed(url):
        raise FeedError("refusing an address that is not on newyorker.com over https")
    answer = webrequest.get(url)
    if not allowed(answer.url):
        raise FeedError("newyorker.com sent the plugin to another server")
    return answer


def parse_feed(body: bytes) -> list[Entry]:
    """The cartoons in the feed (an RSS file), newest first. Cartoons without a picture
    on newyorker.com are left out."""
    import xml.etree.ElementTree as ElementTree  # only needed here: keeps imports quick

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as error:
        raise FeedError(f"The New Yorker's cartoon feed can't be read: {error}") from None
    entries = []
    for item in root.iter("item"):
        thumbnail = item.find(f"{MEDIA}thumbnail")
        url = (thumbnail.get("url") if thumbnail is not None else None) or ""
        if not allowed(url):
            continue
        link = (item.findtext("link") or "").strip()
        entries.append(
            Entry(
                id=(item.findtext("guid") or url).strip(),
                title=" ".join((item.findtext("title") or "").split()),
                creator=" ".join((item.findtext(f"{DC}creator") or "").split()),
                date=day(item.findtext("pubDate")),
                url=url,
                link=link if allowed(link) else "",
            )
        )
    return entries


def day(published: str | None) -> str:
    """ "Monday, October 5" from the feed's date, in its own time zone (New York's day)."""
    try:
        when = parsedate_to_datetime(published or "")
    except (TypeError, ValueError):
        return ""
    return f"{when:%A, %B} {when.day}"


class _CaptionReader(HTMLParser):
    """Collects the text of every element with ``data-testid="caption-wrapper"``: on a
    cartoon's page, the caption (when it has one) and "Cartoon by ..."."""

    VOID = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []
        self.texts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        if self.depth:
            self.depth += 1
        elif ("data-testid", "caption-wrapper") in attrs:
            self.depth, self.parts = 1, []

    def handle_endtag(self, tag):
        if self.depth and tag not in self.VOID:
            self.depth -= 1
            if not self.depth:
                self.texts.append(" ".join("".join(self.parts).split()))

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)


def read_caption(page: str) -> tuple[str, str]:
    """The caption and the credit ("Cartoon by ...") on a cartoon's page; "" for each
    that isn't found."""
    reader = _CaptionReader()
    reader.feed(page)
    reader.close()
    credits = [text for text in reader.texts if text.startswith("Cartoon by ")]
    captions = [text for text in reader.texts if text and text not in credits]
    caption = captions[0] if captions and len(captions[0]) <= MAX_CAPTION else ""
    return caption, credits[0] if credits else ""


def fallback(entry: Entry) -> Texts:
    """ "Monday, October 5th · Chris Gural", from the feed, when the page can't be read."""
    title = re.sub(r"^Daily Cartoon:\s*", "", entry.title)
    return Texts(" · ".join(filter(None, (title, entry.creator))), "", entry.date)


def texts_for(entry: Entry) -> tuple[Texts, bool]:
    """The cartoon's texts from its page, and whether they are final (worth saving): a
    page that can't be downloaded is tried again at the next update."""
    if not entry.link:
        return fallback(entry), True
    try:
        page = get(entry.link).body.decode("utf-8", "replace")
    except (webrequest.WebError, FeedError) as error:
        log.info("can't get the cartoon's caption, showing its title: %s", error)
        return fallback(entry), False
    caption, credit = read_caption(page)
    if not caption and not credit:
        return fallback(entry), True  # the page has changed
    # A cartoon with its words in the picture has only a credit: the caption stays empty.
    if not credit and entry.creator:
        credit = f"Cartoon by {entry.creator}"
    return Texts(caption, credit, entry.date), True


def cartoon_for(entry: Entry, context: Context) -> Cartoon:
    """The cartoon, from storage or downloaded (and then saved, unless the disk is nearly
    full). Raises :class:`FeedError` when the picture is not usable."""
    stem = context.storage / hashlib.sha256(entry.id.encode()).hexdigest()[:24]
    picture_path, texts_path = stem.with_suffix(PICTURE), stem.with_suffix(TEXTS)
    image: bytes | Path | None = picture_path if _usable(picture_path) else None
    if image is None:
        image = get(entry.url).body
        if not _usable(image):
            raise FeedError("the cartoon's picture is not a JPEG or PNG file, or is damaged")
        _save(picture_path, image, context)
    texts = _load_texts(texts_path)
    if texts is None:
        texts, final = texts_for(entry)
        if final:
            _save(texts_path, json.dumps(asdict(texts)).encode(), context)
    return Cartoon(texts, image)


def _save(path: Path, data: bytes, context: Context) -> None:
    if context.low_disk:
        return
    try:
        write_atomic(path, data, durable=False)
    except OSError as error:
        log.warning("can't save the cartoon, showing it anyway: %s", error)


def _usable(image: bytes | Path) -> bool:
    try:
        source = io.BytesIO(image) if isinstance(image, bytes) else image
        with Image.open(source, formats=FORMATS) as picture:
            picture.load()  # decodes it all, so a damaged file is found here, not in draw
        return True
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return False


def _load_texts(path: Path) -> Texts | None:
    try:
        data = json.loads(path.read_bytes())
        return Texts(str(data["caption"]), str(data["credit"]), str(data["date"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def saved_cartoon(storage: Path) -> Cartoon | None:
    """A random saved cartoon with its texts, or ``None`` when there is none."""
    stems = [path.with_suffix("") for path in storage.glob(f"*{TEXTS}")]
    random.shuffle(stems)
    for stem in stems:
        texts = _load_texts(stem.with_suffix(TEXTS))
        if texts and _usable(stem.with_suffix(PICTURE)):
            return Cartoon(texts, stem.with_suffix(PICTURE))
    return None


def forget_old(storage: Path, keep: list[Entry]) -> None:
    """Removes the saved files of cartoons that are not in ``keep``."""
    wanted = {hashlib.sha256(entry.id.encode()).hexdigest()[:24] for entry in keep}
    for path in [*storage.glob(f"*{PICTURE}"), *storage.glob(f"*{TEXTS}")]:
        if path.stem not in wanted:
            try:
                path.unlink()
            except OSError as error:
                log.warning("can't remove an old cartoon: %s", error)


# --- Drawing ---------------------------------------------------------------------------------


def draw(cartoon: Cartoon, context: Context) -> dict:
    image = cartoon.image
    with Image.open(io.BytesIO(image) if isinstance(image, bytes) else image) as picture:
        picture.load()
    texts = cartoon.texts
    values = {
        "comic": picture,
        "caption": texts.caption,
        "credit": texts.credit,
        "date": texts.date,
    }
    blocks = PLUGIN.layout(context.layout, context.settings).blocks
    return {name: value for name, value in values.items() if name in blocks}


PLUGIN = Plugin(
    type="newyorker",
    description="A random cartoon from The New Yorker's Daily Cartoon, with its caption.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    # A made-up cartoon, caption and cartoonist, drawn for PaperPi: not a New Yorker cartoon.
    sample=Cartoon(
        Texts(
            "“Finally, a place where the news arrives only once a week.”",
            "Cartoon by Rosa Paperwhite",
            "Monday, October 5",
        ),
        SAMPLE,
    ),
    refresh=60 * 60,
)
