"""ical_calendar: the next events from one or more calendars, in one list.

The events come from each calendar's secret iCal address, for example Google Calendar's
"Secret address in iCal format". No login is needed: the address itself gives access, so
it is kept as a secret setting.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from pydantic import Field, SecretStr

from ... import webrequest
from ...files import write_atomic
from ...plugin import Context, Plugin, PluginSettings, ready, setting
from . import events
from .events import CalendarError, Event
from .layouts import LAYOUTS

log = logging.getLogger(__name__)

CALENDARS = ("calendar_1", "calendar_2", "calendar_3")
#: The mark before each event's title, per calendar, when two or more are used: a filled
#: circle, an open circle and a filled square.
MARKS = ("dot", "ring", "square")
#: Saved events are shown when a calendar can't be downloaded, until they are this old.
OLDEST = timedelta(days=1)
#: Calendars that have been used for many years can be large (Google: about 1 MB for some
#: years), so allow more than webrequest's usual 5 MB. A Pi 4 needs about 50 seconds to read
#: 5 MB, so a larger file could never be read within the time limit.
MAX_BYTES = 8_000_000
#: Names of servers on the home network, the only ones allowed with http:// (not encrypted).
HOME_NAMES = (".local", ".lan", ".home.arpa", ".internal")


class Settings(PluginSettings):
    calendar_1: SecretStr = setting(
        SecretStr(""),
        required=True,
        group="Calendar 1",
        description="Secret iCal address of a calendar (starts with https:// or webcal://). "
        "The plugin's README shows where to find it in Google, Outlook and iCloud",
    )
    calendar_2: SecretStr = setting(
        SecretStr(""),
        group="Calendar 2",
        description="Secret iCal address of a second calendar (or leave empty)",
    )
    calendar_3: SecretStr = setting(
        SecretStr(""),
        group="Calendar 3",
        description="Secret iCal address of a third calendar (or leave empty)",
    )
    name_1: str = setting(
        "",
        group="Calendar 1",
        max_length=20,
        description="Short name of the first calendar, e.g. Personal",
    )
    name_2: str = setting(
        "", group="Calendar 2", max_length=20, description="Short name of the second, e.g. Family"
    )
    name_3: str = setting(
        "", group="Calendar 3", max_length=20, description="Short name of the third, e.g. Work"
    )
    days: int = Field(7, ge=1, le=31, description="How many days to show, starting today")
    hours: Literal[12, 24] = Field(24, description="12-hour (3:45 PM) or 24-hour (15:45) times")


@dataclass(frozen=True)
class Agenda:
    """What ``draw`` gets: the events of all calendars, the time they are shown at, the
    time zone to show them in (``None``: this computer's own), the name of each calendar
    setting (``None`` for one that is not used) and the calendars that could not be
    updated (0 for ``calendar_1``)."""

    events: tuple[Event, ...]
    now: datetime
    zone: str | None = None
    calendars: tuple[str | None, ...] = ()
    failed: tuple[int, ...] = ()


class SettingsMissing(ValueError):
    pass


class AddressError(ValueError):
    pass


def address(name: str, secret: SecretStr) -> str:
    """The web address in a calendar setting. ``webcal://`` (used by Apple and Outlook)
    is the same address over https. ``http://`` is not encrypted, so anyone on the way
    could read the secret address: it is only allowed for a server on the home network.
    The errors never show the address: it is a secret."""
    text = secret.get_secret_value().strip()
    if text.lower().startswith("webcal://"):
        text = "https://" + text[len("webcal://") :]
    if text.lower().startswith("http://"):
        try:
            host = urlsplit(text).hostname or ""
        except ValueError:
            host = ""
        if not _at_home(host):
            raise AddressError(
                f"{name} starts with http://, which is not encrypted: use https:// (http:// "
                "only works for a server on the home network)"
            )
    elif not text.lower().startswith("https://"):
        raise AddressError(f"{name} is not a web address: it must start with https:// or webcal://")
    return text


def _at_home(host: str) -> bool:
    """Whether a server name or number is on the home network: a name without a dot
    (``nas``), a home name (``nas.local``) or a private address (``192.168.1.5``)."""
    if not host:
        return False
    if "." not in host or host.endswith(HOME_NAMES):
        return True
    try:
        number = ipaddress.ip_address(host)
    except ValueError:
        return False
    return number.is_private or number.is_loopback


def saved_key(url: str, days: int) -> str:
    """Which address and number of days saved events are for. The days are part of it:
    after a change, saved events may cover too few days. A hash, so the secret address is
    not written in the file."""
    return hashlib.sha256(f"{days}\n{url}".encode()).hexdigest()


def _now() -> datetime:
    """The time now, with this computer's time zone (replaced in tests)."""
    return datetime.now().astimezone()


def fetch(context: Context):
    settings = context.settings
    wanted = [n for n in CALENDARS if getattr(settings, n).get_secret_value().strip()]
    if not wanted:
        raise SettingsMissing("ical_calendar needs the address of a calendar in calendar_1")
    now = _now()
    end = events.window_end(now, settings.days)
    found: list[Event] = []
    failed: list[int] = []
    problem = None
    for name in wanted:
        slot = CALENDARS.index(name)
        path = context.storage / f"{name}.json"
        try:
            url = address(name, getattr(settings, name))
            key = saved_key(url, settings.days)
            answer = webrequest.get(url, max_bytes=MAX_BYTES)
            # A day more than shown, so saved events still fill the list tomorrow.
            latest = events.read(answer.body, now, end + timedelta(days=1))
        except (webrequest.WebError, CalendarError, AddressError) as error:
            saved = None if isinstance(error, AddressError) else events.load(path, key)
            if saved is None or now - saved.fetched > OLDEST:
                # The other calendars are still shown; the update fails only when all fail.
                log.warning("%s can't be updated and has no saved events: %s", name, error)
                failed.append(slot)
                problem = problem or error
                continue
            log.warning("%s can't be downloaded, showing the saved events: %s", name, error)
            latest = saved.events
        else:
            _save(context, path, events.save(latest, key, now), name)
        found.extend(replace(e, calendar=slot) for e in events.upcoming(latest, now, end))
    if len(failed) == len(wanted):
        raise problem
    calendars = tuple(
        calendar_name(settings, i) if n in wanted else None for i, n in enumerate(CALENDARS)
    )
    return ready(Agenda(tuple(found), now, calendars=calendars, failed=tuple(failed)))


def _save(context: Context, path, data: bytes, name: str) -> None:
    if context.low_disk and not path.exists():
        return  # little free space: don't add a new file (replacing one is fine)
    try:
        write_atomic(path, data)
    except OSError as error:
        log.warning("can't save the events of %s, showing them anyway: %s", name, error)


def calendar_name(settings: Settings, slot: int) -> str:
    """The name shown for a calendar: its ``name_<n>`` setting, or "Calendar <n>"."""
    return getattr(settings, f"name_{slot + 1}").strip() or f"Calendar {slot + 1}"


# --- Drawing ---------------------------------------------------------------------------------


def clock(t: datetime, hours: int) -> str:
    if hours == 12:
        # Not %p: it depends on the system's language and can be empty.
        return f"{t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"
    return f"{t:%H:%M}"


def day_name(day: date, today: date) -> str:
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%a} {day.day} {day:%b}"


