"""The newyorker plugin: reading the feed, picking and saving cartoons, drawing. No network."""

import io

import pytest
from epdlib import ScreenMode
from PIL import Image

import paperpi.plugins.newyorker as newyorker
from paperpi import fonts, webrequest
from paperpi.plugin import Context, State
from paperpi.plugins.newyorker import (
    FEED,
    PLUGIN,
    Entry,
    FeedError,
    Settings,
    fetch,
    parse_feed,
    saved_name,
)

MEDIA = 'xmlns:media="http://search.yahoo.com/mrss/"'


def item(n, caption="Caption", url=None, guid=True) -> str:
    url = f"https://media.example.com/cartoons/{n}.jpg" if url is None else url
    thumbnail = f'<media:thumbnail url="{url}" width="1500" height="1500"/>' if url else ""
    guid = f'<guid isPermaLink="false">id{n}</guid>' if guid else ""
    return (
        f"<item><title>Daily Cartoon {n}</title>{guid}"
        f"<description>{caption}</description>{thumbnail}</item>"
    )


def feed(*items: str) -> bytes:
    return f'<?xml version="1.0"?><rss {MEDIA}><channel>{"".join(items)}</channel></rss>'.encode()


def jpeg(width=30, height=20) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height), 0).save(buffer, "JPEG")
    return buffer.getvalue()


class FakeSite:
    """Stands in for webrequest.get: the feed, and pictures by address."""

    def __init__(self, monkeypatch, body, pictures=None):
        self.body = body
        self.pictures = pictures or {}
        self.urls = []
        monkeypatch.setattr(newyorker.webrequest, "get", self)

    def __call__(self, url, **options):
        self.urls.append(url)
        if url == FEED:
            return webrequest.Answer(200, self.body, {}, url)
        if url in self.pictures:
            return webrequest.Answer(200, self.pictures[url], {}, url)
        raise webrequest.WebError("media.example.com answered 404 Not Found")


def url(n) -> str:
    return f"https://media.example.com/cartoons/{n}.jpg"


def context(tmp_path, low_disk=False, **settings):
    layout = "comic_caption_time"
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


# --- The feed --------------------------------------------------------------------------------


def test_parse_feed_reads_the_cartoons_newest_first():
    entries = parse_feed(feed(item(1, "First"), item(2, "Second")))
    assert entries == [Entry("id1", "First", url(1)), Entry("id2", "Second", url(2))]


def test_parse_feed_skips_cartoons_without_a_picture_on_https():
    body = feed(
        item(1, url=""),
        item(2, url="http://media.example.com/2.jpg"),
        item(3),
        item(4, url="https:///x.jpg"),
    )
    assert [entry.id for entry in parse_feed(body)] == ["id3"]


def test_parse_feed_without_a_guid_uses_the_picture_address():
    assert parse_feed(feed(item(1, guid=False)))[0].id == url(1)


def test_caption_is_plain_text():
    caption = "<![CDATA[<p>A <i>very</i>\n  good &amp; funny</p> drawing]]>"
    assert parse_feed(feed(item(1, caption)))[0].caption == "A very good & funny drawing"


@pytest.mark.parametrize("body", [b"", b"<html>not a feed", b"<rss><channel><item></rss>"])
def test_broken_feed_raises(body):
    with pytest.raises(FeedError, match="can't be read"):
        parse_feed(body)


def test_saved_name_is_made_from_the_id_only():
    name = saved_name(Entry("../../etc/passwd", "", url(1)))
    assert "/" not in name and name.endswith(".picture")
    assert name != saved_name(Entry("id1", "", url(1)))


# --- Fetching --------------------------------------------------------------------------------


def test_fetch_gets_a_cartoon_and_saves_its_picture(tmp_path, monkeypatch, pick):
    site = FakeSite(monkeypatch, feed(item(1, "First")), {url(1): jpeg()})
    fetched = fetch(context(tmp_path))
    assert fetched.state is State.READY
    assert (fetched.data.caption, fetched.data.image) == ("First", jpeg())
    assert site.urls == [FEED, url(1)]
    assert (tmp_path / saved_name(parse_feed(site.body)[0])).read_bytes() == jpeg()


def test_saved_picture_is_used_again(tmp_path, monkeypatch, pick):
    site = FakeSite(monkeypatch, feed(item(1)), {url(1): jpeg()})
    fetch(context(tmp_path))
    again = fetch(context(tmp_path))
    assert site.urls == [FEED, url(1), FEED]
    assert again.data.image == tmp_path / saved_name(Entry("id1", "", url(1)))


