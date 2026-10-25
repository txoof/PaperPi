"""nl_openbaar_vervoer: when the next buses and trams leave from up to four stops in the
Netherlands, and the next trains on up to two routes, with when to leave the house.

Bus and tram departures come from OVapi (``v0.ovapi.nl``), a free service run by
volunteers, with the live times of all Dutch buses and trams. It asks for no key, but at
most one request a minute. Each stop is a "timing point": one side of the street, so one
direction. Trains come from the NS API, which needs a free key (see :mod:`.ns`).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import Field, SecretStr, field_validator

from ... import fonts, webrequest
from ...files import write_atomic
from ...plugin import NOTHING, Context, Plugin, PluginSettings, alert, ready
from . import departures, ns
from .departures import ZONE, AnswerError, Departure, Saved
from .layouts import LAYOUTS, ROUTES, STOPS
from .ns import Notice

log = logging.getLogger(__name__)

# Only http: OVapi's https certificate is not valid. Nothing secret is sent.
OVAPI = "http://v0.ovapi.nl"
#: Saved departures are shown when OVapi can't be reached, until they are this old.
OLDEST = timedelta(minutes=30)
#: OVapi asks for at most one request a minute: a quicker update uses the saved departures.
QUICKEST = timedelta(minutes=1)
SAVED = "departures.json"
DISRUPTIONS = "disruptions.json"

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAYS: tuple[Day, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
#: A stop code: OVapi's TimingPointCode, e.g. 31001118.
CODE = r"^[A-Za-z0-9]*$"
#: An NS station code, e.g. GVC (Den Haag Centraal) or UT (Utrecht Centraal).
STATION = r"^[A-Za-z]*$"


class SettingsMissing(ValueError):
    pass


def _stop(n: int):
    return Field(
        "",
        pattern=CODE,
        max_length=20,
        description=f"Code of stop {n}: one side of the street, e.g. 31001118 (or leave empty)",
    )


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
        description=f"Minutes from your front door to stop {n}, with a minute to spare (0: off). "
        "Each row then says when to leave. See the README for how to estimate it",
    )


def _days(n: int, what: str = "stop"):
    return Field(DAYS, description=f"Days on which {what} {n} is shown")


def _station(n: int, end: str):
    example = "GVC (Den Haag Centraal)" if end == "from" else "UT (Utrecht Centraal)"
    return Field(
        "",
        pattern=STATION,
        max_length=8,
        description=f"NS code of the station train route {n} goes {end}, e.g. {example} "
        "(or leave empty)",
    )


def _train_walk(n: int):
    return Field(
        0,
        ge=0,
        le=90,
        description=f"Minutes from your front door to the platform of train route {n}, walking "
        "or cycling, with a minute to spare (0: off). See the README for how to estimate it",
    )


def _changes(n: int):
    return Field(
        False,
        description=f"Train route {n}: also show trips with a change of train (off: direct only)",
    )


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
    ns_key: SecretStr = Field(
        SecretStr(""),
        description="NS API key, needed for trains (free; the plugin's README says how to get it)",
    )
    train_from_1: str = _station(1, "from")
    train_to_1: str = _station(1, "to")
    train_walk_1: int = _train_walk(1)
    train_days_1: tuple[Day, ...] = _days(1, "train route")
    train_changes_1: bool = _changes(1)
    train_from_2: str = _station(2, "from")
    train_to_2: str = _station(2, "to")
    train_walk_2: int = _train_walk(2)
    train_days_2: tuple[Day, ...] = _days(2, "train route")
    train_changes_2: bool = _changes(2)
    alert_on_disruption: bool = Field(
        False,
        description="Show this plugin as an alert while NS reports a disruption on a train route "
        "(not for planned works)",
    )
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

    @field_validator("train_from_1", "train_to_1", "train_from_2", "train_to_2")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


@dataclass(frozen=True)
class Section:
    """One stop or train route on the screen: its heading, walking time and departures.
    ``problem``: why there are no departures to show, e.g. OVapi doesn't know the stop.
    ``short``: a shorter title for the rows of the ``by_time`` layout (empty: ``title``)."""

    title: str
    walk: int
    departures: tuple[Departure, ...]
    problem: str = ""
    short: str = ""


@dataclass(frozen=True)
class Board:
    """What ``draw`` gets: the stops and routes shown today, the time now, when the oldest
    departures were fetched (earlier than ``now`` when OVapi or NS could not be reached) and
    the disruptions on the routes."""

    sections: tuple[Section, ...]
    now: datetime
    fetched: datetime
    notices: tuple[Notice, ...] = ()


def lines_of(text: str) -> tuple[str, ...]:
    """The line numbers in a ``lines_<n>`` setting: "9, 12" or "9 12"."""
    return tuple(text.replace(",", " ").split())


def today_stops(settings: Settings, now: datetime) -> list[int]:
    """The stops (1 to 4) that are set and shown on ``now``'s day."""
    day = DAYS[now.astimezone(ZONE).weekday()]
    return [
        n
        for n in range(1, STOPS + 1)
        if getattr(settings, f"stop_{n}") and day in getattr(settings, f"days_{n}")
    ]


