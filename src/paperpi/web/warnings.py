"""The Warnings tab: what needs attention now, and the recent warnings and errors.

"Needs attention now" is built from the scheduler's :class:`~paperpi.scheduler.Summary`
and the config file's plugin blocks: a config file PaperPi could not use, a screen that
does not answer, and the plugins whose card on the home page says they have a problem.
The menu shows how many there are. "Recent warnings and errors" are the newest log lines
of level WARNING and up (see :mod:`paperpi.logbook`), as they are in the log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlencode

from ..logbook import Line, Logbook
from ..scheduler import Summary
from .home import plugin_status, screen_problem
from .plugins import Row

#: The filter of the recent list: its value in the address, its label, and the levels.
FILTERS = (
    ("all", "All", ("WARNING", "ERROR", "CRITICAL")),
    ("errors", "✕ Errors", ("ERROR", "CRITICAL")),
    ("warnings", "⚠ Warnings", ("WARNING",)),
)

#: At most this many recent warnings and errors are listed.
RECENT = 100

#: Level -> (symbol, text, style) of the chip in the recent list.
LEVELS = {
    "WARNING": ("⚠", "Warning", "warn"),
    "ERROR": ("✕", "Error", "bad"),
    "CRITICAL": ("✕", "Crash", "bad"),
}


@dataclass(frozen=True)
class Item:
    """One thing that needs attention now."""

    style: str
    """"bad" (PaperPi can't do its work) or "warn" (one plugin)."""
    symbol: str
    title: str
    text: str
    lines: tuple[str, ...] = ()
    """The config file's mistakes, each shown as it is."""
    again: str | None = None
    """A Try again now button: the plugin's ID, or "" for the screen."""
    settings: str = ""
    """The address of the plugin's settings page."""
    reload: bool = False
    """A Load the file again button."""


@dataclass(frozen=True)
class Entry:
    line: Line
    first: str
    """The message's first line."""
    more: str
    """The lines after it (a traceback), shown folded."""

    @property
    def chip(self) -> tuple[str, str, str]:
        return LEVELS.get(self.line.level, LEVELS["ERROR"])


@dataclass(frozen=True)
class Day:
    label: str
    entries: tuple[Entry, ...]


def needs_attention(
    summary: Summary | None, rows: list[Row], file_problems: list[str], now: datetime
) -> list[Item]:
    """What needs attention now, the most important first. ``summary`` is ``None`` when the
    scheduler does not run (then only the config file is looked at)."""
    items = []
    mistakes = summary.config_errors if summary is not None else ()
    if mistakes or file_problems:
        items.append(
            Item(
                "bad",
                "✕",
                "The config file has a mistake",
                "PaperPi can't use the file and keeps running with the settings it had. "
                "Fix the file, then load it again.",
                lines=tuple(dict.fromkeys(mistakes or file_problems)),
                reload=summary is not None,
            )
        )
    if problem := screen_problem(summary):
        items.append(Item("bad", "✕", "The screen is not answering", problem, again=""))
    plugins = {p.id: p for p in summary.plugins} if summary is not None else {}
    for row in rows:
        status, note = plugin_status(row, plugins.get(row.id), summary is not None, now)
        settings = f"/plugins/{row.index}/settings?{urlencode({'id': row.id})}" if row.id else ""
        if status == "paused":
            title = f"{row.name}: paused due to errors"
            items.append(Item("warn", "⏸", title, note, again=row.id, settings=settings))
        elif status == "needs_settings":
            title = f"{row.name}: Configuration Required"
            items.append(Item("warn", "!", title, note, settings=settings))
        elif status == "errors":
            title = f"{row.name}: not used, has errors"
            items.append(Item("warn", "✕", title, note, settings=settings))
    return items


def filter_of(text: str | None) -> str:
    """A filter from the address; an unknown one is "all"."""
    return text if text in {value for value, _, _ in FILTERS} else "all"


def recent(book: Logbook, shown: str, today: date) -> tuple[Day, ...]:
    """The newest :data:`RECENT` warnings and errors of filter ``shown``, newest first,
    by day."""
    levels = next(found for value, _, found in FILTERS if value == shown)
    lines = [line for line in book.lines() if line.level in levels][-RECENT:]
    days: dict[str, list[Entry]] = {}
    for line in reversed(lines):
        first, _, more = line.text.partition("\n")
        days.setdefault(_day(line.time.date(), today), []).append(Entry(line, first, more))
    return tuple(Day(label, tuple(entries)) for label, entries in days.items())


def _day(day: date, today: date) -> str:
    gone = (today - day).days
    if gone == 0:
        return "Today"
    if gone == 1:
        return "Yesterday"
    return f"{day:%a} {day.day} {day:%b}" + ("" if day.year == today.year else f" {day.year}")
