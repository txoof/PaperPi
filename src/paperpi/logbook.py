"""PaperPi's own log: the last lines in memory, and the important ones in a small file.

The reasons are in ``docs/history/decisions/web-interface.md`` ("Warnings page") and
``docs/history/decisions/errors-and-time-limits.md`` ("Logs"). In short:

- ``paperpi run`` calls :func:`start`. From then on, every log line of level INFO and up
  (DEBUG too with ``--verbose``) is kept in memory: the last :data:`~paperpi.limits.LOG_LINES`.
  The web interface shows them on its Full log page.
- Warnings, errors, and lines logged with ``extra=KEEP`` (start, stop, the hourly health
  line) also go to the file :data:`FILE_NAME` in the state folder, so they survive a restart
  of the Pi (Raspberry Pi OS keeps the system log in memory only). When the file reaches
  :data:`~paperpi.limits.LOG_FILE_BYTES` it becomes ``paperpi.log.1`` (replacing an older
  one), so both together stay under about 2 MB: a few kilobytes of SD card writes a day.
- The lines of a message after the first (a traceback) are written indented by four spaces,
  so the file can be read back one entry at a time. At the start, the entries already in the
  file are read back, so the Full log also shows what happened before a restart.
- A crash (an exception nobody catches, in any thread) is logged as CRITICAL with its
  traceback, so its details are in the file too.
- The system log (what PaperPi writes to stderr) gets what it got before: warnings and
  errors (everything with ``--verbose``), plus the ``KEEP`` lines.

Passwords and secret settings are never logged (plugin processes replace them with
``****``, see :mod:`paperpi.runner`).
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import limits

#: The log file in the state folder; the one before it gets ``.1`` added.
FILE_NAME = "paperpi.log"

#: ``log.info(..., extra=KEEP)``: also write this line to the file, and to the system log.
KEEP = {"keep": True}

#: The levels of the Full log's filter, from the least to the most important.
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_TIME = "%Y-%m-%d %H:%M:%S"
_ENTRY = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) ([A-Z]+) (\S+): (.*)")
_MORE = "    "


@dataclass(frozen=True)
class Line:
    """One log entry."""

    number: int
    """Counts up from 1 at each start; 0 for entries read from the file (logged earlier)."""
    time: datetime
    level: str
    """The level's name: one of :data:`LEVELS`."""
    source: str
    """The name of the logger, e.g. ``paperpi.scheduler``."""
    text: str
    """The message, with the traceback (if any) on the lines after it."""

    @property
    def earlier(self) -> bool:
        """Logged before this start of PaperPi (read back from the file)."""
        return self.number == 0

    def as_text(self) -> str:
        """The entry as it is in the file."""
        first, *more = self.text.split("\n")
        head = f"{self.time.strftime(_TIME)} {self.level} {self.source}: {first}"
        return "\n".join([head, *(_MORE + line for line in more)])