def today_routes(settings: Settings, now: datetime) -> list[int]:
    """The train routes (1 and 2) that are set and shown on ``now``'s day."""
    day = DAYS[now.astimezone(ZONE).weekday()]
    return [
        n
        for n in range(1, ROUTES + 1)
        if getattr(settings, f"train_from_{n}")
        and getattr(settings, f"train_to_{n}")
        and day in getattr(settings, f"train_days_{n}")
    ]


def _anything_set(settings: Settings) -> bool:
    stops = any(getattr(settings, f"stop_{n}") for n in range(1, STOPS + 1))
    routes = any(
        getattr(settings, f"train_from_{n}") and getattr(settings, f"train_to_{n}")
        for n in range(1, ROUTES + 1)
    )
    return stops or routes


def _now() -> datetime:
    """The time now in the Netherlands (replaced in tests)."""
    return datetime.now(ZONE)


def fetch(context: Context):
    settings = context.settings
    if not _anything_set(settings):
        raise SettingsMissing("nl_openbaar_vervoer needs a stop (stop_1) or a train route")
    now = _now()
    stops, routes = today_stops(settings, now), today_routes(settings, now)
    if context.layout == "next":  # it shows only the first: don't ask for, or alert on, more
        stops, routes = stops[:1], routes[:1] if not stops else []
    if not stops and not routes:
        return NOTHING
    found, times, errors = [], [], []
    if stops:
        _stop_sections(context, stops, now, found, times, errors)
    notices: tuple[Notice, ...] = ()
    if routes:
        notices = _route_sections(context, routes, now, found, times, errors)
    if errors and not times:
        raise errors[0]  # no source answered: nothing to show
    board = Board(tuple(found), now, min(times, default=now), notices)
    if settings.alert_on_disruption and any(n.real for n in notices):
        return alert(board)
    return ready(board)


def _latest(context, path, wanted: set[str], now, download, reuse=QUICKEST) -> Saved:
    """The newest answer for ``wanted``: the saved one when it is younger than ``reuse``,
    else a new one from ``download()`` (saved), else the saved one when it is less than
    :data:`OLDEST` old."""
    saved = departures.load(path)
    if saved and wanted <= saved.asked and timedelta(0) <= now - saved.fetched < reuse:
        return saved  # updated a moment ago
    try:
        latest = download()
    except (webrequest.WebError, AnswerError) as error:
        if saved is None or now - saved.fetched > OLDEST:
            raise
        log.warning("%s, showing the saved departures", error)
        return saved
    _save(context, path, departures.save(latest))
    return latest


def _stop_sections(context, wanted, now, found, times, errors) -> None:
    settings = context.settings
    codes = sorted({getattr(settings, f"stop_{n}") for n in wanted})
    try:
        latest = _latest(
            context,
            context.storage / SAVED,
            set(codes),
            now,
            lambda: Saved(
                departures.read(webrequest.get(f"{OVAPI}/tpc/{','.join(codes)}").json()),
                frozenset(codes),
                now,
            ),
        )
    except (webrequest.WebError, AnswerError) as error:
        log.warning("bus and tram times can't be updated: %s", error)
        errors.append(error)
        latest = Saved({}, frozenset(), now)
    else:
        times.append(latest.fetched)
    for n in wanted:
        code = getattr(settings, f"stop_{n}")
        stop = latest.stops.get(code)
        title = getattr(settings, f"name_{n}").strip() or (stop.name if stop else code)
        walk = getattr(settings, f"walk_{n}")
        if stop is None:
            if code in latest.asked:
                problem = "Stop not found: check its code"
            else:
                problem = "Not updated: OVapi can't be reached" if errors else "No saved times yet"
            found.append(Section(title, walk, (), problem))
            continue
        shown = departures.shown(
            stop, lines_of(getattr(settings, f"lines_{n}")), now, settings.ahead
        )
        found.append(Section(title, walk, tuple(shown)))


