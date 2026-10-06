"""The xkcd_comic plugin: picking a comic, skipping unsuitable ones, drawing. No network."""

import io
import json
from pathlib import Path

import pytest
from epdlib import ScreenMode
from PIL import Image

import paperpi.plugins.xkcd_comic as xkcd
from paperpi import fonts, webrequest
from paperpi.plugin import Context, State
from paperpi.plugins.xkcd_comic import PLUGIN, Comic, NoComicFound, Settings, fetch, keep_size


def png(width, height) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height), 0).save(buffer, "PNG")
    return buffer.getvalue()


class FakeXkcd:
    """Stands in for webrequest.get: ``comics`` maps a number to (info, picture bytes)."""

    def __init__(self, monkeypatch, latest=3, comics=None):
        self.latest = latest
        self.comics = comics or {}
        self.urls = []
        monkeypatch.setattr(xkcd.webrequest, "get", self)

    def __call__(self, url, **options):
        self.urls.append(url)
        if url == "https://xkcd.com/info.0.json":
            return self.answer(url, json.dumps({"num": self.latest}).encode())
        for number, (info, picture) in self.comics.items():
            if url == f"https://xkcd.com/{number}/info.0.json":
                return self.answer(url, json.dumps(info).encode())
            if url == info.get("img"):
                return self.answer(url, picture)
        raise webrequest.WebError("xkcd.com answered 404 Not Found")

    @staticmethod
    def answer(url, body):
        return webrequest.Answer(200, body, {}, url)


def info(number, **more):
    return {
        "num": number,
        "safe_title": f"Comic {number}",
        "alt": f"Hover text {number}",
        "img": f"https://imgs.xkcd.com/comics/{number}.png",
    } | more


def context(tmp_path, layout="comic_title_alttext", size=(400, 300), **settings):
    return Context(Settings(**settings), *size, ScreenMode.gray(16), tmp_path, layout)


@pytest.fixture
def pick(monkeypatch):
    """Makes the random choice repeatable: the numbers to pick, in order."""
    order = []
    monkeypatch.setattr(xkcd.random, "choice", lambda numbers: order.pop(0))
    return order


def test_fetch_gets_a_comic(tmp_path, monkeypatch, pick):
    site = FakeXkcd(monkeypatch, comics={2: (info(2), png(300, 200))})
    pick.append(2)
    fetched = fetch(context(tmp_path))
    assert fetched.state is State.READY
    assert fetched.data == Comic(2, "Comic 2", "Hover text 2", png(300, 200))
    assert site.urls == [
        "https://xkcd.com/info.0.json",
        "https://xkcd.com/2/info.0.json",
        "https://imgs.xkcd.com/comics/2.png",
    ]


class NewestXkcd(FakeXkcd):
    """The newest comic's details are in the main info.0.json, as on xkcd.com."""

    def __call__(self, url, **options):
        if url == "https://xkcd.com/info.0.json":
            self.urls.append(url)
            return self.answer(url, json.dumps(self.comics[self.latest][0]).encode())
        return super().__call__(url, **options)


def test_newest_comic(tmp_path, monkeypatch, pick):
    site = NewestXkcd(monkeypatch, latest=3, comics={3: (info(3), png(300, 200))})
    comic = fetch(context(tmp_path, comic="newest")).data
    assert (comic.number, comic.title) == (3, "Comic 3")
    assert site.urls == ["https://xkcd.com/info.0.json", "https://imgs.xkcd.com/comics/3.png"]


def test_newest_comic_too_large_fails(tmp_path, monkeypatch, pick):
    NewestXkcd(monkeypatch, latest=3, comics={3: (info(3), png(900, 200))})
    with pytest.raises(NoComicFound, match=r"newest xkcd comic \(3\).*900x200"):
        fetch(context(tmp_path, comic="newest"))


def test_picks_from_all_comics_but_404(tmp_path, monkeypatch):
    FakeXkcd(monkeypatch, latest=405, comics={1: (info(1), png(10, 10))})
    seen = []
    monkeypatch.setattr(xkcd.random, "choice", lambda numbers: seen.append(numbers) or 1)
    fetch(context(tmp_path))
    assert seen[0] == [n for n in range(1, 406) if n != 404]


def test_too_large_and_broken_comics_are_skipped(tmp_path, monkeypatch, pick, caplog):
    caplog.set_level("INFO")
    FakeXkcd(
        monkeypatch,
        comics={
            1: (info(1), png(801, 100)),  # wider than max_width
            2: (info(2, img="https://xkcd.com/2/"), b"<html>interactive</html>"),
            3: (info(3, img=""), b""),  # no picture
            4: (info(4), png(800, 600)),  # exactly the largest allowed
        },
        latest=4,
    )
    pick.extend([1, 2, 3, 4])
    assert fetch(context(tmp_path)).data.number == 4
    assert "801x100 pixels" in caplog.text


