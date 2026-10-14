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
from paperpi.plugins.xkcd_comic import (
    PLUGIN,
    Comic,
    NoComicFound,
    Settings,
    fetch,
    fit,
    keep_size,
)


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


def test_newest_comic_too_large_shows_a_random_one(tmp_path, monkeypatch, pick, caplog):
    caplog.set_level("INFO")
    comics = {3: (info(3), png(900, 200)), 1: (info(1), png(10, 10))}
    NewestXkcd(monkeypatch, latest=3, comics=comics)
    pick.append(1)
    assert fetch(context(tmp_path, comic="newest")).data.number == 1
    assert "newest xkcd comic (3): it is 900x200 pixels" in caplog.text


def test_newest_and_random_comics_too_large_fails(tmp_path, monkeypatch, pick):
    NewestXkcd(monkeypatch, latest=3, comics={3: (info(3), png(900, 200))})
    pick.extend([3, 3])
    with pytest.raises(NoComicFound, match="in 2 tries"):
        fetch(context(tmp_path, comic="newest", tries=2))


def test_picks_from_all_comics_but_404(tmp_path, monkeypatch):
    FakeXkcd(monkeypatch, latest=405, comics={1: (info(1), png(10, 10))})
    seen = []
    monkeypatch.setattr(xkcd.random, "choice", lambda numbers: seen.append(numbers) or 1)
    fetch(context(tmp_path))
    assert seen[0] == [n for n in range(1, 406) if n != 404]


def picture(width, height, format) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height), 0).save(buffer, format)
    return buffer.getvalue()


def test_too_large_and_broken_comics_are_skipped(tmp_path, monkeypatch, pick, caplog):
    caplog.set_level("INFO")
    refused = [
        "",  # no picture
        "https://imgs.xkcd.com/comics/",  # interactive comics, e.g. 1608: only the folder
        "http://imgs.xkcd.com/comics/3.png",  # not https
        "https://example.com/comics/4.png",  # another server
    ]
    site = FakeXkcd(
        monkeypatch,
        comics={
            1: (info(1, img=refused[0]), b""),
            2: (info(2, img=refused[1]), b""),
            3: (info(3, img=refused[2]), png(10, 10)),
            4: (info(4, img=refused[3]), png(10, 10)),
            5: (info(5), png(801, 100)),  # wider than max_width
            6: (info(6), b"<html>not a picture</html>"),
            7: (info(7), picture(300, 200, "PNG")[:60]),  # cut off after the size
            8: (info(8), picture(30, 20, "BMP")),  # a format xkcd doesn't use
            9: (info(9), picture(800, 600, "GIF")),  # exactly the largest allowed
        },
        latest=9,
    )
    pick.extend(range(1, 10))
    assert fetch(context(tmp_path)).data.number == 9
    assert not set(refused) & set(site.urls)
    assert caplog.text.count("it has no picture") == 4
    assert "801x100 pixels" in caplog.text
    assert caplog.text.count("or is damaged") == 3


def test_picture_address():
    assert xkcd.picture_address("https://imgs.xkcd.com/comics/think_logically.png")
    for url in [None, 5, "", "https://imgs.xkcd.com/comics/", "https://imgs.xkcd.com.evil/a.png"]:
        assert not xkcd.picture_address(url)


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


def test_safe_title_is_used_not_title(tmp_path, monkeypatch, pick):
    # On xkcd.com, "title" can hold HTML for a few comics; "safe_title" is plain text.
    data = info(1, safe_title="Plain", title="<i>Plain</i>")
    FakeXkcd(monkeypatch, comics={1: (data, png(10, 10))})
    pick.append(1)
    assert fetch(context(tmp_path)).data.title == "Plain"


# --- The double-size picture -----------------------------------------------------------------

DOUBLE = "https://imgs.xkcd.com/comics/2_2x.png"


class DoubleXkcd(FakeXkcd):
    """Also has xkcd's double-size pictures: ``doubles`` maps an address to picture bytes."""

    def __init__(self, monkeypatch, doubles, **options):
        super().__init__(monkeypatch, **options)
        self.doubles = doubles

    def __call__(self, url, **options):
        if url in self.doubles:
            self.urls.append(url)
            return self.answer(url, self.doubles[url])
        return super().__call__(url, **options)


def big_screen(tmp_path, **settings):
    # The comic's space on a 1200x825 screen with the default layout is 1200x619.
    return context(tmp_path, size=(1200, 825), **settings)


def test_a_much_enlarged_comic_comes_from_the_double_picture(tmp_path, monkeypatch, pick):
    site = DoubleXkcd(monkeypatch, {DOUBLE: png(599, 401)}, comics={2: (info(2), png(300, 200))})
    pick.append(2)
    comic = fetch(big_screen(tmp_path)).data
    assert comic == Comic(2, "Comic 2", "Hover text 2", png(599, 401), double=True)
    assert site.urls[-1] == DOUBLE


