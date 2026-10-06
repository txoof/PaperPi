"""The moon_phase plugin: reading met.no's answer, the saved answer, the phase, drawing."""

import json
from datetime import date, datetime

import pytest
from epdlib import ScreenMode
from PIL import ImageChops, ImageStat

import paperpi.plugins.moon_phase as moon_phase
from paperpi import webrequest
from paperpi.plugin import Context
from paperpi.plugins.moon_phase import (
    PLUGIN,
    SAMPLE,
    Moon,
    MoonError,
    draw,
    fetch,
    load,
    moon_photo,
    parse,
    phase_name,
    photo_file,
    save,
)

BERLIN = {"lat": 52.52, "lon": 13.40, "email": "me@example.com"}
PLACE = "52.5200,13.4000"


def answer(phase=301.33, rise="2026-10-06T01:38+02:00", set_="2026-10-06T17:04+02:00"):
    """A met.no moon answer, shortened to what the plugin reads."""
    properties = {"body": "Moon", "moonphase": phase}
    if rise is not ...:
        properties["moonrise"] = {"time": rise, "azimuth": 60.09}
    if set_ is not ...:
        properties["moonset"] = {"time": set_, "azimuth": 293.7}
    return {"type": "Feature", "properties": properties}


# --- Reading met.no's answer -----------------------------------------------------------------


def test_parse():
    moon = parse(answer(), date(2026, 10, 6), PLACE)
    assert moon == Moon(
        "2026-10-06",
        PLACE,
        301.33,
        datetime.fromisoformat("2026-10-06T01:38+02:00"),
        datetime.fromisoformat("2026-10-06T17:04+02:00"),
    )


@pytest.mark.parametrize("missing", [None, ...])  # no time, or no moonrise at all
def test_a_day_without_moonrise(missing):
    moon = parse(answer(rise=missing), date(2026, 10, 6), PLACE)
    assert moon.rise is None
    assert moon.set is not None


@pytest.mark.parametrize(
    "broken",
    [{}, {"properties": None}, answer(phase=None), answer(phase="x"), answer(phase=361),
     answer(phase=-1), answer(rise="not a time")],
)  # fmt: skip
def test_broken_answers(broken):
    with pytest.raises(MoonError):
        parse(broken, date(2026, 10, 6), PLACE)


def test_save_and_load(tmp_path):
    path = tmp_path / "moon.json"
    moon = parse(answer(set_=None), date(2026, 10, 6), PLACE)
    path.write_bytes(save(moon))
    assert load(path) == moon


@pytest.mark.parametrize("content", [None, b"", b"{", b"[]", b'{"day": "x"}'])
def test_load_broken_or_missing(tmp_path, content):
    path = tmp_path / "moon.json"
    if content is not None:
        path.write_bytes(content)
    assert load(path) is None


# --- Fetching --------------------------------------------------------------------------------


class FakeMetNo:
    """Stands in for webrequest.get and records the addresses asked for."""

    def __init__(self, monkeypatch, result=None):
        self.urls = []
        self.result = result
        monkeypatch.setattr(moon_phase.webrequest, "get", self)

    def __call__(self, url, **options):
        self.urls.append(url)
        self.options = options
        if isinstance(self.result, Exception):
            raise self.result
        return webrequest.Answer(200, json.dumps(answer()).encode(), {}, url)


def context(tmp_path, layout="moon_data", **settings):
    return Context(PLUGIN.settings(**settings), 1200, 825, ScreenMode.gray(16), tmp_path, layout)


def today() -> str:
    return datetime.now().astimezone().date().isoformat()