def _short_day(day: date) -> str:
    return f"{day:%a} {day.day}"


def time_text(event: Event, today: date, local, hours: int) -> str:
    """ "08:30", "all day", or for an event that started on an earlier day "until 10:00"
    or "until Sun 25"."""
    if event.all_day:
        last = max(event.end - timedelta(days=1), event.start)
        if last == event.start:
            return "all day"
        return "ends today" if last == today else f"until {_short_day(last)}"
    start, end = local(event.start), local(event.end)
    if start.date() >= today:
        return clock(start, hours)
    # An event that ends at midnight (00:00) ends on the day before.
    last = (end - timedelta(microseconds=1)).date() if end > start else end.date()
    if last != today:
        return f"until {_short_day(last)}"
    return f"until {clock(end, hours)}" if end.date() == today else "ends today"


def when_text(event: Event, day: date, today: date, time: str) -> str:
    """Day and time in one short text, for small screens: "18:45", "Thu 18:45", "Thu 1".
    12-hour times are shortened to "6:45p", so they fit too."""
    time = time.replace(" AM", "a").replace(" PM", "p")
    if day == today:
        return "Today" if event.all_day else time
    return _short_day(day) if event.all_day else f"{day:%a} {time}"


def mark(kind: str, width: int, height: int, size: int) -> Image.Image:
    """A calendar's mark, ``size`` pixels wide, in the middle of a picture of its block's
    size, so nothing is resized (see writing-plugins.md)."""
    image = Image.new("L", (max(width, 1), max(height, 1)), 255)
    size = max(min(size, width, height), 4)
    left, top = (width - size) // 2, (height - size) // 2
    box = (left, top, left + size - 1, top + size - 1)
    pen = ImageDraw.Draw(image)
    if kind == "dot":
        pen.ellipse(box, fill=0)
    elif kind == "ring":
        pen.ellipse(box, outline=0, width=max(size // 7, 2))
    else:
        inset = round(size * 0.08)  # a square looks larger than a circle of the same width
        pen.rectangle((box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset), fill=0)
    return image


def draw(agenda: Agenda, context: Context) -> dict:
    settings = context.settings
    zone = ZoneInfo(agenda.zone) if agenda.zone else None
    local = (lambda t: t.astimezone(zone)) if zone else (lambda t: t.astimezone())
    today = local(agenda.now).date()
    end = events.window_end(agenda.now, settings.days, zone)

    def start_day(e: Event) -> date:
        return e.start if e.all_day else local(e.start).date()

    def shown_day(e: Event) -> date:
        return max(start_day(e), today)

    def order(e: Event):
        # All-day events and events that started earlier come first on their day.
        early = e.all_day or shown_day(e) != start_day(e)
        return (shown_day(e), not early, events.moment(e.start, zone), e.title)

    # Saved events, and the sample, may have ended since they were fetched.
    listed = sorted(events.upcoming(agenda.events, agenda.now, end, zone), key=order)
    layout = PLUGIN.layout(context.layout, settings)
    wanted = layout.blocks
    rows = sum(1 for name in wanted if name.startswith("title_"))
    used = [(i, n) for i, n in enumerate(agenda.calendars) if n is not None]
    # Marks only with several calendars, and in layouts that have them.
    marked = len(used) > 1 and "mark_0" in wanted
    values = {"today": f"{local(agenda.now):%A} {today.day} {local(agenda.now):%B}"}
    if marked:
        # Every mark, in the rows and in the header, is 60 % of a row's mark block.
        prepared = layout.prepare(context.width, context.height, context.mode)
        blocks = {
            b: prepared.content_size(f"{b}_0") for b in ("mark", "key_mark") if f"{b}_0" in wanted
        }
        size = round(min(blocks["mark"]) * 0.6)
        marks = {
            (slot, b): mark(MARKS[slot], *wh, size) for slot, _ in used for b, wh in blocks.items()
        }
    if marked and "key_mark_0" in wanted:
        # Filled from the right, so the last one ends at the screen's edge.
        offset = sum(1 for n in wanted if n.startswith("key_mark_")) - len(used)
        for k, (slot, name) in enumerate(used, start=offset):
            values[f"key_mark_{k}"] = marks[slot, "key_mark"]
            values[f"key_name_{k}"] = name
    # The last rows say which calendars could not be updated; the events get the rest.
    notes = [(slot, f"{agenda.calendars[slot]}: not updated") for slot in agenda.failed]
    room = max(rows - len(notes), 0)
    shown, more = listed, 0
    if len(listed) > room:
        shown = listed[: room - 1] if room else []
        more = len(listed) - len(shown)
    previous = None
    for i, event in enumerate(shown):
        day = shown_day(event)
        values[f"day_{i}"] = day_name(day, today) if day != previous else ""
        values[f"time_{i}"] = time_text(event, today, local, settings.hours)
        values[f"title_{i}"] = event.title
        if marked:
            values[f"mark_{i}"] = marks[event.calendar, "mark"]
        values[f"when_{i}"] = when_text(event, day, today, values[f"time_{i}"])
        previous = day
    texts = []
    if not listed:
        days = "today" if settings.days == 1 else f"the next {settings.days} days"
        texts.append((None, f"Nothing planned for {days}"))
    if more and room:
        texts.append((None, f"+ {more} more"))
    for i, (slot, text) in enumerate(texts + notes, start=len(shown)):
        values[f"title_{i}"] = text
        if marked and slot is not None:
            values[f"mark_{i}"] = marks[slot, "mark"]
    return {name: value for name, value in values.items() if name in wanted}


def _sample() -> Agenda:
    """A made-up week in Berlin from two calendars, with all-day, repeating and multi-day
    events."""
    zone = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 9, 30, 9, 15, tzinfo=zone)

    def at(days, hour, minute=0, length=1.0):
        """Start and end, ``days`` after today."""
        start = datetime(2026, 9, 30, hour, minute, tzinfo=zone) + timedelta(days=days)
        return start, start + timedelta(hours=length)

    sample = [
        Event("School autumn break", date(2026, 9, 26), date(2026, 10, 5), calendar=1),
        Event("Compost bin out", *at(0, 7), calendar=1),
        Event("Dentist appointment with Anne", *at(0, 14, 30)),
        Event("Running club", *at(1, 18, 45, 1.5)),
        Event("Pay the rent", date(2026, 10, 1), date(2026, 10, 2), calendar=1),
        Event("Grandma's birthday", date(2026, 10, 3), date(2026, 10, 4), calendar=1),
        Event("Football match", *at(3, 10)),
        Event("Dinner with friends", *at(3, 19, 30, 3), calendar=1),
        Event("Running club", *at(4, 8, 30, 1.5)),
        Event("Window cleaner", *at(5, 9), calendar=1),
    ]
    return Agenda(tuple(sample), now, zone="Europe/Berlin", calendars=("Personal", "Family", None))


PLUGIN = Plugin(
    type="ical_calendar",
    title="Calendar",
    network="internet",
    description="The next events from one to three calendars (Google, Outlook, iCloud and "
    "others) in one list, using each calendar's secret iCal address. No login needed.",
    settings=Settings,
    layouts=LAYOUTS,
    layout_titles={"list": "Date and the next 8 events", "small": "Small: the next 3 events"},
    fetch=fetch,
    draw=draw,
    sample=_sample(),
    refresh=30 * 60,
    setup="First copy each calendar's secret iCal address from Google Calendar, Outlook.com "
    "or iCloud; the README shows where.",
)
