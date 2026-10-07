"""The newyorker plugin: the feed, captions, saving cartoons, falling back, drawing. No network."""

import io
import json

import pytest
from epdlib import ScreenMode
from PIL import Image

import paperpi.plugins.newyorker as newyorker
from paperpi import fonts, webrequest
from paperpi.plugin import Context, State
from paperpi.plugins.newyorker import (
    FEED,
    PLUGIN,
    Cartoon,
    FeedError,
    Settings,
    Texts,
    allowed,
    day,
    fetch,
    parse_feed,
    read_caption,
)

NAMESPACES = (
    'xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/"'
)
SITE = "https://www.newyorker.com/cartoons/daily-cartoon"


def url(n) -> str:
    return f"https://media.newyorker.com/cartoons/{n}.jpg"


def link(n) -> str:
    return f"{SITE}/cartoon-{n}"


def item(n, picture=None, page=None, guid=True, date="Mon, 05 Oct 2026 15:11:07 +0000") -> str:
    picture = url(n) if picture is None else picture
    page = link(n) if page is None else page
    thumbnail = f'<media:thumbnail url="{picture}" width="1500" height="1500"/>' if picture else ""
    return (
        f"<item><title>Daily Cartoon: Monday, October {n}th</title><link>{page}</link>"
        + (f'<guid isPermaLink="false">id{n}</guid>' if guid else "")
        + f"<pubDate>{date}</pubDate><dc:creator>Artist {n}</dc:creator>"
        f"<description>A drawing that riffs on the latest news.</description>{thumbnail}</item>"
    )


def feed(*items: str) -> bytes:
    rss = f'<?xml version="1.0"?><rss {NAMESPACES}><channel>{"".join(items)}</channel></rss>'
    return rss.encode()


def page(caption="“A made-up caption.”", credit="Cartoon by Page Artist") -> bytes:
    """A cartoon page, shaped like newyorker.com's: one wrapper each for caption and credit."""
    wrap = (
        '<div class="CaptionWrapper" data-testid="caption-wrapper"><span class="x">{}</span></div>'
    )
    parts = [wrap.format(text) for text in (caption, credit) if text is not None]
    return f"<html><body><img src='a.jpg'><br>{''.join(parts)}<p>More</p></body></html>".encode()


def jpeg(width=30, height=20) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height), 0).save(buffer, "JPEG")
    return buffer.getvalue()


class FakeSite:
    """Stands in for webrequest.get: ``pages`` maps an address to its content. Other
    addresses answer 404. ``moved`` maps an address to where it is redirected."""

    def __init__(self, monkeypatch, pages, moved=None):
        self.pages = pages
        self.moved = moved or {}
        self.urls = []
        monkeypatch.setattr(newyorker.webrequest, "get", self)

    def __call__(self, address, **options):
        self.urls.append(address)
        if address in self.pages:
            return webrequest.Answer(200, self.pages[address], {}, self.moved.get(address, address))
        raise webrequest.WebError("www.newyorker.com answered 404 Not Found")


def site(monkeypatch, *numbers, **pages):
    """The feed with cartoons ``numbers``, each with its picture and page."""
    content = {FEED: feed(*(item(n) for n in numbers))}
    for n in numbers:
        content |= {url(n): jpeg(), link(n): page()}
    return FakeSite(monkeypatch, content | pages)


def context(tmp_path, layout="comic_caption_date", low_disk=False, **settings):
    mode = ScreenMode.gray(16)
    return Context(Settings(**settings), 400, 300, mode, tmp_path, layout, low_disk=low_disk)


@pytest.fixture
def pick(monkeypatch):
    """Records the cartoons offered to random.choice, and picks the first one."""
    seen = []
    monkeypatch.setattr(
        newyorker.random, "choice", lambda entries: seen.append(entries) or entries[0]
    )
    return seen


# --- The feed and the page -------------------------------------------------------------------


def test_parse_feed_reads_the_cartoons_newest_first():
    first, second = parse_feed(feed(item(1), item(2)))
    assert (first.id, first.title, first.creator) == (
        "id1",
        "Daily Cartoon: Monday, October 1th",
        "Artist 1",
    )
    assert (first.date, first.url, first.link) == ("Monday, October 5", url(1), link(1))
    assert second.id == "id2"


def test_only_newyorker_com_over_https():
    assert allowed("https://media.newyorker.com/a.jpg") and allowed("https://newyorker.com/x")
    for address in [
        "http://media.newyorker.com/a.jpg",
        "https://newyorker.com.evil/a.jpg",
        "https://evilnewyorker.com/a",
        "",
        "https:///a.jpg",
    ]:
        assert not allowed(address)


def test_parse_feed_skips_pictures_elsewhere_and_drops_links_elsewhere():
    body = feed(
        item(1, picture=""),
        item(2, picture="https://example.com/2.jpg"),
        item(3, page="https://example.com/3"),
    )
    (entry,) = parse_feed(body)
    assert (entry.id, entry.link) == ("id3", "")