def test_without_a_double_picture_the_normal_one_is_used(tmp_path, monkeypatch, pick):
    site = FakeXkcd(monkeypatch, comics={2: (info(2), png(300, 200))})  # the double: "404"
    pick.append(2)
    comic = fetch(big_screen(tmp_path)).data
    assert comic == Comic(2, "Comic 2", "Hover text 2", png(300, 200))
    assert site.urls[-1] == DOUBLE


@pytest.mark.parametrize("double", [png(500, 400), b"not a picture"])
def test_a_double_picture_of_the_wrong_size_or_damaged_is_not_used(
    tmp_path, monkeypatch, pick, double
):
    DoubleXkcd(monkeypatch, {DOUBLE: double}, comics={2: (info(2), png(300, 200))})
    pick.append(2)
    assert not fetch(big_screen(tmp_path)).data.double


@pytest.mark.parametrize(
    ("size", "settings"),
    [
        ((600, 420), {}),  # enlarged less than 1.5 times: the normal picture is good enough
        ((300, 200), {"enlarge": False}),
    ],
)
def test_no_double_picture_is_asked_for(tmp_path, monkeypatch, pick, size, settings):
    site = DoubleXkcd(monkeypatch, {DOUBLE: png(1, 1)}, comics={2: (info(2), png(*size))})
    pick.append(2)
    fetch(big_screen(tmp_path, **settings))
    assert DOUBLE not in site.urls


@pytest.mark.parametrize(("width", "used"), [(612, True), (613, False), (588, True), (587, False)])
def test_a_double_picture_may_be_two_percent_off(tmp_path, monkeypatch, pick, width, used):
    DoubleXkcd(monkeypatch, {DOUBLE: png(width, 400)}, comics={2: (info(2), png(300, 200))})
    pick.append(2)
    assert fetch(big_screen(tmp_path)).data.double is used


def test_the_double_picture_has_a_shorter_time_limit(tmp_path, monkeypatch, pick):
    site = DoubleXkcd(monkeypatch, {DOUBLE: png(600, 400)}, comics={2: (info(2), png(300, 200))})
    limits = []
    original = site.__call__
    monkeypatch.setattr(
        xkcd.webrequest, "get", lambda url, **options: limits.append(options) or original(url)
    )
    pick.append(2)
    fetch(big_screen(tmp_path))
    assert limits[-1] == {"total": xkcd.DOUBLE_TIME} and limits[:-1] == [{}, {}, {}]


def test_double_address():
    assert xkcd.double_address("https://imgs.xkcd.com/comics/a.b.png") == (
        "https://imgs.xkcd.com/comics/a.b_2x.png"
    )
    # Without a file extension, the address stays on the picture server.
    assert xkcd.double_address("https://imgs.xkcd.com/comics/name") == (
        "https://imgs.xkcd.com/comics/name_2x"
    )


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


def test_fit_enlarges_at_most_twice():
    page = fit(Image.new("L", (100, 50), 0), False, 1000, 300, 2)
    assert page.size == (1000, 300)
    assert Image.eval(page.convert("L"), lambda v: 255 - v).getbbox() == (400, 100, 600, 200)


def test_fit_fills_the_space_when_less_than_twice():
    page = fit(Image.new("L", (100, 50), 0), False, 150, 300, 2)
    assert Image.eval(page.convert("L"), lambda v: 255 - v).getbbox() == (0, 112, 150, 187)


def test_fit_counts_a_double_picture_at_half_its_size():
    page = fit(Image.new("L", (200, 100), 0), True, 1000, 300, 2)
    assert Image.eval(page.convert("L"), lambda v: 255 - v).getbbox() == (400, 100, 600, 200)
    page = fit(Image.new("L", (200, 100), 0), True, 1000, 300, 1)  # enlarge off: own size
    assert Image.eval(page.convert("L"), lambda v: 255 - v).getbbox() == (450, 125, 550, 175)


def test_fit_leaves_a_large_comic_to_the_layout():
    picture = Image.new("L", (400, 100))
    assert fit(picture, False, 300, 300, 2) is picture


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


@pytest.mark.parametrize(("enlarge", "width"), [(True, 200), (False, 100)])
def test_draw_counts_a_double_picture_at_half_its_size(tmp_path, enlarge, width):
    # Also when enlarge was switched off after the double picture was downloaded.
    comic = Comic(1, "Title", "Hover", png(200, 160), double=True)
    ctx = context(tmp_path, "comic_only", size=(800, 600), enlarge=enlarge)
    layout = PLUGIN.layout("comic_only", ctx.settings).prepare(800, 600, ctx.mode)
    assert comic_width(layout.render(xkcd.draw(comic, ctx))) == width


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
