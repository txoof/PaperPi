"""Reading an iCal file into a short list of events, and saving that list.

An iCal file (``.ics``) holds every event of a calendar, back to the first one, with rules
for the events that repeat. Only the events of the next few days are kept: Google sends
about 1 MB for a calendar used for some years, and reading it takes a few seconds on a Pi.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo


class CalendarError(ValueError):
    """The downloaded file is not a calendar that can be read."""


@dataclass(frozen=True)
class Event:
    """One event, or one time of a repeating event. All-day events have dates, the others
    times with a time zone. ``end`` is not part of the event: for all-day events it is the
    day after the last day, as in iCal."""

    title: str
    start: datetime | date
    end: datetime | date
    calendar: int = 0
    """Which calendar setting it is from: 0 for ``calendar_1``. Not saved: it is set
    after reading."""

    @property
    def all_day(self) -> bool:
        return not isinstance(self.start, datetime)


def moment(value: datetime | date, zone: tzinfo | None = None) -> datetime:
    """A time to compare with: dates become midnight in ``zone`` (``None``: this
    computer's own time zone)."""
    if isinstance(value, datetime):
        return value
    return _zoned(datetime.combine(value, time()), zone)


def read(body: bytes, start: datetime, end: datetime, zone: tzinfo | None = None) -> list[Event]:
    """The events in an iCal file that are not over at ``start`` and begin before ``end``.
    Times without a time zone ("floating" times) are taken as times in ``zone``."""
    # Imported here: reading the plugin's settings must stay quick (see writing-plugins.md).
    import icalendar
    import recurring_ical_events

    try:
        calendar = icalendar.Calendar.from_ical(body)
        if calendar.name != "VCALENDAR":
            raise CalendarError("the address doesn't give a calendar file")
        # skip_bad_series: a repeating event with broken rules is left out, not the calendar.
        found = recurring_ical_events.of(calendar, skip_bad_series=True).between(start, end)
    except CalendarError:
        raise
    except ValueError as error:
        raise CalendarError(f"the calendar file can't be read ({type(error).__name__})") from None
    events = []
    for component in found:
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            continue
        first, last = component.start, component.end
        if isinstance(first, datetime):
            first, last = _zoned(first, zone), _zoned(last, zone)
        title = " ".join(str(component.get("SUMMARY", "")).split()) or "(no title)"
        events.append(Event(title, first, last))
    return events


def _zoned(t: datetime, zone: tzinfo | None) -> datetime:
    """``t`` with a time zone: ``zone``, or this computer's own when ``zone`` is ``None``."""
    if t.tzinfo is not None:
        return t
    return t.astimezone(zone) if zone is None else t.replace(tzinfo=zone)


# --- Saving ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Saved:
    events: list[Event]
    fetched: datetime


def save(events: list[Event], key: str, fetched: datetime) -> bytes:
    """The events as JSON. ``key`` says which calendar they are from (a hash of its
    address), so a saved list is not shown for another calendar."""
    rows = [
        {"title": e.title, "start": e.start.isoformat(), "end": e.end.isoformat()} for e in events
    ]
    return json.dumps({"key": key, "fetched": fetched.isoformat(), "events": rows}).encode()


def load(path, key: str) -> Saved | None:
    """The saved events of the calendar with ``key``, or ``None`` when there are none (or
    the file can't be read: then it is like a first run)."""
    try:
        data = json.loads(path.read_bytes())
        if data["key"] != key:
            return None
        events = [Event(r["title"], _when(r["start"]), _when(r["end"])) for r in data["events"]]
        return Saved(events, datetime.fromisoformat(data["fetched"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _when(text: str) -> datetime | date:
    return datetime.fromisoformat(text) if "T" in text else date.fromisoformat(text)


def upcoming(events, now: datetime, end: datetime, zone: tzinfo | None = None) -> list[Event]:
    """The events not over at ``now`` that begin before ``end``."""
    return [e for e in events if moment(e.end, zone) > now and moment(e.start, zone) < end]


def window_end(now: datetime, days: int, zone: tzinfo | None = None) -> datetime:
    """Midnight at the end of the last day shown: ``days`` 1 is today only."""
    local = now.astimezone(zone)
    return moment(local.date() + timedelta(days=days), zone)