def test_parse_feed_without_a_guid_uses_the_picture_address():
    assert parse_feed(feed(item(1, guid=False)))[0].id == url(1)


@pytest.mark.parametrize(
    ("published", "shown"),
    [
        ("Wed, 07 Oct 2026 14:09:24 +0000", "Wednesday, October 7"),
        ("Thu, 01 Oct 2026 23:30:00 -0400", "Thursday, October 1"),
        ("", ""),
        ("someday", ""),
        (None, ""),
    ],
)
def test_day(published, shown):
    assert day(published) == shown


@pytest.mark.parametrize("body", [b"", b"<html>not a feed", b"<rss><channel><item></rss>"])
def test_broken_feed_raises(body):
    with pytest.raises(FeedError, match="can't be read"):
        parse_feed(body)


def test_read_caption_finds_caption_and_credit():
    assert read_caption(page().decode()) == ("“A made-up caption.”", "Cartoon by Page Artist")


def test_read_caption_without_one():
    assert read_caption(page(caption=None).decode()) == ("", "Cartoon by Page Artist")
    assert read_caption("<html><p>changed page</p>") == ("", "")
    assert read_caption(page(caption="word " * 100).decode())[0] == ""  # too long: not a caption


def test_read_caption_nested_tags_and_entities():
    html = '<div data-testid="caption-wrapper"><p>“Fish &amp; <em>chips</em>,\n please.”</p></div>'
    assert read_caption(html) == ("“Fish & chips, please.”", "")


# --- Fetching --------------------------------------------------------------------------------


def test_fetch_gets_a_cartoon_with_its_caption(tmp_path, monkeypatch, pick):
    fake = site(monkeypatch, 1)
    fetched = fetch(context(tmp_path))
    assert fetched.state is State.READY
    assert fetched.data == Cartoon(
        Texts("“A made-up caption.”", "Cartoon by Page Artist", "Monday, October 5"), jpeg()
    )
    assert fake.urls == [FEED, url(1), link(1)]
    assert len(list(tmp_path.glob("*.picture"))) == len(list(tmp_path.glob("*.json"))) == 1


def test_saved_cartoon_is_used_again(tmp_path, monkeypatch, pick):
    fake = site(monkeypatch, 1)
    first = fetch(context(tmp_path)).data
    again = fetch(context(tmp_path)).data
    assert fake.urls == [FEED, url(1), link(1), FEED]
    assert again.texts == first.texts and again.image.suffix == ".picture"


def test_cartoon_without_a_caption_shows_only_the_credit(tmp_path, monkeypatch, pick):
    # Words inside the picture: the page has only "Cartoon by ...".
    site(monkeypatch, 1, **{link(1): page(caption=None)})
    texts = fetch(context(tmp_path)).data.texts
    assert texts == Texts("", "Cartoon by Page Artist", "Monday, October 5")
    assert list(tmp_path.glob("*.json"))  # saved: the page is not asked again


def test_changed_page_shows_title_and_cartoonist(tmp_path, monkeypatch, pick):
    site(monkeypatch, 1, **{link(1): b"<html><p>a new page design</p></html>"})
    texts = fetch(context(tmp_path)).data.texts
    assert texts == Texts("Monday, October 1th · Artist 1", "", "Monday, October 5")
    assert list(tmp_path.glob("*.json"))


def test_page_that_cant_be_downloaded_is_tried_again(tmp_path, monkeypatch, pick):
    fake = site(monkeypatch, 1)
    del fake.pages[link(1)]
    assert fetch(context(tmp_path)).data.texts.caption == "Monday, October 1th · Artist 1"
    assert not list(tmp_path.glob("*.json"))
    fake.pages[link(1)] = page()
    assert fetch(context(tmp_path)).data.texts.caption == "“A made-up caption.”"
    assert fake.urls[-2:] == [FEED, link(1)]  # the picture was saved


def test_credit_from_the_feed_when_the_page_has_none(tmp_path, monkeypatch, pick):
    site(monkeypatch, 1, **{link(1): page(credit=None)})
    assert fetch(context(tmp_path)).data.texts.credit == "Cartoon by Artist 1"


def test_redirect_away_from_newyorker_com_is_refused(tmp_path, monkeypatch, pick):
    fake = site(monkeypatch, 1)
    fake.moved = {link(1): "https://example.com/elsewhere"}
    assert fetch(context(tmp_path)).data.texts.caption == "Monday, October 1th · Artist 1"
    fake.moved = {url(1): "https://example.com/1.jpg"}
    for path in tmp_path.iterdir():
        path.unlink()
    with pytest.raises(FeedError, match="another server"):
        fetch(context(tmp_path))


