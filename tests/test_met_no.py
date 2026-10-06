"""The met_no weather plugin: trimming met.no's answer, the saved forecast, drawing."""

import json
import os
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest
from epdlib import Layout, ScreenMode

import paperpi.plugins.met_no as met_no
from paperpi import webrequest
from paperpi.plugin import Context
from paperpi.plugins.met_no import PLUGIN, Settings, Weather, barbs, draw, fetch, forecast
from paperpi.plugins.met_no.forecast import Forecast, ForecastError, Hour

BERLIN = {"lat": 52.52, "lon": 13.40, "email": "me@example.com", "place": "Berlin"}
START = datetime(2026, 10, 5, 7, tzinfo=UTC)


def step(hour, temperature=10.0, rain=0.0, symbol="cloudy", speed=3.0, wind_from=200.0):
    """One time step as met.no writes it."""
    return {
        "time": (START + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": {
            "instant": {
                "details": {
                    "air_temperature": temperature,
                    "wind_speed": speed,
                    "wind_from_direction": wind_from,
                    "relative_humidity": 70,
                }
            },
            "next_1_hours": {
                "summary": {"symbol_code": symbol},
                "details": {"precipitation_amount": rain},
            },
            "next_6_hours": {"summary": {"symbol_code": symbol}, "details": {}},
        },
    }


def answer(*steps):
    return {"type": "Feature", "properties": {"meta": {}, "timeseries": list(steps)}}


def hours(*rain, temperature=10.0):
    return tuple(
        Hour(START + timedelta(hours=i), temperature + i, r, "cloudy", 3.0, 200.0)
        for i, r in enumerate(rain)
    )


# --- Trimming met.no's answer ----------------------------------------------------------------


def test_trim_keeps_one_small_entry_per_hour():
    six_hourly = {
        "time": "2026-10-08T00:00:00Z",
        "data": {
            "instant": {
                "details": {"air_temperature": 5, "wind_speed": 1, "wind_from_direction": 0}
            }
        },
    }
    trimmed = forecast.trim(
        answer(step(0, 8.4, 0.0, "clearsky_day"), step(1, 9.6, 1.6, "rain"), six_hourly)
    )
    assert trimmed == (
        Hour(START, 8.4, 0.0, "clearsky_day", 3.0, 200.0),
        Hour(START + timedelta(hours=1), 9.6, 1.6, "rain", 3.0, 200.0),
    )


def test_trim_skips_steps_with_nan():
    nan = step(1)
    nan["data"]["instant"]["details"]["air_temperature"] = float("nan")
    assert len(forecast.trim(answer(step(0), nan))) == 1


def test_trim_skips_broken_steps():
    broken = step(1)
    del broken["data"]["instant"]["details"]["air_temperature"]
    assert len(forecast.trim(answer(step(0), broken, step(2)))) == 2


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"properties": {}},
        answer(),
        [],
        "text",
        {"properties": {"timeseries": 5}},
        {"properties": "x"},
        answer({"time": 1}, "step", {"data": []}),
    ],
)
def test_trim_without_hours(data):
    with pytest.raises(ForecastError):
        forecast.trim(data)


def test_window_starts_at_the_current_hour():
    f = Forecast(hours(*[0] * 20), START)
    shown = forecast.window(f, START + timedelta(hours=2, minutes=40))
    assert len(shown) == 12
    assert shown[0].time == START + timedelta(hours=2)


def test_summary_and_rain_spells():
    s = forecast.summarize(hours(0, 0.2, 1.6, 0.05, 0, 0.3))
    assert (s.high, s.low) == (15.0, 10.0)
    assert s.rain == pytest.approx(2.15)
    one = timedelta(hours=1)
    assert s.spells == ((START + one, START + 3 * one), (START + 5 * one, START + 6 * one))


def test_save_and_load(tmp_path):
    f = Forecast(
        hours(0, 1.5), START, START + timedelta(minutes=30), "Mon, 05 Oct 2026 07:00:00 GMT"
    )
    path = tmp_path / "forecast.json"
    path.write_bytes(forecast.save(f))
    assert forecast.load(path) == f


@pytest.mark.parametrize("content", [b"", b"{", b'{"hours": []}', b"[1, 2]"])
def test_load_broken_or_missing(tmp_path, content):
    assert forecast.load(tmp_path / "missing.json") is None
    (tmp_path / "f.json").write_bytes(content)
    assert forecast.load(tmp_path / "f.json") is None