def _route_sections(context, wanted, now, found, times, errors) -> tuple[Notice, ...]:
    settings = context.settings
    key = settings.ns_key.get_secret_value().strip()
    notices: list[Notice] = []
    for n in wanted:
        origin, destination = (
            getattr(settings, f"train_from_{n}"),
            getattr(settings, f"train_to_{n}"),
        )
        walk = getattr(settings, f"train_walk_{n}")
        title, short = f"{origin} → {destination}", f"to {destination}"
        if not key:
            found.append(Section(title, walk, (), "Trains need an NS key (ns_key)", short))
            continue
        changes = getattr(settings, f"train_changes_{n}")
        code = f"{origin}-{destination}"
        try:
            latest = _latest(
                context,
                context.storage / f"trains_{code}{'_changes' if changes else ''}.json",
                {code},
                now,
                lambda o=origin, d=destination, c=changes: ns.route_saved(
                    _trips(key, o, d, c, now, settings.ahead), now
                ),
                reuse=ns.TRIPS_EVERY,
            )
        except (webrequest.WebError, AnswerError) as error:
            log.warning("train times %s can't be updated: %s", title, error)
            # webrequest's messages name the answer, e.g. "... answered 401 Unauthorized".
            text = str(error)
            if " 401 " in text or " 403 " in text:
                problem = "NS key not accepted"  # the user can fix this: show it
            else:
                errors.append(error)
                busy = " 429 " in text
                problem = (
                    "NS: too many requests today" if busy else "Not updated: NS can't be reached"
                )
            found.append(Section(title, walk, (), problem, short))
            continue
        times.append(latest.fetched)
        route = latest.stops[code]
        shown = departures.shown(route, (), now, settings.ahead)
        # route.name is "Rotterdam Centraal → Den Haag Centraal": too long for a row.
        short = "to " + route.name.rpartition(" → ")[2]
        found.append(Section(route.name, walk, tuple(shown), short=short))
        notices += [
            x for x in _disruptions(context, origin, destination, key, now) if x not in notices
        ]
    return tuple(notices)


def _trips(key, origin, destination, changes, now, ahead) -> departures.Stop:
    """The trains of a route, from 5 minutes ago to ``ahead`` minutes ahead. NS sends 5 trips
    per request; when they end too soon, it is asked once more from the last one on."""
    start = now - departures.SHOWN_AFTER
    answer = webrequest.get(ns.trips_url(origin, destination, start), headers=ns.headers(key))
    route, last = ns.read_trips(answer.json(), origin, destination, changes)
    if last is not None and last < now + timedelta(minutes=ahead):
        url = ns.trips_url(origin, destination, last + timedelta(minutes=1))
        try:
            more, _ = ns.read_trips(
                webrequest.get(url, headers=ns.headers(key)).json(), origin, destination, changes
            )
        except (webrequest.WebError, AnswerError) as error:
            log.warning("more train times can't be fetched, showing the first ones: %s", error)
            return route
        seen = {(d.line, d.planned) for d in route.departures}
        extra = tuple(d for d in more.departures if (d.line, d.planned) not in seen)
        route = departures.Stop(route.code, route.name, route.departures + extra)
    return route


def _disruptions(context, origin, destination, key, now) -> tuple[Notice, ...]:
    """The disruptions on a route, asked for at most every :data:`ns.DISRUPTIONS_EVERY`. When
    NS can't be reached they are left out: the train times matter more."""
    path = context.storage / f"disruptions_{origin}-{destination}.json"
    saved = ns.load_notices(path)
    if saved and timedelta(0) <= now - saved[1] < ns.DISRUPTIONS_EVERY:
        return saved[0]
    try:
        answer = webrequest.get(ns.disruptions_url(origin), headers=ns.headers(key))
        notices = ns.read_disruptions(answer.json(), origin, destination)
    except (webrequest.WebError, AnswerError) as error:
        log.warning("NS disruptions can't be updated: %s", error)
        return saved[0] if saved and now - saved[1] <= OLDEST else ()
    _save(context, path, ns.save_notices(notices, now))
    return notices


def _save(context: Context, path, data: bytes) -> None:
    if context.low_disk and not path.exists():
        return  # little free space: don't add a new file (replacing one is fine)
    try:
        write_atomic(path, data)
    except OSError as error:
        log.warning("can't save the departures, showing them anyway: %s", error)