def test_damaged_saved_picture_is_downloaded_again(tmp_path, monkeypatch, pick):
    fake = site(monkeypatch, 1)
    fetch(context(tmp_path))
    next(tmp_path.glob("*.picture")).write_bytes(b"half a picture")
    assert fetch(context(tmp_path)).data.image == jpeg()
    assert fake.urls[-2:] == [FEED, url(1)]


def test_picks_from_the_newest_day_range_cartoons(tmp_path, monkeypatch, pick):
    site(monkeypatch, *range(1, 8))
    fetch(context(tmp_path, day_range=3))
    assert [entry.id for entry in pick[0]] == ["id1", "id2", "id3"]


def test_old_cartoons_are_removed(tmp_path, monkeypatch, pick):
    fake = site(monkeypatch, 1, 2, 3)
    pick_order = iter([2, 1, 0])
    monkeypatch.setattr(newyorker.random, "choice", lambda entries: entries[next(pick_order)])
    for _ in range(3):
        fetch(context(tmp_path))  # saves cartoons 3, 2 and 1
    other = tmp_path / "notes.txt"  # not the plugin's file: left alone
    other.write_text("hello")
    fake.pages[FEED] = feed(item(1), item(2), item(3))
    monkeypatch.setattr(newyorker.random, "choice", lambda entries: entries[0])
    fetch(context(tmp_path, day_range=2))
    assert len(list(tmp_path.glob("*.picture"))) == len(list(tmp_path.glob("*.json"))) == 2
    assert other.exists()


def test_low_disk_shows_without_saving(tmp_path, monkeypatch, pick):
    site(monkeypatch, 1)
    assert fetch(context(tmp_path, low_disk=True)).data.image == jpeg()
    assert not list(tmp_path.iterdir())


def test_cartoon_that_cant_be_saved_is_shown(tmp_path, monkeypatch, pick, caplog):
    site(monkeypatch, 1)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(newyorker, "write_atomic", fail)
    assert fetch(context(tmp_path)).data.image == jpeg()
    assert "can't save the cartoon" in caplog.text


@pytest.mark.parametrize("picture", [b"<html>not a picture</html>", jpeg()[:100]])
def test_unusable_picture_raises(tmp_path, monkeypatch, pick, picture):
    site(monkeypatch, 1, **{url(1): picture})
    with pytest.raises(FeedError, match="not a JPEG or PNG"):
        fetch(context(tmp_path))
    assert not list(tmp_path.iterdir())


def test_feed_without_cartoons_raises(tmp_path, monkeypatch):
    FakeSite(monkeypatch, {FEED: feed(item(1, picture=""))})
    with pytest.raises(FeedError, match="no cartoons"):
        fetch(context(tmp_path))


def test_network_errors_are_raised(tmp_path, monkeypatch, pick):
    FakeSite(monkeypatch, {FEED: feed(item(1))})  # the picture answers 404
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path))


@pytest.mark.parametrize("broken", ["feed", "picture"])
def test_saved_cartoon_is_shown_when_downloads_fail(tmp_path, monkeypatch, pick, caplog, broken):
    fake = site(monkeypatch, 1)
    first = fetch(context(tmp_path)).data
    if broken == "feed":
        del fake.pages[FEED]
    else:
        fake.pages[FEED] = feed(item(2))  # a new cartoon whose picture answers 404
    shown = fetch(context(tmp_path)).data
    assert shown.texts == first.texts and shown.image.suffix == ".picture"
    assert "showing a saved one" in caplog.text
    assert len(list(tmp_path.glob("*.picture"))) == 1  # nothing removed


def test_broken_saved_files_are_not_shown(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text(json.dumps({"caption": "x", "credit": "", "date": ""}))
    (tmp_path / "a.picture").write_bytes(b"broken")
    (tmp_path / "b.json").write_text("not json")
    FakeSite(monkeypatch, {})
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path))


# --- Drawing ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("layout", "blocks"),
    [
        ("comic_caption_date", {"comic", "caption", "credit", "date"}),
        ("comic_caption", {"comic", "caption", "credit"}),
        ("comic_only", {"comic"}),
    ],
)
def test_draw_gives_only_the_layouts_blocks(tmp_path, layout, blocks):
    values = newyorker.draw(PLUGIN.sample, context(tmp_path, layout))
    assert set(values) == blocks
    assert values["comic"].size == (800, 800)
    assert values.get("date", "Monday, October 5") == "Monday, October 5"


def test_draw_takes_downloaded_bytes(tmp_path):
    cartoon = Cartoon(PLUGIN.sample.texts, jpeg(30, 20))
    assert newyorker.draw(cartoon, context(tmp_path))["comic"].size == (30, 20)


def test_layout_fonts():
    layout = PLUGIN.layout("comic_caption_date", Settings())
    assert layout.blocks["caption"].options["font"] == fonts.LIBRE_CASLON_TEXT
    assert layout.blocks["credit"].options["font"] == fonts.LATO_ITALIC
    assert layout.blocks["date"].options["font"] == fonts.ANTON