class Logbook:
    """The kept log lines, in memory and in ``folder``/:data:`FILE_NAME` (no file without
    ``folder``). Safe to use from every thread."""

    def __init__(
        self,
        folder: Path | None,
        *,
        lines: int = limits.LOG_LINES,
        file_bytes: int = limits.LOG_FILE_BYTES,
    ) -> None:
        self.path = folder / FILE_NAME if folder is not None else None
        self._file_bytes = file_bytes
        self._earlier = read(self.path)[-lines:] if self.path is not None else []
        self._lines: deque[Line] = deque(maxlen=lines)
        self._number = 0
        self._lock = threading.Lock()
        self._file = None
        self._file_failed = False
        self.handler = _Handler(self)
        self._filtered: list[tuple[logging.Handler, logging.Filter]] = []
        self._level = logging.WARNING
        self._hook = threading.__excepthook__

    def lines(self, after: int | None = None) -> list[Line]:
        """The entries from the file, then the ones kept in memory, oldest first. With
        ``after``, only the ones in memory with a :attr:`Line.number` above it."""
        with self._lock:
            if after is None:
                return self._earlier + list(self._lines)
            return [line for line in self._lines if line.number > after]

    def add(self, record: logging.LogRecord, text: str) -> None:
        when = datetime.fromtimestamp(record.created)
        if len(text) > limits.LOG_LINE_CHARS:
            left_out = len(text) - limits.LOG_LINE_CHARS
            text = f"{text[: limits.LOG_LINE_CHARS]} … ({left_out} more characters left out)"
        with self._lock:
            self._number += 1
            line = Line(self._number, when, level_name(record.levelno), record.name, text)
            self._lines.append(line)
            if record.levelno >= logging.WARNING or getattr(record, "keep", False):
                self._write(line)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    def _write(self, line: Line) -> None:
        """Add ``line`` to the file. Never raises: the first failure is reported once on
        stderr (logging it here would come back to this method)."""
        if self.path is None:
            return
        try:
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
                fd = os.open(self.path, flags, 0o600)
                os.fchmod(fd, 0o600)  # also when the file was there already
                self._file = open(fd, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
            self._file.write(line.as_text() + "\n")
            if self._file.tell() >= self._file_bytes:
                self._file.close()
                self._file = None
                os.replace(self.path, self.path.with_name(FILE_NAME + ".1"))
        except OSError as error:
            if self._file is not None:
                self._file.close()
                self._file = None
            if not self._file_failed:
                print(f"paperpi: can't write the log file {self.path}: {error}", file=sys.stderr)
            self._file_failed = True
        else:
            self._file_failed = False


def level_name(level: int) -> str:
    """The name of ``level``, or of the standard level below it (a library's own level 25
    counts as INFO), so every line has one of :data:`LEVELS`."""
    names = [name for name in LEVELS if logging.getLevelName(name) <= level]
    return names[-1] if names else LEVELS[0]


class _Handler(logging.Handler):
    def __init__(self, book: Logbook) -> None:
        super().__init__()
        self.book = book
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.book.add(record, self.format(record))
        except Exception:  # noqa: BLE001 - a log line must never break PaperPi
            self.handleError(record)


class _SystemLog(logging.Filter):
    """Lets through what the system log got before :func:`start` lowered the level, plus the
    ``KEEP`` lines."""

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.level or getattr(record, "keep", False)


def read(path: Path) -> list[Line]:
    """The entries in ``path`` and the file before it (``.1``), oldest first. Lines that
    can't be read are left out; a missing file has none. Of a file larger than
    :data:`~paperpi.limits.LOG_FILE_BYTES`, only the end is read."""
    found: list[Line] = []
    for part in (path.with_name(path.name + ".1"), path):
        try:
            with part.open("rb") as file:
                size = file.seek(0, os.SEEK_END)
                file.seek(max(0, size - limits.LOG_FILE_BYTES))
                if size > limits.LOG_FILE_BYTES:
                    file.readline()  # the row the cut landed in
                text = file.read().decode("utf-8", "replace")
        except OSError:
            continue
        # Only "\n" ends a line, as in as_text: a "\r" in a message can't start a new entry.
        for row in text.split("\n"):
            if row.startswith(_MORE) and found:
                last = found[-1]
                found[-1] = Line(0, last.time, last.level, last.source, last.text + "\n" + row[4:])
            elif match := _ENTRY.fullmatch(row):
                when, level, source, message = match.groups()
                try:
                    time = datetime.strptime(when, _TIME)
                except ValueError:
                    continue
                if level in LEVELS:
                    found.append(Line(0, time, level, source, message))
    return found


def start(folder: Path | None, *, verbose: bool = False) -> Logbook:
    """Keep the log lines from now on (see the top of this module), with the file in
    ``folder``. :func:`stop` undoes it."""
    book = Logbook(folder)
    root = logging.getLogger()
    for handler in root.handlers:
        book._filtered.append((handler, _SystemLog(root.getEffectiveLevel())))
        handler.addFilter(book._filtered[-1][1])
    book._level = root.level
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(book.handler)
    book._hook = threading.excepthook
    threading.excepthook = _thread_crashed
    return book


def stop(book: Logbook) -> None:
    """Stop keeping log lines in ``book``, and close its file."""
    root = logging.getLogger()
    root.removeHandler(book.handler)
    for handler, system_log in book._filtered:
        handler.removeFilter(system_log)
    root.setLevel(book._level)
    threading.excepthook = book._hook
    book.close()


def _thread_crashed(args: threading.ExceptHookArgs) -> None:
    """A crash in a thread (``paperpi run`` logs one in the main thread itself)."""
    if issubclass(args.exc_type, SystemExit):
        return
    name = args.thread.name if args.thread is not None else "?"
    logging.getLogger("paperpi").critical(
        "thread %s crashed",
        name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