def test_gives_up_after_the_tries(tmp_path, monkeypatch, pick):
    FakeXkcd(monkeypatch, comics={1: (info(1), png(100, 700))})
    pick.extend([1, 1, 1])
    with pytest.raises(NoComicFound, match="in 3 tries.*100x700"):
        fetch(context(tmp_path, tries=3))


def test_settings_set_the_largest_size(tmp_path, monkeypatch, pick):
    FakeXkcd(monkeypatch, comics={1: (info(1), png(1000, 700))})
    pick.append(1)
    fetched = fetch(context(tmp_path, max_width=1000, max_height=700))
    assert fetched.data.number == 1


def test_network_errors_are_raised(tmp_path, monkeypatch, pick):
    site = FakeXkcd(monkeypatch)
    pick.append(2)  # not in the fake site: "404"
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path))
    assert len(site.urls) == 2  # no more tries: another comic would not help


@pytest.mark.parametrize("answer", [{}, {"num": "7"}, {"num": 0}, [1, 2]])
def test_latest_without_a_number(tmp_path, monkeypatch, answer):
    monkeypatch.setattr(
        xkcd.webrequest, "get", lambda url: FakeXkcd.answer(url, json.dumps(answer).encode())
    )
    with pytest.raises(NoComicFound, match="newest"):
        fetch(context(tmp_path))


def test_title_falls_back_and_texts_are_strings(tmp_path, monkeypatch, pick):
    data = info(1, safe_title="", title="Plain", alt=None)
    FakeXkcd(monkeypatch, comics={1: (data, png(10, 10))})
    pick.append(1)
    comic = fetch(context(tmp_path)).data
    assert (comic.title, comic.alt) == ("Plain", "")


# --- Drawing ---------------------------------------------------------------------------------


def test_keep_size_puts_a_small_comic_in_the_middle():
    page = keep_size(Image.new("L", (10, 6), 0), 30, 20).convert("L")
    assert page.size == (30, 20)
    assert Image.eval(page, lambda v: 255 - v).getbbox() == (10, 7, 20, 13)


def test_keep_size_leaves_a_large_comic():
    picture = Image.new("L", (40, 6))
    assert keep_size(picture, 30, 20) is picture


def test_keep_size_makes_transparent_parts_white():
    picture = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    assert keep_size(picture, 8, 8).getpixel((4, 4)) == (255, 255, 255)


def comic_width(image) -> int:
    left, _, right, _ = Image.eval(image.convert("L"), lambda v: 255 - v).getbbox()
    return right - left


@pytest.mark.parametrize(("enlarge", "wider"), [(False, False), (True, True)])
def test_small_comics_keep_their_size_unless_enlarged(tmp_path, enlarge, wider):
    comic = Comic(1, "Title", "Hover", png(100, 80))
    ctx = context(tmp_path, "comic_only", size=(800, 600), enlarge=enlarge)
    values = xkcd.draw(comic, ctx)
    layout = PLUGIN.layout("comic_only", ctx.settings).prepare(800, 600, ctx.mode)
    image = layout.render(values)
    assert (comic_width(image) > 100) is wider


@pytest.mark.parametrize(
    ("layout", "blocks"),
    [
        ("comic_title_alttext", {"comic", "title", "alt"}),
        ("comic_title", {"comic", "title"}),
        ("comic_only", {"comic"}),
    ],
)
def test_draw_gives_only_the_layouts_blocks(tmp_path, layout, blocks):
    values = xkcd.draw(PLUGIN.sample, context(tmp_path, layout))
    assert set(values) == blocks
    assert values.get("title", "1112: Think Logically") == "1112: Think Logically"


def test_title_without_a_name_is_the_number(tmp_path):
    comic = Comic(7, "", "", png(10, 10))
    assert xkcd.draw(comic, context(tmp_path, "comic_title"))["title"] == "7"


def test_layouts_use_lato():
    layout = PLUGIN.layout("comic_title_alttext", Settings())
    assert layout.blocks["title"].options["font"] == fonts.LATO_BOLD
    assert layout.blocks["alt"].options["font"] == fonts.LATO_ITALIC
    assert Path(fonts.LATO_BOLD).is_file() and Path(fonts.LATO_ITALIC).is_file()
