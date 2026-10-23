"""ical_calendar: the next events from one or more calendars, in one list.

The events come from each calendar's secret iCal address, for example Google Calendar's
"Secret address in iCal format". No login is needed: the address itself gives access, so
it is kept as a secret setting.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr

from ... import webrequest
from ...files import write_atomic
from ...plugin import Context, Plugin, PluginSettings, ready, setting
from . import events
from .events import CalendarError, Event
from .layouts import LAYOUTS

log = logging.getLogger(__name__)

CALENDARS = ("calendar_1", "calendar_2", "calendar_3")
#: The mark before each event's title, per calendar, when two or more are used.
MARKS = ("●", "○", "■")
#: Saved events are shown when a calendar can't be downloaded, until they are this old.
OLDEST = timedelta(days=1)
#: Calendars that have been used for many years can be large (Google: about 1 MB for some
#: years), so allow more than webrequest's usual 5 MB.
MAX_BYTES = 20_000_000

_HELP = (
    "Secret iCal address of a calendar, starting with https:// or webcal://. In Google "
    "Calendar: Settings, click the calendar, Integrate calendar, Secret address in iCal format"
)


class Settings(PluginSettings):
    calendar_1: SecretStr = setting(SecretStr(""), required=True, description=_HELP)
    calendar_2: SecretStr = Field(
        SecretStr(""), description="Address of a second calendar, shown in the same list"
    )
    calendar_3: SecretStr = Field(
        SecretStr(""), description="Address of a third calendar, shown in the same list"
    )
    name_1: str = Field(
        "", max_length=20, description="Short name of the first calendar, e.g. Personal"
    )
    name_2: str = Field("", max_length=20, description="Short name of the second, e.g. Family")
    name_3: str = Field("", max_length=20, description="Short name of the third, e.g. Work")
    days: int = Field(7, ge=1, le=31, description="How many days to show, starting today")
    hours: Literal[12, 24] = Field(24, description="12-hour (3:45 PM) or 24-hour (15:45) times")


@dataclass(frozen=True)
class Agenda:
    """What ``draw`` gets: the events of all calendars, the time they are shown at, when
    the oldest saved events used were downloaded (``None``: all are new), the time zone
    to show them in (``None``: this computer's own) and the name of each calendar setting
    (``None`` for one that is not used)."""

    events: tuple[Event, ...]
    now: datetime
    saved: datetime | None = None
    zone: str | None = None
    calendars: tuple[str | None, ...] = ()


class SettingsMissing(ValueError):
    pass


def address(name: str, secret: SecretStr) -> str:
    """The web address in a calendar setting. ``webcal://`` (used by Apple and Outlook)
    is the same address over https. The error never shows the address: it is a secret."""
    text = secret.get_secret_value().strip()
    if text.lower().startswith("webcal://"):
        text = "https://" + text[len("webcal://") :]
    if not text.lower().startswith(("https://", "http://")):
        raise ValueError(f"{name} is not a web address: it must start with https:// or webcal://")
    return text


def fetch(context: Context):
    settings = context.settings
    wanted = [n for n in CALENDARS if getattr(settings, n).get_secret_value().strip()]
    if not wanted:
        raise SettingsMissing("ical_calendar needs the address of a calendar in calendar_1")
    now = datetime.now().astimezone()
    end = events.window_end(now, settings.days)
    found: list[Event] = []
    oldest = None
    for name in wanted:
        slot = CALENDARS.index(name)
        url = address(name, getattr(settings, name))
        path = context.storage / f"{name}.json"
        key = hashlib.sha256(url.encode()).hexdigest()
        try:
            answer = webrequest.get(url, max_bytes=MAX_BYTES)
            # A day more than shown, so saved events still fill the list tomorrow.
            latest = events.read(answer.body, now, end + timedelta(days=1))
        except (webrequest.WebError, CalendarError) as error:
            saved = events.load(path, key)
            if saved is None or now - saved.fetched > OLDEST:
                raise
            log.warning("%s can't be downloaded, showing the saved events: %s", name, error)
            latest, oldest = saved.events, min(oldest or saved.fetched, saved.fetched)
        else:
            try:
                write_atomic(path, events.save(latest, key, now))
            except OSError as error:
                log.warning("can't save the events of %s, showing them anyway: %s", name, error)
        found.extend(replace(e, calendar=slot) for e in events.upcoming(latest, now, end))
    calendars = tuple(
        calendar_name(settings, i) if n in wanted else None for i, n in enumerate(CALENDARS)
    )
    return ready(Agenda(tuple(found), now, oldest, calendars=calendars))


def calendar_name(settings: Settings, slot: int) -> str:
    """The name shown for a calendar: its ``name_<n>`` setting, or "Calendar <n>"."""
    return getattr(settings, f"name_{slot + 1}").strip() or f"Calendar {slot + 1}"


# --- Drawing ---------------------------------------------------------------------------------


def clock(t: datetime, hours: int) -> str:
    if hours == 12:
        return f"{t.hour % 12 or 12}:{t:%M} {t:%p}"
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
    return (
        f"until {clock(end, hours)}" if end.date() == today else f"until {_short_day(end.date())}"
    )


def when_text(event: Event, day: date, today: date, time: str) -> str:
    """Day and time in one short text, for small screens: "18:45", "Thu 18:45", "Thu 1"."""
    if day == today:
        return "Today" if event.all_day else time
    return _short_day(day) if event.all_day else f"{_short_day(day)} {time}"


def draw(agenda: Agenda, context: Context) -> dict:
    settings = context.settings
    zone = ZoneInfo(agenda.zone) if agenda.zone else None
    local = (lambda t: t.astimezone(zone)) if zone else (lambda t: t.astimezone())
    today = local(agenda.now).date()
    end = events.window_end(agenda.now, settings.days, zone)

    def shown_day(e: Event) -> date:
        start = e.start if e.all_day else local(e.start).date()
        return max(start, today)

    def order(e: Event):
        # All-day events and events that started earlier come first on their day.
        first = e.all_day or shown_day(e) != (e.start if e.all_day else local(e.start).date())
        return (shown_day(e), not first, events.moment(e.start, zone), e.title)

    # Saved events, and the sample, may have ended since they were fetched.
    listed = sorted(events.upcoming(agenda.events, agenda.now, end, zone), key=order)
    wanted = PLUGIN.layout(context.layout, settings).blocks
    rows = sum(1 for name in wanted if name.startswith("title_"))
    used = [(i, n) for i, n in enumerate(agenda.calendars) if n is not None]
    marked = len(used) > 1
    corner = [f"{MARKS[i]} {n}" for i, n in used] if marked else []
    if agenda.saved:
        corner.append(f"Saved {clock(local(agenda.saved), settings.hours)}")
    values = {
        "today": f"{local(agenda.now):%A} {today.day} {local(agenda.now):%B}",
        "legend": "  ".join(corner),
    }
    if not listed:
        days = "today" if settings.days == 1 else f"the next {settings.days} days"
        values["title_0"] = f"Nothing planned for {days}"
    if len(listed) > rows:
        values[f"title_{rows - 1}"] = f"+ {len(listed) - rows + 1} more"
        listed = listed[: rows - 1]
    previous = None
    for i, event in enumerate(listed):
        day = shown_day(event)
        values[f"day_{i}"] = day_name(day, today) if day != previous else ""
        values[f"time_{i}"] = time_text(event, today, local, settings.hours)
        values[f"title_{i}"] = f"{MARKS[event.calendar]} {event.title}" if marked else event.title
        values[f"when_{i}"] = when_text(event, day, today, values[f"time_{i}"])
        previous = day
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
)
