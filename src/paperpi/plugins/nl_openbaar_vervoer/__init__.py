"""nl_openbaar_vervoer: when the next buses and trams leave from up to four stops in the
Netherlands, and when to leave the house to catch them.

The departures come from OVapi (``v0.ovapi.nl``), a free service run by volunteers, with
the live times of all Dutch buses and trams. It asks for no key, but at most one request a
minute. Each stop is a "timing point": one side of the street, so one direction.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, field_validator

from ... import webrequest
from ...files import write_atomic
from ...plugin import NOTHING, Context, Plugin, PluginSettings, ready, setting
from . import departures
from .departures import ZONE, AnswerError, Departure
from .layouts import LAYOUTS, STOPS

log = logging.getLogger(__name__)

# Only http: OVapi's https certificate is not valid. Nothing secret is sent.
OVAPI = "http://v0.ovapi.nl"
#: Saved departures are shown when OVapi can't be reached, until they are this old.
OLDEST = timedelta(minutes=30)
SAVED = "departures.json"

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAYS: tuple[Day, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
#: A stop code: OVapi's TimingPointCode, e.g. 31001118.
CODE = r"^[A-Za-z0-9]*$"


def _stop(n: int):
    text = f"Code of stop {n}: one side of the street, e.g. 31001118"
    if n == 1:
        return setting("", required=True, pattern=CODE, max_length=20, description=text)
    return Field("", pattern=CODE, max_length=20, description=text + " (or leave empty)")


def _name(n: int):
    return Field("", max_length=30, description=f"Heading of stop {n} (empty: its name)")


def _lines(n: int):
    return Field(
        "",
        max_length=60,
        description=f"Lines to show at stop {n}, e.g. 9, 12 (empty: all lines)",
    )


def _walk(n: int):
    return Field(
        0,
        ge=0,
        le=60,
        description=f"Minutes to walk to stop {n}; each row then says when to leave (0: off)",
    )


def _days(n: int):
    return Field(DAYS, description=f"Days on which stop {n} is shown")


class Settings(PluginSettings):
    stop_1: str = _stop(1)
    name_1: str = _name(1)
    lines_1: str = _lines(1)
    walk_1: int = _walk(1)
    days_1: tuple[Day, ...] = _days(1)
    stop_2: str = _stop(2)
    name_2: str = _name(2)
    lines_2: str = _lines(2)
    walk_2: int = _walk(2)
    days_2: tuple[Day, ...] = _days(2)
    stop_3: str = _stop(3)
    name_3: str = _name(3)
    lines_3: str = _lines(3)
    walk_3: int = _walk(3)
    days_3: tuple[Day, ...] = _days(3)
    stop_4: str = _stop(4)
    name_4: str = _name(4)
    lines_4: str = _lines(4)
    walk_4: int = _walk(4)
    days_4: tuple[Day, ...] = _days(4)
    ahead: int = Field(60, ge=10, le=80, description="Minutes ahead to show departures for")

    @field_validator(
        "stop_1",
        "stop_2",
        "stop_3",
        "stop_4",
        "lines_1",
        "lines_2",
        "lines_3",
        "lines_4",
        mode="before",
    )
    @classmethod
    def _number_as_text(cls, value):
        # A code or line written without quotes in the config file is a number.
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


@dataclass(frozen=True)
class Section:
    """One stop on the screen: its heading, walking time and departures. ``missing``: OVapi
    doesn't know the stop."""

    title: str
    walk: int
    departures: tuple[Departure, ...]
    missing: bool = False


@dataclass(frozen=True)
class Board:
    """What ``draw`` gets: the stops shown today, the time now, and when the departures were
    fetched (earlier than ``now`` when OVapi could not be reached)."""

    sections: tuple[Section, ...]
    now: datetime
    fetched: datetime


def lines_of(text: str) -> tuple[str, ...]:
    """The line numbers in a ``lines_<n>`` setting: "9, 12" or "9 12"."""
    return tuple(text.replace(",", " ").split())


def today_stops(settings: Settings, now: datetime) -> list[int]:
    """The stops (1 to 4) that are set and shown on ``now``'s day."""
    day = DAYS[now.weekday()]
    return [
        n
        for n in range(1, STOPS + 1)
        if getattr(settings, f"stop_{n}") and day in getattr(settings, f"days_{n}")
    ]


def _now() -> datetime:
    """The time now in the Netherlands (replaced in tests)."""
    return datetime.now(ZONE)


