"""The Full log page: PaperPi's kept log lines (see :mod:`paperpi.logbook`), filtered by
level and by a search text."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from ..logbook import Line, Logbook

#: The level filter: its value in the address, its label, and the lowest level it shows.
FILTERS = (
    ("DEBUG", "Everything", logging.DEBUG),
    ("INFO", "Info and up", logging.INFO),
    ("WARNING", "Warnings and errors", logging.WARNING),
)
DEFAULT = "INFO"

#: At most this many lines are on the page (the newest that match); the download has all.
SHOWN = 1_000

#: Longest search text.
LONGEST_SEARCH = 100


@dataclass(frozen=True)
class Row:
    line: Line
    parts: tuple[tuple[str, bool], ...]
    """The text in parts, each with whether it matches the search (to be marked)."""
    started: bool = False
    """The first line of this start, right after lines from the file: the page marks it."""


@dataclass(frozen=True)
class Shown:
    rows: tuple[Row, ...]
    matching: int
    """How many lines match (more than are shown when there are over :data:`SHOWN`)."""
    total: int
    newest: int
    """The number of the newest line, so the page can ask for the lines after it."""

    @property
    def ends_earlier(self) -> bool:
        """The last line shown is from the file (logged before this start)."""
        return bool(self.rows) and self.rows[-1].line.earlier


def level_of(text: str | None) -> str:
    """A level filter from the address; an unknown one is the default."""
    return text if text in {value for value, _, _ in FILTERS} else DEFAULT


def show(
    book: Logbook, level: str, search: str, after: int | None = None, earlier: bool = False
) -> Shown:
    """The lines of ``book`` at ``level`` and up that contain ``search`` (any case), the
    newest :data:`SHOWN`. With ``after``, only the new ones after that line number;
    ``earlier`` says the page's last line is from the file, so the first new one is marked
    as the start."""
    lines = book.lines(after)
    # Taken from the lines themselves: a line logged meanwhile comes with the next request.
    newest = max(after or 0, lines[-1].number if lines else 0)
    lowest = next(number for value, _, number in FILTERS if value == level)
    search = search.strip()[:LONGEST_SEARCH]
    found = [
        line
        for line in lines
        if logging.getLevelName(line.level) >= lowest
        and (not search or search.casefold() in line.text.casefold())
    ]
    rows, before_earlier = [], earlier
    for line in found[-SHOWN:]:
        rows.append(Row(line, _parts(line.text, search), before_earlier and not line.earlier))
        before_earlier = line.earlier
    return Shown(tuple(rows), len(found), len(lines), newest)


def as_text(book: Logbook) -> str:
    """Every kept line, as in the log file, for Download log."""
    return "".join(line.as_text() + "\n" for line in book.lines())


def file_name(now: datetime) -> str:
    return f"paperpi-log-{now:%Y-%m-%d-%H%M}.txt"


def _parts(text: str, search: str) -> tuple[tuple[str, bool], ...]:
    if not search:
        return ((text, False),)
    parts = []
    folded, wanted, start = text.casefold(), search.casefold(), 0
    # casefold() can change the length of some letters (ß -> ss); then nothing is marked.
    if len(folded) != len(text):
        return ((text, False),)
    while (found := folded.find(wanted, start)) >= 0:
        parts += [(text[start:found], False), (text[found : found + len(wanted)], True)]
        start = found + len(wanted)
    parts.append((text[start:], False))
    return tuple(part for part in parts if part[0])