def test_damaged_saved_picture_is_downloaded_again(tmp_path, monkeypatch, pick):
    site = FakeSite(monkeypatch, feed(item(1)), {url(1): jpeg()})
    (tmp_path / saved_name(Entry("id1", "", url(1)))).write_bytes(b"half a picture")
    assert fetch(context(tmp_path)).data.image == jpeg()
    assert site.urls == [FEED, url(1)]


def test_picks_from_the_newest_day_range_cartoons(tmp_path, monkeypatch, pick):
    FakeSite(monkeypatch, feed(*(item(n) for n in range(1, 8))), {url(1): jpeg()})
    fetch(context(tmp_path, day_range=3))
    assert [entry.id for entry in pick[0]] == ["id1", "id2", "id3"]


def test_day_range_larger_than_the_feed_uses_all(tmp_path, monkeypatch, pick, caplog):
    caplog.set_level("INFO")
    FakeSite(monkeypatch, feed(item(1), item(2)), {url(1): jpeg()})
    fetch(context(tmp_path, day_range=10))
    assert len(pick[0]) == 2
    assert "only 2 cartoons" in caplog.text


def test_old_pictures_are_removed(tmp_path, monkeypatch, pick):
    FakeSite(monkeypatch, feed(item(1), item(2), item(3)), {url(1): jpeg()})
    kept, old = (tmp_path / saved_name(Entry(f"id{n}", "", "")) for n in (2, 3))
    for path in (kept, old):
        path.write_bytes(jpeg())
    other = tmp_path / "notes.txt"  # not the plugin's picture: left alone
    other.write_text("hello")
    fetch(context(tmp_path, day_range=2))
    assert kept.exists() and other.exists() and not old.exists()
    assert len(list(tmp_path.glob("*.picture"))) == 2


def test_low_disk_shows_without_saving(tmp_path, monkeypatch, pick):
    FakeSite(monkeypatch, feed(item(1)), {url(1): jpeg()})
    assert fetch(context(tmp_path, low_disk=True)).data.image == jpeg()
    assert not list(tmp_path.glob("*.picture"))


def test_picture_that_cant_be_saved_is_shown(tmp_path, monkeypatch, pick, caplog):
    FakeSite(monkeypatch, feed(item(1)), {url(1): jpeg()})

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(newyorker, "write_atomic", fail)
    assert fetch(context(tmp_path)).data.image == jpeg()
    assert "can't save the cartoon's picture" in caplog.text


@pytest.mark.parametrize("picture", [b"<html>not a picture</html>", jpeg()[:100]])
def test_unusable_picture_raises(tmp_path, monkeypatch, pick, picture):
    FakeSite(monkeypatch, feed(item(1)), {url(1): picture})
    with pytest.raises(FeedError, match="not a JPEG or PNG"):
        fetch(context(tmp_path))
    assert not list(tmp_path.iterdir())


def test_feed_without_cartoons_raises(tmp_path, monkeypatch):
    FakeSite(monkeypatch, feed(item(1, url="")))
    with pytest.raises(FeedError, match="no cartoons"):
        fetch(context(tmp_path))


def test_network_errors_are_raised(tmp_path, monkeypatch, pick):
    FakeSite(monkeypatch, feed(item(1)))  # the picture answers 404
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path))


# --- Drawing ---------------------------------------------------------------------------------


def test_draw_gives_the_picture_caption_and_time(tmp_path):
    values = newyorker.draw(PLUGIN.sample, context(tmp_path))
    assert set(values) == {"comic", "caption", "time"}
    assert values["time"] == "10:42"
    assert values["caption"] == PLUGIN.sample.caption
    assert values["comic"].size == (800, 800)


def test_draw_takes_downloaded_bytes(tmp_path):
    cartoon = newyorker.Cartoon("Caption", jpeg(30, 20), PLUGIN.sample.time)
    assert newyorker.draw(cartoon, context(tmp_path))["comic"].size == (30, 20)


def test_layout_fonts():
    layout = PLUGIN.layout("comic_caption_time", Settings())
    assert layout.blocks["caption"].options["font"] == fonts.LATO_ITALIC
    assert layout.blocks["time"].options["font"] == fonts.ANTON