def test_fetch_downloads_and_saves(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    fetched = fetch(context(tmp_path, lat=52.523456, lon=13.4, email="me@example.com"))
    assert fetched.data.phase == 301.33
    assert fetched.data.day == today()
    (url,) = metno.urls
    assert url.startswith(f"{moon_phase.URL}?lat=52.5235&lon=13.4000&date={today()}&offset=")
    assert metno.options == {"contact": "me@example.com"}
    assert load(tmp_path / "moon.json") == fetched.data
    assert (tmp_path / "moon.json").stat().st_mode & 0o077 == 0  # only PaperPi can read it


def test_fetch_asks_once_a_day(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    for _ in range(3):
        fetch(context(tmp_path, **BERLIN))
    assert len(metno.urls) == 1


@pytest.mark.parametrize(
    ("day", "place"), [("2000-01-01", PLACE), (None, "-22.9068,-43.1729")]
)  # saved on another day, or for another place (Rio)
def test_old_or_other_saved_answer_is_downloaded_again(tmp_path, monkeypatch, day, place):
    metno = FakeMetNo(monkeypatch)
    saved = Moon(day or today(), place, 10.0, None, None)
    (tmp_path / "moon.json").write_bytes(save(saved))
    fetched = fetch(context(tmp_path, **BERLIN))
    assert len(metno.urls) == 1
    assert fetched.data.phase == 301.33


def test_unreachable_fails_and_saves_nothing(tmp_path, monkeypatch):
    FakeMetNo(monkeypatch, webrequest.WebError("api.met.no can't be reached"))
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path, **BERLIN))
    assert not (tmp_path / "moon.json").exists()


@pytest.mark.parametrize("missing", ["lat", "lon", "email"])
def test_settings_are_required(tmp_path, monkeypatch, missing):
    FakeMetNo(monkeypatch)
    settings = {k: v for k, v in BERLIN.items() if k != missing}
    with pytest.raises(moon_phase.SettingsMissing):
        fetch(context(tmp_path, **settings))


# --- Phase and picture -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phase", "name"),
    [(0, "New Moon"), (6, "New Moon"), (7, "Waxing Crescent"), (89, "First Quarter"),
     (120, "Waxing Gibbous"), (180, "Full Moon"), (200, "Waning Gibbous"),
     (270, "Last Quarter"), (301.33, "Waning Crescent"), (355, "New Moon"), (360, "New Moon")],
)  # fmt: skip
def test_phase_name(phase, name):
    assert phase_name(phase) == name


def test_a_photo_every_1_8_degrees():
    angles = sorted(float(path.stem) for path in moon_phase.PHOTOS.glob("*.jpeg"))
    assert angles == [round(i * 1.8, 1) for i in range(201)]  # 0.0 to 360.0


@pytest.mark.parametrize(
    ("phase", "photo"),
    [(0, "0.0"), (0.8, "0.0"), (1.0, "1.8"), (301.33, "300.6"), (359.5, "360.0")],
)
def test_the_nearest_photo(phase, photo):
    assert photo_file(phase).stem == photo


def brightness(image, box):
    return ImageStat.Stat(image.convert("L").crop(box)).sum[0]


@pytest.mark.parametrize(
    ("lat", "lit_on_the_right"), [(52.52, True), (None, True), (-22.91, False)]
)
def test_south_of_the_equator_the_photo_is_upside_down(lat, lit_on_the_right):
    """At first quarter the moon is lit on the right in the north, on the left in the south
    (Rio)."""
    photo = moon_photo(90, lat)
    width, height = photo.size
    left = brightness(photo, (0, 0, width // 2, height))
    right = brightness(photo, (width // 2, 0, width, height))
    assert (right > left) is lit_on_the_right


def test_southern_photo_is_the_northern_one_turned():
    north, south = moon_photo(301.33, 52.52), moon_photo(301.33, -22.91)
    assert ImageChops.difference(south, north.rotate(180)).getbbox() is None


# --- Drawing ---------------------------------------------------------------------------------


def test_draw_the_sample(tmp_path):
    values = draw(SAMPLE, context(tmp_path))
    assert values["moonrise"] == "Moonrise: 01:38"
    assert values["moonset"] == "Moonset: 17:04"
    assert values["phase"] == "Waning Crescent"
    assert values["credit"] == "Data: MET Norway · Image: NASA SVS"
    assert values["moon"].size == (1080, 1080)


def test_draw_a_day_without_moonset(tmp_path):
    moon = Moon("2026-10-06", PLACE, 301.33, SAMPLE.rise, None, "Europe/Berlin")
    assert draw(moon, context(tmp_path))["moonset"] == "Moonset: none"


def test_moon_only_gets_only_the_moon(tmp_path):
    assert set(draw(SAMPLE, context(tmp_path, layout="moon_only"))) == {"moon"}