# --- Drawing ---------------------------------------------------------------------------------


def gone(departure: Departure, now: datetime) -> bool:
    """It left, or its time has passed."""
    return departure.left or departure.expected < now


def note(departure: Departure, walk: int, now: datetime) -> str:
    """What a row says after the destination: "cancelled", "left", or with a walking time
    "leave in 3 min", "leave now" or "too late"."""
    if departure.cancelled:
        return "cancelled"
    if gone(departure, now):  # even if OVapi doesn't say so yet
        return "left"
    if not walk:
        return ""
    minutes = math.floor((departure.expected - timedelta(minutes=walk) - now).total_seconds() / 60)
    if minutes < 0:
        return "too late"
    return "leave now" if minutes == 0 else f"leave in {minutes} min"


def draw(board: Board, context: Context) -> dict:
    layout = PLUGIN.layout(context.layout, context.settings)
    wanted = layout.blocks
    ahead = context.settings.ahead
    if context.layout == "by_time":
        values = _draw_by_time(board, wanted, ahead)
    elif context.layout == "next":
        values = _draw_next(board, wanted, ahead)
    else:
        values = _draw_sections(board, wanted, ahead)
    if "notice" in wanted and board.notices:
        values["notice"] = "; ".join(
            ("Disruption: " if n.real else "Works: ") + n.title for n in board.notices
        )
    if board.fetched < board.now - timedelta(minutes=5):
        values["footer"] = f"Not updated since {board.fetched.astimezone(ZONE):%H:%M}"
    else:
        values["footer"] = f"Updated {board.fetched.astimezone(ZONE):%H:%M}"
    tracks = [name for name, value in values.items() if name.startswith("track_") and value]
    if tracks:
        prepared = layout.prepare(context.width, context.height, context.mode)
        for name in tracks:
            values[name] = sign(values[name], prepared.content_size(name))
    return {name: value for name, value in values.items() if name in wanted}


def sign(track: str, area: tuple[int, int]) -> Image.Image:
    """The platform number in a box, as on NS's signs, ``size`` pixels large (the box a
    little lower than the row, so the boxes of rows after each other don't touch). Drawn in
    black and white only, without smoothed edges, so no screen turns it into dots."""
    width, height = area
    picture = Image.new("L", (max(1, width), max(1, height)), 255)
    pen = ImageDraw.Draw(picture)
    pen.fontmode = "1"
    margin = round(height * 0.06)
    line = max(1, round(height / 16))
    # About as wide as high, as NS's signs; wider only when the number needs it.
    box = min(width, round(height * 1.25))
    left = (width - box) // 2
    pen.rectangle((left, margin, left + box - 1, height - 1 - margin), outline=0, width=line)
    size = max(4, round((height - 2 * margin - 2 * line) * 0.85))
    font = ImageFont.truetype(fonts.LATO_BOLD, size)
    while size > 4 and pen.textlength(track, font=font) > box - 4 * line:
        size -= 1
        font = ImageFont.truetype(fonts.LATO_BOLD, size)
    pen.text((width / 2, height / 2), track, font=font, fill=0, anchor="mm")
    return picture


def _fill_row(values: dict, at: str, d: Departure, walk: int, now: datetime, wanted) -> None:
    """The blocks ``time_<at>``, ``delay_<at>``, ... of one departure row. A train's
    platform goes in its box (``track_<at>``), or before the station in a row without one."""
    values[f"time_{at}"] = f"{d.expected.astimezone(ZONE):%H:%M}"
    values[f"delay_{at}"] = f"+{d.delay}" if d.delay > 0 else ""
    values[f"line_{at}"] = d.line
    values[f"dest_{at}"] = d.destination
    if f"track_{at}" in wanted:
        if d.track:
            values[f"track_{at}"] = d.track
    elif d.track:
        values[f"dest_{at}"] = f"[{d.track}] {d.destination}"
    values[f"note_{at}"] = note(d, walk, now)


def _heading(values: dict, s: int, section: Section) -> None:
    values[f"head_{s}"] = section.title
    values[f"walk_{s}"] = f"{section.walk} min walk" if section.walk else ""


