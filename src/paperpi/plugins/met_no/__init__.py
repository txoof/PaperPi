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
from pydantic import Field

from ... import webrequest
from ...files import write_atomic
from ...plugin import Context, Plugin, PluginSettings, ready
from . import barbs, forecast
from .forecast import Forecast, Hour
from .layouts import HOURS, LAYOUTS

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
    lat: float | None = Field(
        None, ge=-90, le=90, description="Latitude of the place, e.g. 52.52 (required)"
    )
    lon: float | None = Field(
        None, ge=-180, le=180, description="Longitude of the place, e.g. 13.40 (required)"
    )
    place: str = Field(
        "", max_length=60, description="Name shown on the screen, e.g. Berlin (else lat, lon)"
    )
    email: str = Field(
        "",
        max_length=200,
        pattern=r"^$|^[^@\s]+@[^@\s]+$",
        description="Your email address, sent only to met.no (required: met.no asks for it)",
    )
    temperature: Literal["C", "F"] = Field("C", description="Degrees Celsius or Fahrenheit")
    rain: Literal["mm", "inch"] = Field("mm", description="Rain in millimetres or inches")


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
    lat, lon = place.split(",")
    answer = webrequest.get(
        f"{URL}?lat={lat}&lon={lon}",
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
    return f"{value:.0f}°"


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

    def end_hour(t):
        hour = t.astimezone(zone).hour
        return "24" if hour == 0 else f"{hour:02d}"

    return ", ".join(f"{start.astimezone(zone):%H}–{end_hour(end)}" for start, end in spells)


def summary_text(hours: tuple[Hour, ...], settings: Settings, zone) -> str:
    s = forecast.summarize(hours)
    unit = "in" if settings.rain == "inch" else "mm"
    t = settings.temperature
    text = f"Max {degrees(s.high, t)}{t} · Min {degrees(s.low, t)}{t} · "
    if not s.spells:
        return text + "No rain"
    total = rain_text(s.rain, settings.rain) or "0.1"
    return text + f"Rain {total} {unit}, {spells_text(s.spells, zone)}"


def rain_bar(mm: float, top: float):
    """A bar for one hour's rain; full height is ``top`` mm."""
    # Drawn larger than it will be shown, so the layout only ever shrinks it: enlarging
    # would blur the edges, and blurred edges show as dots on black-and-white screens.
    width, height = 400, 1200
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    filled = round(height * min(mm / top, 1.0)) if mm >= forecast.WET else 0
    if filled:
        draw.rectangle((40, height - filled, width - 41, height - 1), fill=0)
    draw.rectangle((0, height - 16, width - 1, height - 1), fill=0)  # the ground
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
    values = {
        "place": place_name(settings),
        "updated": f"Updated {local(weather.forecast.fetched):%H:%M} · {CREDIT}",
        "summary": summary_text(hours, settings, zone),
    }
    # Bars share one scale: at least 2 mm per hour, so a drizzle doesn't look like a storm.
    top = max([2.0, *(h.rain for h in hours)])
    for i, hour in enumerate(hours):
        values[f"bar_{i}"] = rain_bar(hour.rain, top)
        values[f"mm_{i}"] = rain_text(hour.rain, settings.rain)
        values[f"hour_{i}"] = f"{local(hour.time):%H}"
        values[f"temp_{i}"] = degrees(hour.temperature, settings.temperature)
        values[f"barb_{i}"] = barbs.barb(hour.wind_speed * forecast.KNOTS, hour.wind_from)
        if i % 2 == 0:
            values[f"icon_{i // 2}"] = icon(hour.symbol)
    return values


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
    description="The weather for the next 12 hours from met.no: temperature, rain and wind.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=_sample(),
    refresh=30 * 60,
)
