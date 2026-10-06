"""met.no's forecast, trimmed to what the plugin shows.

met.no's answer is large: about 90 time steps, each with many values. Right after
downloading, :func:`trim` keeps one small :class:`Hour` per hour, and everything else in
the plugin works with that list.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

#: Rain below this, in mm per hour, counts as dry.
WET = 0.1
#: m/s to knots (nautical miles per hour), the unit of the wind barbs.
KNOTS = 1.943844


class ForecastError(ValueError):
    """met.no's answer can't be read as a forecast."""


@dataclass(frozen=True)
class Hour:
    """The weather in one hour, starting at ``time`` (in UTC)."""

    time: datetime
    temperature: float  # °C at the start of the hour
    rain: float  # mm during the hour
    symbol: str | None  # met.no icon name, e.g. "rain" or "partlycloudy_day"
    wind_speed: float  # m/s
    wind_from: float  # degrees: 0 = from the north, 90 = from the east


@dataclass(frozen=True)
class Forecast:
    """The trimmed forecast, and when it was fetched."""

    hours: tuple[Hour, ...]
    fetched: datetime  # when met.no last confirmed it (UTC)
    expires: datetime | None = None  # met.no asks not to fetch again before this
    last_modified: str | None = None  # for "has anything changed?" next time
    place: str = ""  # the rounded coordinates it is for, "52.5200,13.4000"


def trim(answer: dict) -> tuple[Hour, ...]:
    """The hourly steps of a met.no ``locationforecast`` answer. Steps further ahead come
    in 6-hour blocks; they are left out."""
    try:
        steps = list(answer["properties"]["timeseries"])
    except (KeyError, TypeError, IndexError):
        raise ForecastError("no time steps in the answer") from None
    hours = []
    for step in steps:
        try:
            now = step["data"]["instant"]["details"]
            hour = step["data"]["next_1_hours"]
            numbers = [
                float(now["air_temperature"]),
                float(hour["details"].get("precipitation_amount", 0.0)),
                float(now["wind_speed"]),
                float(now["wind_from_direction"]),
            ]
            if not all(map(math.isfinite, numbers)):
                continue  # "NaN" or "Infinity" would be drawn as text
            symbol = hour.get("summary", {}).get("symbol_code")
            hours.append(
                Hour(
                    time=datetime.fromisoformat(step["time"]).astimezone(UTC),
                    temperature=numbers[0],
                    rain=numbers[1],
                    symbol=symbol if isinstance(symbol, str) else None,
                    wind_speed=numbers[2],
                    wind_from=numbers[3],
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            continue  # not an hourly step, or one with missing or broken values
    if not hours:
        raise ForecastError("no hourly steps in the answer")
    return tuple(hours)


def window(forecast: Forecast, now: datetime, hours: int = 12) -> tuple[Hour, ...]:
    """The ``hours`` hours from the current hour on."""
    start = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return tuple(h for h in forecast.hours if h.time >= start)[:hours]


@dataclass(frozen=True)
class Summary:
    high: float
    low: float
    rain: float  # mm in total
    spells: tuple[tuple[datetime, datetime], ...]  # (start, end) of each rainy stretch


def summarize(hours: tuple[Hour, ...]) -> Summary:
    """Max, min, total rain, and when it rains."""
    spells = []
    for hour in hours:
        if hour.rain < WET:
            continue
        end = hour.time + timedelta(hours=1)
        if spells and spells[-1][1] == hour.time:
            spells[-1] = (spells[-1][0], end)
        else:
            spells.append((hour.time, end))
    return Summary(
        high=max(h.temperature for h in hours),
        low=min(h.temperature for h in hours),
        rain=sum(h.rain for h in hours),
        spells=tuple(spells),
    )


def save(forecast: Forecast) -> bytes:
    """The forecast as JSON, for the plugin's storage folder."""
    data = asdict(forecast)
    return json.dumps(data, default=lambda t: t.isoformat()).encode()


def load(path: Path) -> Forecast | None:
    """A forecast saved by :func:`save`, or ``None`` if there is none or it can't be read."""
    try:
        data = json.loads(path.read_bytes())
        hours = tuple(
            replace(Hour(**h), time=datetime.fromisoformat(h["time"])) for h in data["hours"]
        )
        expires = data.get("expires")
        return Forecast(
            hours=hours,
            fetched=datetime.fromisoformat(data["fetched"]),
            expires=datetime.fromisoformat(expires) if expires else None,
            last_modified=data.get("last_modified"),
            place=data.get("place", ""),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None