def _draw_sections(board: Board, wanted, ahead: int) -> dict:
    values = {}
    for s, section in enumerate(board.sections):
        if f"head_{s}" not in wanted:
            break  # more stops today than the layout has room for
        _heading(values, s, section)
        rows = sum(1 for name in wanted if name.startswith(f"dest_{s}_"))
        shown = section.departures
        if rows <= 2:  # little room: only what can still be caught
            shown = tuple(d for d in shown if not gone(d, board.now))
        if section.problem:
            values[f"dest_{s}_0"] = section.problem
        elif not shown:
            values[f"dest_{s}_0"] = f"No departures in the next {ahead} min"
        for i, d in enumerate(shown[:rows]):
            _fill_row(values, f"{s}_{i}", d, section.walk, board.now, wanted)
    return values


def _draw_by_time(board: Board, wanted, ahead: int) -> dict:
    """Problems first (so they are seen), then the departures that haven't left, soonest
    first. Those that left are left out: from several stops they would fill the list."""
    values = {}
    rows = sum(1 for name in wanted if name.startswith("dest_"))
    problems = [s for s in board.sections if s.problem]
    for i, section in enumerate(problems[:rows]):
        values[f"stop_{i}"] = section.title
        values[f"dest_{i}"] = section.problem
    waiting = sorted(
        (
            (d, section)
            for section in board.sections
            for d in section.departures
            if not gone(d, board.now)
        ),
        key=lambda pair: pair[0].expected,
    )
    first = len(problems)
    if not waiting and first < rows:
        values[f"dest_{first}"] = f"No departures in the next {ahead} min"
    for i, (d, section) in enumerate(waiting[: max(0, rows - first)], start=first):
        _fill_row(values, str(i), d, section.walk, board.now, wanted)
        values[f"stop_{i}"] = section.short or section.title
    return values


def _draw_next(board: Board, wanted, ahead: int) -> dict:
    """The first stop: the next departure that can still be caught large, the ones after
    it in small rows."""
    if not board.sections:
        return {}
    section = board.sections[0]
    values = {}
    _heading(values, 0, section)
    if section.problem:
        values["next_dest"] = section.problem
        return values
    catchable = [
        d
        for d in section.departures
        if note(d, section.walk, board.now) not in ("cancelled", "left", "too late")
    ]
    if not catchable:
        values["next_dest"] = f"No departures in the next {ahead} min"
        return values
    first = catchable[0]
    values["next_dest"] = f"{first.line}  {first.destination}"
    text = note(first, section.walk, board.now)
    if not text:  # no walking time: when it leaves
        minutes = math.floor((first.expected - board.now).total_seconds() / 60)
        text = "leaves now" if minutes <= 0 else f"leaves in {minutes} min"
    values["next_note"] = text[0].upper() + text[1:]
    late = f" (+{first.delay})" if first.delay > 0 else ""
    platform = f" · spoor {first.track}" if first.track else ""
    values["next_time"] = f"{first.expected.astimezone(ZONE):%H:%M}{late}{platform}"
    rows = sum(1 for name in wanted if name.startswith("dest_0_"))
    after = section.departures[section.departures.index(first) + 1 :]
    later = [d for d in after if not gone(d, board.now)]
    for i, d in enumerate(later[:rows]):
        _fill_row(values, f"0_{i}", d, section.walk, board.now, wanted)
    return values


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
    trains = (
        at("IC", "Amsterdam Centraal", 6, delay=2, track="11"),
        at("SPR", "Den Haag Centraal", 13, track="12"),
        at("IC", "Amsterdam Centraal · was 11", 21, track="9"),
        at("IC", "Amsterdam Centraal", 36, track="11"),
    )
    return Board(
        (
            Section("Centraal perron A", 6, platform_a),
            Section("Centraal perron B", 6, platform_b),
            Section(
                "Rotterdam Centraal → Den Haag Centraal", 6, trains, short="to Den Haag Centraal"
            ),
        ),
        now,
        now,
        (Notice("Rotterdam - Den Haag: fewer trains in the evening", "MAINTENANCE"),),
    )


PLUGIN = Plugin(
    type="nl_openbaar_vervoer",
    title="Dutch public transport",
    network="internet",
    description="When the next buses, trams and trains leave in the Netherlands (up to four "
    "stops and two train routes), and when to leave the house to catch them. Live times from "
    "OVapi and NS.",
    settings=Settings,
    layouts=LAYOUTS,
    layout_titles={
        "sections": "A heading per stop or route",
        "by_time": "One list sorted by time",
        "next": "First stop, next departure large",
    },
    fetch=fetch,
    draw=draw,
    sample=_sample(),
    refresh=120,
)
