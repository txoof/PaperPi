"""met_no: the weather for the next 12 hours, from the Norwegian Meteorological Institute."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from ... import webrequest
from ...files import write_atomic
from ...places import location_helper
from ...plugin import Context, Plugin, PluginSettings, ready, setting
from . import barbs, forecast
from .forecast import Forecast, Hour
from .layouts import HOURS, LAYOUTS, PICKS

log = logging.getLogger(__name__)

URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
SAVED = "forecast.json"
#: A saved forecast is used when met.no can't be reached, until it is this old.
OLDEST = timedelta(hours=6)
#: The longest wait for met.no's "Expires" time, in case it is far ahead or the clock is off.
LONGEST_WAIT = timedelta(hours=1)
ICONS = Path(__file__).parent / "icons"
#: met.no's data licence (CC BY 4.0) asks for credit; it is shown on the screen.
CREDIT = "Data: MET Norway"


class Settings(PluginSettings):
    lat: float | None = setting(
        None,
        required=True,
        group="Place",
        ge=-90,
        le=90,
        helper="location",
        description="Latitude of the place, e.g. 52.52",
    )
    lon: float | None = setting(
        None,
        required=True,
        group="Place",
        ge=-180,
        le=180,
        description="Longitude of the place, e.g. 13.40",
    )
    altitude: int | None = setting(
        None,
        group="Place",
        ge=-500,
        le=9000,
        description="Height of the ground at the place, in whole metres, e.g. 34. Makes the "
        "temperatures more exact in hills and mountains (else met.no guesses it from its own "
        "map)",
    )
    place: str = setting(
        "",
        group="Place",
        max_length=60,
        description="Name shown on the screen, e.g. Berlin (else lat, lon)",
    )
    email: str = setting(
        "",
        required=True,
        max_length=200,
        pattern=r"^$|^[^@\s]+@[^@\s]+$",
        description="Your own, real email address, sent only to met.no (their terms of "
        "service ask for one)",
    )
    temperature: Literal["C", "F"] = setting(
        "C", group="Units", description="Degrees Celsius or Fahrenheit"
    )
    rain: Literal["mm", "inch"] = setting(
        "mm", group="Units", description="Rain in millimetres or inches"
    )
    wind: Literal["m/s", "km/h", "mph", "knots"] = setting(
        "m/s",
        group="Units",
        description="Wind speed, shown by the now layout (wind barbs are always in knots)",
    )


@dataclass(frozen=True)
class Weather:
    """What ``draw`` gets: the forecast, the time to start the 12 hours at, and the time
    zone to show hours in (``None``: this computer's own)."""

    forecast: Forecast
    now: datetime
    zone: str | None = None


class SettingsMissing(ValueError):
    pass


def fetch(context: Context):
    settings = context.settings
    if settings.lat is None or settings.lon is None or not settings.email:
        raise SettingsMissing(
            "met_no needs the settings lat, lon and email (met.no asks every program for "
            "contact details)"
        )
    now = datetime.now(UTC)
    path = context.storage / SAVED
    place = f"{settings.lat:.4f},{settings.lon:.4f}"
    if settings.altitude is not None:
        place += f",{settings.altitude}"
    saved = forecast.load(path)
    if saved and saved.place != place:
        saved = None  # the place was changed: the saved forecast is for somewhere else
    if saved and saved.expires and now < min(saved.expires, saved.fetched + LONGEST_WAIT):
        return ready(Weather(saved, now))  # met.no asks not to fetch again before this
    try:
        latest = download(settings, place, saved, now)
    except (webrequest.WebError, forecast.ForecastError) as error:
        if saved and now - saved.fetched <= OLDEST:
            log.warning("met.no can't be reached, showing the saved forecast: %s", error)
            return ready(Weather(saved, now))
        raise
    try:
        write_atomic(path, forecast.save(latest))
    except OSError as error:
        log.warning("can't save the forecast, showing it anyway: %s", error)
    return ready(Weather(latest, now))


def download(settings: Settings, place: str, saved: Forecast | None, now: datetime) -> Forecast:
    # met.no asks for at most 4 decimals: more only makes its caching work less well.
    lat, lon, *altitude = place.split(",")
    extra = f"&altitude={altitude[0]}" if altitude else ""
    answer = webrequest.get(
        f"{URL}?lat={lat}&lon={lon}{extra}",
        contact=settings.email,
        if_modified_since=saved.last_modified if saved else None,
    )
    if answer.status == 203:
        # met.no's way of saying this version of its service will be switched off.
        log.warning("met.no says this forecast service is going to be replaced")
    expires = _expires(answer.headers.get("expires"))
    if answer.not_modified and saved:
        return replace(saved, fetched=now, expires=expires)
    return Forecast(forecast.trim(answer.json()), now, expires, answer.last_modified, place)


def _expires(text: str | None) -> datetime | None:
    try:
        return parsedate_to_datetime(text).astimezone(UTC)
    except (TypeError, ValueError):
        return None


# --- Drawing ---------------------------------------------------------------------------------


def degrees(celsius: float, unit: str) -> str:
    value = celsius * 9 / 5 + 32 if unit == "F" else celsius
    return f"{round(value)}°"  # round(): -0.4 shows as "0°", not "-0°"


def rain_unit(settings: Settings) -> str:
    return "in" if settings.rain == "inch" else "mm"


def end_hour(t: datetime, zone) -> str:
    """The hour something ends, in local time: "24" for midnight, not "00"."""
    hour = t.astimezone(zone).hour
    return "24" if hour == 0 else f"{hour:02d}"


def rain_text(mm: float, unit: str) -> str:
    """The number only: "6.2", "12", or in inches "0.25" (at least "0.01", so a little
    rain never shows as nothing). Dry hours give an empty text."""
    if mm < forecast.WET:
        return ""
    if unit == "inch":
        return f"{max(mm / 25.4, 0.01):.2f}"
    return f"{mm:.1f}" if mm < 10 else f"{mm:.0f}"


def spells_text(spells, zone) -> str:
    """ "13–17, 19–20": the hours it rains, in local time. Rain until midnight ends at
    "24", not "00"."""
    return ", ".join(f"{start.astimezone(zone):%H}–{end_hour(end, zone)}" for start, end in spells)


def temperatures_text(s: forecast.Summary, settings: Settings) -> str:
    t = settings.temperature
    return f"Max {degrees(s.high, t)}{t} · Min {degrees(s.low, t)}{t}"


def rain_summary_text(s: forecast.Summary, settings: Settings, zone) -> str:
    """ "Rain 6.6 mm, 13–17, 19–20", or "No rain"."""
    if not s.spells:
        return "No rain"
    total = rain_text(s.rain, settings.rain) or "0.1"
    return f"Rain {total} {rain_unit(settings)}, {spells_text(s.spells, zone)}"


#: Wind speed units: the number to multiply m/s by, and the text shown after the speed.
WIND_UNITS = {
    "m/s": (1.0, "m/s"),
    "km/h": (3.6, "km/h"),
    "mph": (2.236936, "mph"),
    "knots": (forecast.KNOTS, "kn"),
}


def wind_text(speed: float, unit: str) -> str:
    """ "4 m/s": a wind speed in m/s, in the chosen unit."""
    factor, name = WIND_UNITS[unit]
    return f"{round(speed * factor)} {name}"


def wind_arrow(wind_from: float):
    """A plain, thick arrow that points where the wind is going: easier to see from a
    distance than a barb. Drawn larger than shown, like the rain bars."""
    size = 400
    picture = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(picture)
    middle = size / 2
    draw.line((middle, 60, middle, size - 110), fill=0, width=36)
    draw.polygon(
        [(middle - 90, size - 150), (middle + 90, size - 150), (middle, size - 20)], fill=0
    )
    # Drawn pointing down: wind from the north (0°) goes south. Turned clockwise from there.
    return picture.rotate(-wind_from, resample=Image.Resampling.BICUBIC, fillcolor=255)


def rain_amount(mm: float, settings: Settings) -> str:
    """ "3.4 mm", or "dry" when it doesn't rain."""
    number = rain_text(mm, settings.rain)
    return f"{number} {rain_unit(settings)}" if number else "dry"


def rain_start_text(s: forecast.Summary, zone) -> str:
    """ "Rain from 13:00", or "No rain"."""
    if not s.spells:
        return "No rain"
    return f"Rain from {s.spells[0][0].astimezone(zone):%H}:00"


def summary_text(s: forecast.Summary, settings: Settings, zone) -> str:
    return f"{temperatures_text(s, settings)} · {rain_summary_text(s, settings, zone)}"


def rain_bar(mm: float, top: float, *, upright: bool = True):
    """A bar for one hour's rain; full length is ``top`` mm. Upright bars grow from the
    bottom, the others (for the tall layouts) from the left."""
    # Drawn larger than it will be shown, so the layout only ever shrinks it: enlarging
    # would blur the edges, and blurred edges show as dots on black-and-white screens.
    long, short, edge, ground = 1200, 400, 40, 16
    filled = round(long * min(mm / top, 1.0)) if mm >= forecast.WET else 0
    if upright:
        image = Image.new("L", (short, long), 255)
        draw = ImageDraw.Draw(image)
        if filled:
            draw.rectangle((edge, long - filled, short - edge - 1, long - 1), fill=0)
        draw.rectangle((0, long - ground, short - 1, long - 1), fill=0)
    else:
        image = Image.new("L", (long, short), 255)
        draw = ImageDraw.Draw(image)
        if filled:
            draw.rectangle((0, edge, filled - 1, short - edge - 1), fill=0)
        draw.rectangle((0, 0, ground - 1, short - 1), fill=0)
    return image


def place_name(settings: Settings) -> str:
    """The name shown for the place: the ``place`` setting, or else the coordinates."""
    if settings.place:
        return settings.place
    if settings.lat is None or settings.lon is None:
        return ""
    return f"{settings.lat:.2f}, {settings.lon:.2f}"


def icon(symbol: str | None):
    """The icon file for a met.no symbol name, or ``None``. Only plain names are used, so
    a strange name from the network can't point at another file."""
    if not symbol or not re.fullmatch(r"[a-z_]+", symbol):
        return None
    path = ICONS / f"{symbol}.png"
    return path if path.is_file() else None


def draw(weather: Weather, context: Context) -> dict:
    settings = context.settings
    zone = ZoneInfo(weather.zone) if weather.zone else None
    hours = forecast.window(weather.forecast, weather.now, HOURS)
    if not hours:
        raise forecast.ForecastError("the saved forecast has no hours from now on")
    local = (lambda t: t.astimezone(zone)) if zone else (lambda t: t.astimezone())
    t, unit = settings.temperature, settings.rain
    summary = forecast.summarize(hours)
    # Bars share one scale: at least 2 mm per hour, so a drizzle doesn't look like a storm.
    top = max([2.0, *(h.rain for h in hours)])

    def wind(hour: Hour):
        return barbs.barb(hour.wind_speed * forecast.KNOTS, hour.wind_from)

    # What each block can show. Only the blocks of the chosen layout are made, because
    # pictures (barbs, bars) take time to draw.
    makers = {
        "place": lambda: place_name(settings),
        "updated": lambda: f"Updated {local(weather.forecast.fetched):%H:%M} · {CREDIT}",
        "summary": lambda: summary_text(summary, settings, zone),
        "temperatures": lambda: temperatures_text(summary, settings),
        "rain": lambda: rain_summary_text(summary, settings, zone),
        "now_temp": lambda: f"{degrees(hours[0].temperature, t)}{t}",
        "now_icon": lambda: icon(hours[0].symbol),
        "now_barb": lambda: wind(hours[0]),
        "now_degrees": lambda: degrees(hours[0].temperature, t),
        "now_arrow": lambda: wind_arrow(hours[0].wind_from),
        "now_wind": lambda: wind_text(hours[0].wind_speed, settings.wind),
        "high": lambda: f"Max {degrees(summary.high, t)}",
        "low": lambda: f"Min {degrees(summary.low, t)}",
        "rain_start": lambda: rain_start_text(summary, zone),
    }
    for k, i in enumerate(PICKS):
        if i >= len(hours):
            break
        hour = hours[i]
        makers |= {
            f"pick_time_{k}": lambda h=hour: f"{local(h.time):%H:%M}",
            f"pick_name_{k}": lambda h=hour, k=k: "Now" if k == 0 else f"{local(h.time):%H:%M}",
            f"pick_icon_{k}": lambda h=hour: icon(h.symbol),
            f"pick_temp_{k}": lambda h=hour: degrees(h.temperature, t),
            f"pick_rain_{k}": lambda h=hour: rain_amount(h.rain, settings),
            f"pick_barb_{k}": lambda h=hour: wind(h),
        }
    pairs = [hours[i : i + 2] for i in range(0, len(hours), 2)]
    wet = [sum(h.rain for h in pair if h.rain >= forecast.WET) for pair in pairs]
    pair_top = max([2 * 2.0, *wet])  # like the hourly bars: at least 2 mm per hour
    for k, (pair, mm) in enumerate(zip(pairs, wet, strict=True)):
        makers |= {
            f"pair_hour_{k}": lambda h=pair[0]: f"{local(h.time):%H}",
            f"pair_icon_{k}": lambda h=pair[0]: icon(h.symbol),
            f"pair_temp_{k}": lambda h=pair[0]: degrees(h.temperature, t),
            f"pair_bar_{k}": lambda mm=mm: rain_bar(mm, pair_top),
            f"pair_mm_{k}": lambda mm=mm: rain_text(mm, unit),
        }
    for i, hour in enumerate(hours):
        makers |= {
            f"bar_{i}": lambda h=hour: rain_bar(h.rain, top),
            f"hbar_{i}": lambda h=hour: rain_bar(h.rain, top, upright=False),
            f"mm_{i}": lambda h=hour: rain_text(h.rain, unit),
            f"hour_{i}": lambda h=hour: f"{local(h.time):%H}",
            f"temp_{i}": lambda h=hour: degrees(h.temperature, t),
            f"barb_{i}": lambda h=hour: wind(h),
            f"hicon_{i}": lambda h=hour: icon(h.symbol),
        }
        if i % 2 == 0:
            makers[f"icon_{i // 2}"] = lambda h=hour: icon(h.symbol)
    for k in range(len(hours) // 3):
        part = hours[3 * k : 3 * k + 3]
        mm = sum(h.rain for h in part if h.rain >= forecast.WET)
        # The icon of the wettest hour, so it matches the rain shown under it; when dry,
        # the middle hour's.
        wettest = max(part, key=lambda h: h.rain)
        shown = wettest if wettest.rain >= forecast.WET else part[1]
        end = part[-1].time + timedelta(hours=1)
        makers |= {
            f"step_{k}": lambda p=part, e=end: f"{local(p[0].time):%H}–{end_hour(e, zone)}",
            f"step_icon_{k}": lambda h=shown: icon(h.symbol),
            f"step_temp_{k}": lambda p=part: degrees(max(h.temperature for h in p), t),
            f"step_rain_{k}": lambda mm=mm: rain_amount(mm, settings),
        }
    wanted = PLUGIN.layout(context.layout, settings).blocks
    return {name: make() for name, make in makers.items() if name in wanted}


def _sample() -> Weather:
    """A made-up afternoon in Berlin with a shower, so every part of the layouts shows."""
    start = datetime(2026, 10, 5, 7, tzinfo=UTC)  # 09:00 in Berlin
    temperatures = [8.4, 9.6, 11.2, 12.8, 13.9, 14.3, 13.1, 12.0, 11.4, 10.6, 9.9, 9.2, 8.8]
    rain = [0, 0, 0, 0, 0.2, 1.6, 3.4, 1.1, 0, 0, 0.3, 0, 0]
    symbols = [
        "clearsky_day", "clearsky_day", "fair_day", "partlycloudy_day", "lightrainshowers_day",
        "rainshowers_day", "heavyrain", "rain", "cloudy", "partlycloudy_night",
        "lightrain", "cloudy", "fair_night",
    ]  # fmt: skip
    wind = [
        (1.5, 200),
        (2.6, 210),
        (3.4, 220),
        (4.8, 230),
        (6.2, 240),
        (9.3, 250),
        (12.6, 260),
        (8.1, 270),
        (5.4, 280),
        (3.0, 290),
        (0.3, 300),
        (2.2, 310),
        (2.0, 320),
    ]
    hours = tuple(
        Hour(start + timedelta(hours=i), temperatures[i], rain[i], symbols[i], *wind[i])
        for i in range(13)
    )
    fetched = start - timedelta(minutes=28)
    forecast_ = Forecast(hours, fetched, place="52.5200,13.4000")
    return Weather(forecast_, start + timedelta(minutes=10), "Europe/Berlin")


PLUGIN = Plugin(
    type="met_no",
    title="Weather",
    network="internet",
    description="The weather for the next 12 hours from met.no: temperature, rain and wind.",
    settings=Settings,
    layouts=LAYOUTS,
    layout_titles={
        "hours_12": "Next 12 hours",
        "three_rows": "Three rows: now, +3 and +6 hours",
        "three_columns": "Three columns: now, +3 and +6 hours",
        "now_and_today": "Right now and today",
        "six_hours": "Every 2 hours",
        "steps_3h": "Every 3 hours",
        "now": "Right now, large",
        "small": "Small: right now",
        "portrait_hours": "Upright: hour by hour",
        "portrait_now": "Upright: right now",
    },
    fetch=fetch,
    draw=draw,
    sample=_sample(),
    refresh=30 * 60,
    helpers={"location": location_helper(altitude="altitude", name="place")},
)
