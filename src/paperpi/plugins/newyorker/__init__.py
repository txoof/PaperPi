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
from zoneinfo import ZoneInfo

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
#: Larger pictures are refused: a 4000x4000 picture needs about 50 MB of memory.
MAX_SIDE = 4000
#: Size limits for the downloads (the real page is about 800 kB, a picture about 400 kB),
#: and time limits, so feed + picture + page fit in the 60 s update with time to spare
#: for showing a saved cartoon.
PAGE_BYTES = PICTURE_BYTES = 2_000_000
FEED_SECONDS, PICTURE_SECONDS, PAGE_SECONDS = 20, 15, 10
NEW_YORK = "America/New_York"
SAMPLE = Path(__file__).parent / "sample" / "therapist.png"


class Settings(PluginSettings):
    day_range: int = Field(
        5,
        ge=1,
        le=20,
        description="Pick a random cartoon from this many of the newest ones, 1 to 20 (1: "
        "always the newest)",
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
    """What ``draw`` gets. ``image`` is the picture file's content (a path only for the
    sample: a saved file may be removed by the storage clean-up before ``draw``)."""

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
        entries = parse_feed(get(FEED, total=FEED_SECONDS).body)
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


def get(url: str, **options) -> webrequest.Answer:
    """``webrequest.get``, only from newyorker.com, also after redirects."""
    if not allowed(url):
        raise FeedError("refusing an address that is not on newyorker.com over https")
    answer = webrequest.get(url, **options)
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
    """ "Monday, October 5": the day in New York (as in the cartoon's title) at the feed's
    date, which is in UTC."""
    try:
        when = parsedate_to_datetime(published or "").astimezone(ZoneInfo(NEW_YORK))
    except (TypeError, ValueError):
        return ""
    return f"{when:%A, %B} {when.day}"


class _CaptionReader(HTMLParser):
    """Collects the text of every element with ``data-testid="caption-wrapper"``: on a
    cartoon's page, the caption (when it has one) and "Cartoon by ...". Keeps the open tags
    inside a wrapper, so a tag left open (``<p>`` without ``</p>``) is closed by its parent's
    end tag; void tags (``<br>``) have no end tag and count as a space."""

    VOID = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open: list[str] = []  # the wrapper's tag and the tags open inside it
        self.parts: list[str] = []
        self.texts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            self.handle_data(" ")
        elif self.open:
            self.open.append(tag)
        elif ("data-testid", "caption-wrapper") in attrs:
            self.open, self.parts = [tag], []

    def handle_endtag(self, tag):
        if tag in self.open:
            del self.open[len(self.open) - 1 - self.open[::-1].index(tag) :]
            if not self.open:
                self.texts.append(" ".join("".join(self.parts).split()))

    def handle_data(self, data):
        if self.open:
            self.parts.append(data)


def read_caption(page: str) -> tuple[str, str] | None:
    """The caption ("" when there is none) and the credit ("Cartoon by ...", or "") on a
    cartoon's page. ``None`` when the page has changed: neither is found, or the caption is
    longer than :data:`MAX_CAPTION`."""
    reader = _CaptionReader()
    reader.feed(page)
    reader.close()
    credits = [text for text in reader.texts if text.startswith("Cartoon by ")]
    captions = [text for text in reader.texts if text and text not in credits]
    caption, credit = captions[0] if captions else "", credits[0] if credits else ""
    if not (caption or credit) or len(caption) > MAX_CAPTION:
        return None
    return caption, credit


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
        answer = get(entry.link, max_bytes=PAGE_BYTES, total=PAGE_SECONDS)
        page = answer.body.decode("utf-8", "replace")
    except (webrequest.WebError, FeedError) as error:
        log.info("can't get the cartoon's caption, showing its title: %s", error)
        return fallback(entry), False
    found = read_caption(page)
    if found is None:
        return fallback(entry), True  # the page has changed
    caption, credit = found
    # A cartoon with its words in the picture has only a credit: the caption stays empty.
    if not credit and entry.creator:
        credit = f"Cartoon by {entry.creator}"
    return Texts(caption, credit, entry.date), True


def cartoon_for(entry: Entry, context: Context) -> Cartoon:
    """The cartoon, from storage or downloaded (and then saved, unless the disk is nearly
    full). Raises :class:`FeedError` when the picture is not usable."""
    stem = context.storage / _stem(entry)
    picture_path, texts_path = stem.with_suffix(PICTURE), stem.with_suffix(TEXTS)
    image = _read(picture_path)
    if not _usable(image):
        image = get(entry.url, max_bytes=PICTURE_BYTES, total=PICTURE_SECONDS).body
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


def _stem(entry: Entry) -> str:
    """The name of the cartoon's saved files, made from its id so the feed can't choose a
    path."""
    return hashlib.sha256(entry.id.encode()).hexdigest()[:24]


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _usable(image: bytes) -> bool:
    """True for a JPEG or PNG picture of at most MAX_SIDE x MAX_SIDE pixels that decodes."""
    try:
        with Image.open(io.BytesIO(image), formats=FORMATS) as picture:
            if max(picture.size) > MAX_SIDE:  # read from the header, before decoding
                return False
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
        image = _read(stem.with_suffix(PICTURE)) if texts else b""
        if texts and _usable(image):
            return Cartoon(texts, image)
    return None


def forget_old(storage: Path, keep: list[Entry]) -> None:
    """Removes the saved files of cartoons that are not in ``keep``."""
    wanted = {_stem(entry) for entry in keep}
    for path in [*storage.glob(f"*{PICTURE}"), *storage.glob(f"*{TEXTS}")]:
        if path.stem not in wanted:
            try:
                path.unlink()
            except OSError as error:
                log.warning("can't remove an old cartoon: %s", error)


# --- Drawing ---------------------------------------------------------------------------------


def draw(cartoon: Cartoon, context: Context) -> dict:
    """The values for the blocks of the chosen layout."""
    image = cartoon.image
    source = io.BytesIO(image) if isinstance(image, bytes) else image
    with Image.open(source, formats=FORMATS) as picture:
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
    # A made-up cartoon, caption and cartoonist, made for PaperPi: not a New Yorker cartoon.
    sample=Cartoon(
        Texts(
            "“You keep saying you want to be more spontaneous, but have you considered that "
            "spontaneity might be the problem?”",
            "Cartoon by Chatwell Gilbert Pennington Thurston (C.G.P.T.)",
            "Monday, October 5",
        ),
        SAMPLE,
    ),
    refresh=60 * 60,
)