# --- Fetching --------------------------------------------------------------------------------


class FakeMetNo:
    """Stands in for webrequest.get and records the calls."""

    def __init__(self, monkeypatch):
        self.calls = []
        self.result = None
        monkeypatch.setattr(met_no.webrequest, "get", self)

    def __call__(self, url, **options):
        self.calls.append((url, options))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def ok(*steps, last_modified="Mon, 05 Oct 2026 06:30:00 GMT", expires=None):
    headers = {"last-modified": last_modified}
    if expires:
        headers["expires"] = expires
    body = json.dumps(answer(*steps)).encode()
    return webrequest.Answer(200, body, headers, met_no.URL)


def context(tmp_path, layout="hours_12", **settings):
    return Context(Settings(**(BERLIN | settings)), 400, 300, ScreenMode.gray(16), tmp_path, layout)


def test_fetch_downloads_and_saves(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = ok(step(0), step(1))
    fetched = fetch(context(tmp_path, lat=52.520008, lon=13.404954))
    url, options = metno.calls[0]
    assert url == f"{met_no.URL}?lat=52.5200&lon=13.4050"  # met.no asks for 4 decimals
    assert options["contact"] == "me@example.com"
    assert options["if_modified_since"] is None
    assert len(fetched.data.forecast.hours) == 2
    assert (
        forecast.load(tmp_path / "forecast.json").last_modified == "Mon, 05 Oct 2026 06:30:00 GMT"
    )


def test_fetch_waits_until_the_forecast_expires(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    later = datetime.now(UTC) + timedelta(minutes=20)
    metno.result = ok(step(0), expires=format_datetime(later, usegmt=True))
    fetch(context(tmp_path))
    fetch(context(tmp_path))
    assert len(metno.calls) == 1


@pytest.mark.parametrize(
    ("age", "expires", "downloads"),
    [
        (10, None, True),  # no Expires: ask again
        (10, timedelta(minutes=-5), True),  # already passed
        (10, timedelta(minutes=20), False),
        (10, timedelta(days=3), False),  # far ahead, but the last download was 10 min ago
        (70, timedelta(days=3), True),  # far ahead (or a wrong clock): wait at most 1 hour
    ],
)
def test_expires(tmp_path, monkeypatch, age, expires, downloads):
    metno = FakeMetNo(monkeypatch)
    metno.result = webrequest.Answer(304, b"", {}, met_no.URL)
    when = None if expires is None else datetime.now(UTC) + expires
    saved(
        tmp_path,
        timedelta(minutes=age),
        expires=when,
        last_modified="Mon, 05 Oct 2026 06:30:00 GMT",
    )
    fetch(context(tmp_path))
    assert bool(metno.calls) == downloads


def test_a_changed_place_is_downloaded_again(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = ok(step(0), step(1), step(2))
    later = datetime.now(UTC) + timedelta(minutes=20)
    saved(
        tmp_path,
        timedelta(minutes=5),
        place="9.0300,38.7400",
        expires=later,
        last_modified="Mon, 05 Oct 2026 06:30:00 GMT",
    )
    fetched = fetch(context(tmp_path))
    assert metno.calls[0][1]["if_modified_since"] is None  # not the other place's time
    assert len(fetched.data.forecast.hours) == 3
    assert forecast.load(tmp_path / "forecast.json").place == HERE


def test_a_changed_place_doesnt_use_the_old_forecast_as_fallback(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = webrequest.WebError("api.met.no answered 503 Service Unavailable")
    saved(tmp_path, timedelta(minutes=30), place="-22.9100,-43.1700")
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path))


def test_broken_answer_falls_back_to_the_saved_forecast(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = webrequest.Answer(200, b'{"properties": {"timeseries": 5}}', {}, met_no.URL)
    saved(tmp_path, timedelta(hours=1))
    before = (tmp_path / "forecast.json").read_bytes()
    assert len(fetch(context(tmp_path)).data.forecast.hours) == 2
    assert (tmp_path / "forecast.json").read_bytes() == before  # not overwritten


def test_saved_file_is_private(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = ok(step(0))
    fetch(context(tmp_path))
    assert os.stat(tmp_path / "forecast.json").st_mode & 0o077 == 0


def test_fetch_asks_whether_anything_changed(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = ok(step(0), step(1))
    fetch(context(tmp_path))
    metno.result = webrequest.Answer(304, b"", {}, met_no.URL)
    again = fetch(context(tmp_path))
    assert metno.calls[1][1]["if_modified_since"] == "Mon, 05 Oct 2026 06:30:00 GMT"
    assert len(again.data.forecast.hours) == 2


HERE = "52.5200,13.4000"  # BERLIN, rounded as the plugin saves it


def saved(tmp_path, age, place=HERE, **more):
    f = Forecast(hours(0, 1), datetime.now(UTC) - age, place=place, **more)
    (tmp_path / "forecast.json").write_bytes(forecast.save(f))


def test_unreachable_uses_a_saved_forecast_up_to_6_hours(tmp_path, monkeypatch, caplog):
    metno = FakeMetNo(monkeypatch)
    metno.result = webrequest.WebError("api.met.no answered 503 Service Unavailable")
    saved(tmp_path, timedelta(hours=5, minutes=50))
    assert len(fetch(context(tmp_path)).data.forecast.hours) == 2
    assert "showing the saved forecast" in caplog.text


def test_unreachable_with_an_old_forecast_fails(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = webrequest.WebError("api.met.no answered 503 Service Unavailable")
    saved(tmp_path, timedelta(hours=6, minutes=10))
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path))


@pytest.mark.parametrize("missing", [{"lat": None}, {"lon": None}, {"email": ""}])
def test_settings_are_required(tmp_path, monkeypatch, missing):
    FakeMetNo(monkeypatch)
    with pytest.raises(ValueError, match="needs the settings lat, lon and email"):
        fetch(context(tmp_path, **missing))


# --- Drawing ---------------------------------------------------------------------------------


def weather(*rain):
    return Weather(Forecast(hours(*rain), START - timedelta(minutes=28)), START, "Europe/Berlin")


def test_draw_the_sample(tmp_path):
    values = draw(PLUGIN.sample, context(tmp_path))
    assert values["place"] == "Berlin"
    assert values["updated"] == "Updated 08:32"
    assert values["summary"] == "Max 14°C · Min 8°C · Rain 6.6 mm, 13–17, 19–20"
    assert [values[f"hour_{i}"] for i in (0, 11)] == ["09", "20"]
    assert values["mm_6"] == "3.4"
    assert values["mm_0"] == ""
    assert values["icon_0"].name == "clearsky_day.png"
    assert "icon_6" not in values  # one icon every 2 hours


def test_place_name_or_coordinates(tmp_path):
    assert draw(PLUGIN.sample, context(tmp_path, place=""))["place"] == "52.52, 13.40"
    assert draw(PLUGIN.sample, context(tmp_path))["place"] == "Berlin"


def test_fahrenheit_and_inches(tmp_path):
    values = draw(weather(0, 25.4, 0), context(tmp_path, temperature="F", rain="inch"))
    assert values["summary"] == "Max 54°F · Min 50°F · Rain 1.00 in, 10–11"
    assert values["temp_0"] == "50°"
    assert values["mm_1"] == "1.00"


def test_a_little_rain_in_inches_is_not_nothing(tmp_path):
    values = draw(weather(0, 0.1, 0), context(tmp_path, rain="inch"))
    assert values["mm_1"] == "0.01"
    assert "Rain 0.01 in" in values["summary"]


def test_rain_until_midnight_ends_at_24(tmp_path):
    late = Weather(Forecast(hours(0, 0, 1.0), START), START, "Asia/Tokyo")  # 16:00 in Tokyo
    one = timedelta(hours=1)
    spell = ((START + 7 * one, START + 8 * one),)  # 23:00 to midnight in Tokyo
    assert met_no.spells_text(spell, met_no.ZoneInfo("Asia/Tokyo")) == "23–24"
    assert draw(late, context(tmp_path))["summary"].endswith("18–19")


def test_no_rain(tmp_path):
    assert draw(weather(0, 0.05, 0), context(tmp_path))["summary"].endswith("No rain")


def test_nothing_left_to_show(tmp_path):
    old = Weather(Forecast(hours(0, 0), START), START + timedelta(hours=5))
    with pytest.raises(ForecastError):
        draw(old, context(tmp_path))


def test_unknown_icon_is_left_empty():
    assert met_no.icon("no_such_symbol") is None
    assert met_no.icon("../../../tests/images/met_no-hours_12-9in7") is None
    assert met_no.icon(None) is None
    assert met_no.icon("rain") == met_no.ICONS / "rain.png"


def test_sample_icons_exist():
    for hour in PLUGIN.sample.forecast.hours:
        assert met_no.icon(hour.symbol) is not None, hour.symbol


# --- Wind barbs ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("knots", "parts"),
    [
        (1, (0, 0, 0)),
        (2.4, (0, 0, 0)),
        (2.5, (0, 0, 1)),
        (10, (0, 1, 0)),
        (25, (0, 2, 1)),
        (50, (1, 0, 0)),
        (57, (1, 0, 1)),
        (104, (2, 0, 1)),
    ],
)
def test_barb_steps(knots, parts):
    assert barbs.steps(knots) == parts


def dark(image, box):
    return image.crop(box).point(lambda p: 255 if p < 128 else 0).histogram()[255]


@pytest.mark.parametrize(
    ("wind_from", "arrow_at"),
    [(0, "bottom"), (180, "top"), (90, "left"), (270, "right")],
)
def test_barb_points_where_the_wind_goes(wind_from, arrow_at):
    """Wind from the north goes south, so the arrow is at the bottom, and so on."""
    image = barbs.barb(1.5, wind_from)  # no feathers: only the line and the arrowhead
    sides = {
        "top": (100, 0, 150, 60),
        "bottom": (100, 190, 150, 250),
        "left": (0, 100, 60, 150),
        "right": (190, 100, 250, 150),
    }
    opposite = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
    assert dark(image, sides[arrow_at]) > dark(image, sides[opposite[arrow_at]])


def test_a_feather_after_a_triangle_is_visible():
    assert barbs.barb(60, 180).tobytes() != barbs.barb(50, 180).tobytes()
    assert barbs.barb(55, 180).tobytes() != barbs.barb(50, 180).tobytes()
    # The short feather adds clearly visible ink, not a bump on the triangle.
    whole = (0, 0, 250, 250)
    assert dark(barbs.barb(55, 180), whole) - dark(barbs.barb(50, 180), whole) > 150


def test_calm_and_storm_look_different():
    calm, storm, breeze = barbs.barb(0.5, 90), barbs.barb(110, 90), barbs.barb(10, 90)
    assert calm.tobytes() == barbs.barb(0.5, 270).tobytes()  # a circle has no direction
    assert len({calm.tobytes(), storm.tobytes(), breeze.tobytes()}) == 3


def test_barb_size():
    assert barbs.barb(10, 45, size=100).size == (100, 100)


# --- The other layouts -----------------------------------------------------------------------


@pytest.mark.parametrize("layout", list(met_no.LAYOUTS))
def test_every_block_gets_a_value(tmp_path, layout):
    """draw fills exactly the blocks of the chosen layout, no more, no fewer."""
    blocks = Layout(met_no.LAYOUTS[layout](Settings())).blocks
    assert set(draw(PLUGIN.sample, context(tmp_path, layout))) == set(blocks)


@pytest.mark.parametrize("layout", list(met_no.LAYOUTS))
def test_every_layout_shows_the_place(tmp_path, layout):
    assert draw(PLUGIN.sample, context(tmp_path, layout))["place"] == "Berlin"


@pytest.mark.parametrize("count", [1, 2, 4, 7])
@pytest.mark.parametrize("layout", list(met_no.LAYOUTS))
def test_fewer_than_12_hours_still_draws(tmp_path, layout, count):
    """Near the 6-hour limit of a saved forecast, fewer hours are left; the rest stays empty."""
    few = Weather(Forecast(hours(*[0.5] * count), START), START, "Europe/Berlin")
    values = draw(few, context(tmp_path, layout))
    assert sum(name.startswith("step_temp_") for name in values) == (
        count // 3 if layout == "steps_3h" else 0
    )
    PLUGIN.layout(layout, Settings()).prepare(400, 300, ScreenMode.gray(16)).render(values)


def steps_at(start, zone, count=12, rain=0.0):
    hours_ = tuple(
        Hour(start + timedelta(hours=i), 10.0, rain, "cloudy", 3.0, 200.0) for i in range(count)
    )
    return Weather(Forecast(hours_, start), start, zone)


@pytest.mark.parametrize(
    ("start", "zone", "labels"),
    [
        (
            datetime(2026, 10, 5, 19, tzinfo=UTC),
            "Europe/Berlin",
            ["21–24", "00–03", "03–06", "06–09"],
        ),
        (
            datetime(2026, 10, 5, 20, tzinfo=UTC),
            "Europe/Berlin",
            ["22–01", "01–04", "04–07", "07–10"],
        ),
        # The night the clocks go forward: 02:00 becomes 03:00.
        (
            datetime(2026, 3, 28, 23, tzinfo=UTC),
            "Europe/Berlin",
            ["00–04", "04–07", "07–10", "10–13"],
        ),
    ],
)
def test_step_labels(tmp_path, start, zone, labels):
    values = draw(steps_at(start, zone), context(tmp_path, "steps_3h"))
    assert [values[f"step_{k}"] for k in range(4)] == labels


def test_small_and_now(tmp_path):
    small = draw(PLUGIN.sample, context(tmp_path, "small"))
    assert small["now_temp"] == "8°C"
    assert small["temperatures"] == "Max 14°C · Min 8°C"
    assert small["rain"] == "Rain 6.6 mm, 13–17, 19–20"
    assert small["now_icon"].name == "clearsky_day.png"
    assert "now_barb" not in small  # txoof: no wind barb on tiny screens
    assert small["now_icon"] == met_no.icon(PLUGIN.sample.forecast.hours[0].symbol)
    assert draw(weather(0, 0), context(tmp_path, "small"))["rain"] == "No rain"


def test_steps_of_3_hours(tmp_path):
    values = draw(PLUGIN.sample, context(tmp_path, "steps_3h"))
    assert [values[f"step_{k}"] for k in range(4)] == ["09–12", "12–15", "15–18", "18–21"]
    assert values["step_temp_0"] == "8–11°"
    assert values["step_rain_0"] == ""
    assert values["step_rain_2"] == "4.5 mm"  # 3.4 + 1.1 + 0
    same = draw(weather(0, 0, 0), context(tmp_path, "steps_3h"))
    assert same["step_temp_0"] == "10–12°"
    # The icon of the wettest hour (15:00, heavy rain), the wind of the middle hour.
    assert values["step_icon_2"].name == "heavyrain.png"
    middle = PLUGIN.sample.forecast.hours[7]  # 16:00, the middle of 15-18
    expected = barbs.barb(middle.wind_speed * forecast.KNOTS, middle.wind_from)
    assert values["step_barb_2"].tobytes() == expected.tobytes()


def test_drizzle_is_dry_in_steps_too(tmp_path):
    values = draw(steps_at(START, "Europe/Berlin", rain=0.05), context(tmp_path, "steps_3h"))
    assert values["summary"].endswith("No rain")
    assert values["step_rain_0"] == ""


def test_step_rain_in_inches(tmp_path):
    values = draw(
        steps_at(START, "Europe/Berlin", rain=8.5), context(tmp_path, "steps_3h", rain="inch")
    )
    assert values["step_rain_0"] == "1.00 in"


def test_now(tmp_path):
    values = draw(PLUGIN.sample, context(tmp_path, "now"))
    first = PLUGIN.sample.forecast.hours[0]
    assert values["now_temp"] == "8°C"
    assert (
        values["now_barb"].tobytes()
        == barbs.barb(first.wind_speed * forecast.KNOTS, first.wind_from).tobytes()
    )


def test_portrait_rows_hold_their_own_hour(tmp_path):
    values = draw(PLUGIN.sample, context(tmp_path, "portrait_hours"))
    hour = PLUGIN.sample.forecast.hours[6]  # 15:00
    assert values["hour_6"] == "15"
    assert values["temp_6"] == "13°"
    assert values["mm_6"] == "3.4"
    assert values["hicon_6"].name == f"{hour.symbol}.png"


def test_no_minus_zero(tmp_path):
    assert met_no.degrees(-0.4, "C") == "0°"


def test_sideways_rain_bars():
    upright = met_no.rain_bar(1.0, 2.0)
    sideways = met_no.rain_bar(1.0, 2.0, upright=False)
    assert upright.width < upright.height and sideways.width > sideways.height
    assert sideways.getpixel((500, 200)) == 0  # half full from the left
    assert sideways.getpixel((700, 200)) == 255