def fetch(context: Context):
    settings = context.settings
    now = _now()
    wanted = today_stops(settings, now)
    if not wanted:
        return NOTHING
    codes = sorted({getattr(settings, f"stop_{n}") for n in wanted})
    path = context.storage / SAVED
    try:
        answer = webrequest.get(f"{OVAPI}/tpc/{','.join(codes)}")
        stops = departures.read(answer.json())
        fetched = now
    except (webrequest.WebError, AnswerError) as error:
        saved = departures.load(path)
        if saved is None or now - saved[1] > OLDEST:
            raise
        log.warning("OVapi can't be reached, showing the saved departures: %s", error)
        stops, fetched = saved
    else:
        _save(context, path, departures.save(stops, now))
    found = []
    for n in wanted:
        code = getattr(settings, f"stop_{n}")
        stop = stops.get(code)
        title = getattr(settings, f"name_{n}").strip() or (stop.name if stop else code)
        walk = getattr(settings, f"walk_{n}")
        if stop is None:
            found.append(Section(title, walk, (), missing=True))
            continue
        shown = departures.shown(
            stop, lines_of(getattr(settings, f"lines_{n}")), now, settings.ahead
        )
        found.append(Section(title, walk, tuple(shown)))
    return ready(Board(tuple(found), now, fetched))


def _save(context: Context, path, data: bytes) -> None:
    if context.low_disk and not path.exists():
        return  # little free space: don't add a new file (replacing one is fine)
    try:
        write_atomic(path, data)
    except OSError as error:
        log.warning("can't save the departures, showing them anyway: %s", error)


# --- Drawing ---------------------------------------------------------------------------------


def note(departure: Departure, walk: int, now: datetime) -> str:
    """What a row says after the destination: "cancelled", "left", or with a walking time
    "leave in 3 min", "leave now" or "too late"."""
    if departure.cancelled:
        return "cancelled"
    if departure.left or departure.expected < now:
        return "left"
    if not walk:
        return ""
    minutes = math.floor((departure.expected - timedelta(minutes=walk) - now).total_seconds() / 60)
    if minutes < 0:
        return "too late"
    return "leave now" if minutes == 0 else f"leave in {minutes} min"


def draw(board: Board, context: Context) -> dict:
    wanted = PLUGIN.layout(context.layout, context.settings).blocks
    values = {}
    for s, section in enumerate(board.sections):
        if f"head_{s}" not in wanted:
            break  # more stops today than the layout has room for
        walk = f" · {section.walk} min walk" if section.walk else ""
        values[f"head_{s}"] = section.title + walk
        rows = sum(1 for name in wanted if name.startswith(f"dest_{s}_"))
        if section.missing:
            values[f"dest_{s}_0"] = "Stop not found: check its code"
        elif not section.departures:
            values[f"dest_{s}_0"] = f"No departures in the next {context.settings.ahead} min"
        for i, d in enumerate(section.departures[:rows]):
            values[f"time_{s}_{i}"] = f"{d.expected.astimezone(ZONE):%H:%M}"
            values[f"delay_{s}_{i}"] = f"+{d.delay}" if d.delay > 0 else ""
            values[f"line_{s}_{i}"] = d.line
            values[f"dest_{s}_{i}"] = d.destination
            values[f"note_{s}_{i}"] = note(d, section.walk, board.now)
    if board.fetched < board.now - timedelta(minutes=5):
        values["footer"] = f"Not updated since {board.fetched.astimezone(ZONE):%H:%M}"
    else:
        values["footer"] = f"Updated {board.fetched.astimezone(ZONE):%H:%M}"
    return {name: value for name, value in values.items() if name in wanted}


def _sample() -> Board:
    """Saturday morning at Rotterdam Centraal: the two tram platforms, with made-up times."""
    now = datetime(2026, 10, 24, 8, 10, tzinfo=ZONE)

    def at(line, destination, minutes, delay=0, **more):
        planned = now + timedelta(minutes=minutes)
        return Departure(line, destination, planned, planned + timedelta(minutes=delay), **more)

    platform_a = (
        at("14", "Heemraadsplein", -3, left=True),
        at("18", "Spangen", 2, delay=1),
        at("14", "Heemraadsplein", 9),
        at("18", "Spangen", 17),
        at("14", "Heemraadsplein", 24, delay=3),
        at("18", "Spangen", 32),
        at("14", "Heemraadsplein", 39),
    )
    platform_b = (
        at("5", "Carnisselande", 4),
        at("5", "Carnisselande", 14, cancelled=True),
        at("5", "Carnisselande", 24, delay=2),
        at("5", "Carnisselande", 34),
    )
    return Board(
        (
            Section("Centraal perron A", 6, platform_a),
            Section("Centraal perron B", 6, platform_b),
        ),
        now,
        now,
    )


PLUGIN = Plugin(
    type="nl_openbaar_vervoer",
    title="Dutch public transport",
    network="internet",
    description="When the next buses and trams leave from up to four stops in the "
    "Netherlands, and when to leave the house to catch them. Live times from OVapi.",
    settings=Settings,
    layouts=LAYOUTS,
    layout_titles={"sections": "A heading per stop"},
    fetch=fetch,
    draw=draw,
    sample=_sample(),
    refresh=120,
)
