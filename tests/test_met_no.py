"""The met_no weather plugin: trimming met.no's answer, the saved forecast, drawing."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from epdlib import ScreenMode

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


def test_trim_skips_broken_steps():
    broken = step(1)
    del broken["data"]["instant"]["details"]["air_temperature"]
    assert len(forecast.trim(answer(step(0), broken, step(2)))) == 2


@pytest.mark.parametrize("data", [{}, {"properties": {}}, answer(), [], "text"])
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
    metno.result = ok(step(0), expires=later.strftime("%a, %d %b %Y %H:%M:%S GMT"))
    fetch(context(tmp_path))
    fetch(context(tmp_path))
    assert len(metno.calls) == 1


def test_fetch_asks_whether_anything_changed(tmp_path, monkeypatch):
    metno = FakeMetNo(monkeypatch)
    metno.result = ok(step(0), step(1))
    fetch(context(tmp_path))
    metno.result = webrequest.Answer(304, b"", {}, met_no.URL)
    again = fetch(context(tmp_path))
    assert metno.calls[1][1]["if_modified_since"] == "Mon, 05 Oct 2026 06:30:00 GMT"
    assert len(again.data.forecast.hours) == 2


def saved(tmp_path, age):
    f = Forecast(hours(0, 1), datetime.now(UTC) - age)
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


def test_fahrenheit_and_inches(tmp_path):
    values = draw(weather(0, 25.4, 0), context(tmp_path, temperature="F", rain="inch"))
    assert values["summary"] == "Max 54°F · Min 50°F · Rain 1.00 in, 10–11"
    assert values["temp_0"] == "50°"
    assert values["mm_1"] == "1.00"


def test_no_rain(tmp_path):
    assert draw(weather(0, 0.05, 0), context(tmp_path))["summary"].endswith("No rain")


def test_nothing_left_to_show(tmp_path):
    old = Weather(Forecast(hours(0, 0), START), START + timedelta(hours=5))
    with pytest.raises(ForecastError):
        draw(old, context(tmp_path))


def test_unknown_icon_is_left_empty():
    assert met_no.icon("no_such_symbol") is None
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


def test_barb_points_where_the_wind_goes():
    north_wind = barbs.barb(10, 0)  # coming from the north, so going south: arrow at the bottom
    south_wind = barbs.barb(10, 180)
    top, bottom = (100, 0, 150, 60), (100, 190, 150, 250)
    assert dark(south_wind, top) > dark(south_wind, bottom)
    assert dark(north_wind, bottom) > dark(north_wind, top)


def test_calm_and_storm_look_different():
    calm, storm, breeze = barbs.barb(0.5, 90), barbs.barb(110, 90), barbs.barb(10, 90)
    assert calm.tobytes() == barbs.barb(0.5, 270).tobytes()  # a circle has no direction
    assert len({calm.tobytes(), storm.tobytes(), breeze.tobytes()}) == 3


def test_barb_size():
    assert barbs.barb(10, 45, size=100).size == (100, 100)
