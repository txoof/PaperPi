"""What the home page shows: the picture on the screen now, and a card for each plugin.

The scheduler's :class:`~paperpi.scheduler.Summary` says what is on screen and how each
plugin is doing; the config file says which plugins there are, in which order (the file
can be ahead of the scheduler for a moment, until PaperPi has loaded it again). The page
asks for the screen part again every few seconds while it is open.

The pictures are sent as PNG files. Each one is made once, when the page first asks for
it, and its address holds a number that changes with the picture, so the browser keeps it
and doesn't fetch it again at every look.
"""

from __future__ import annotations

import hashlib
import io
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from PIL import Image

from ..scheduler import PluginSummary, Summary
from .pictures import Shown
from .plugins import Row, title_of

#: The built-in plugins that can be on screen, with the names the page shows for them.
BUILT_IN = {
    "built-in-splash": ("Splash Screen", "splash_screen"),
    "built-in-clock": ("Clock (no plugin is ready yet)", "basic_clock"),
    "built-in-default": ("PaperPi message", "default"),
}
#: Card pictures are made at most this wide or high (the screen picture keeps its size).
CARD_PICTURE = 640

#: Status -> (symbol, text, style). A status never relies on colour alone.
STATUS = {
    "on_screen": ("▶", "On screen now", "current"),
    "next": ("→", "Next", "next"),
    "rotation": ("↻", "In rotation", "rotation"),
    "on": ("↻", "On", "rotation"),
    "waiting": ("…", "Waiting", "quiet"),
    "dismissed": ("✓", "Dismissed", "quiet"),
    "paused": ("⏸", "Paused due to errors", "bad"),
    "errors": ("✕", "Not used: has errors", "bad"),
    "needs_settings": ("!", "Configuration Required", "config"),
    "off": ("○", "Off", "quiet"),
    "unknown": ("?", "Unknown", "quiet"),
}


class Controls(Protocol):
    """What the home page asks of the scheduler (see :mod:`paperpi.scheduler`)."""

    summary: Summary

    def show_now(self, plugin_id: str) -> None: ...
    def skip(self) -> None: ...
    def refresh(self) -> None: ...
    def try_again(self, plugin_id: str | None = None) -> None: ...
    def dismiss(self, plugin_id: str) -> None: ...
    def reload(self) -> None: ...


@dataclass(frozen=True)
class Card:
    """One plugin on the home page."""

    row: Row
    number: int
    """Its place in the order, counted from 1."""
    status: str
    """A key of :data:`STATUS`."""
    note: str = ""
    """More about the status: when it shows, why it failed, ..."""
    picture: int | None = None
    """The number of its latest picture (see :class:`Snapshots`); ``None``: no picture."""
    example: Shown | None = None
    """Without a picture of its own: the Plugin Library's example."""
    paused: bool = False
    """Left out after failures: "Try again now" updates it at once."""

    @property
    def key(self) -> str:
        """A name for the card in the page, the same in every order."""
        return card_key(self.row)

    @property
    def symbol(self) -> str:
        return STATUS[self.status][0]

    @property
    def label(self) -> str:
        return STATUS[self.status][1]

    @property
    def style(self) -> str:
        return STATUS[self.status][2]

    @property
    def can_show(self) -> bool:
        """Show now can be asked for: the scheduler takes turns with it."""
        return self.status in ("next", "rotation", "waiting", "dismissed", "paused")


@dataclass(frozen=True)
class Now:
    """The screen part of the home page."""

    id: str | None = None
    """The ID of the plugin on screen; ``None`` before the first picture."""
    name: str = ""
    type: str = ""
    title: str = ""
    """The plain name of its plugin type, e.g. ``Weather``."""
    since: str = ""
    next: str = ""
    """The name of the plugin that comes next, and about when."""
    picture: int | None = None
    width: int = 0
    height: int = 0
    extra: bool = False
    alert: bool = False
    screen_problem: str = ""
    """Why the screen shows no new pictures; empty while it works."""


def card_key(row: Row) -> str:
    """A short name for ``row``'s card that stays the same when the order changes (plugin
    IDs may hold any character, so they are not used as they are)."""
    return "c" + hashlib.sha1(f"{row.index if not row.id else row.id}".encode()).hexdigest()[:10]


def cards(
    rows: list[Row],
    summary: Summary | None,
    snapshots: Snapshots,
    examples: dict[str, Shown | None],
    now: datetime,
) -> list[Card]:
    """A card for each row; ``summary`` is ``None`` when no scheduler runs (tests)."""
    found = {p.id: p for p in summary.plugins} if summary else {}
    made = []
    for row in rows:
        plugin = found.get(row.id) if row.id else None
        status, note = plugin_status(row, plugin, summary is not None, now)
        picture = None
        if plugin is not None and plugin.picture is not None:
            picture = snapshots.version(row.id, plugin.picture)
        made.append(
            Card(
                row,
                row.index + 1,
                status,
                note,
                picture=picture,
                example=examples.get(row.type) if picture is None else None,
                paused=status == "paused",
            )
        )
    return made


def plugin_status(
    row: Row, plugin: PluginSummary | None, running: bool, now: datetime
) -> tuple[str, str]:
    """A card's status (a key of :data:`STATUS`) and the note about it."""
    if not row.known:
        return "unknown", ""
    if row.errors:
        return "errors", "; ".join(row.errors)
    if row.missing:
        return "needs_settings", "Fill in: " + ", ".join(row.missing)
    if not row.enabled:
        return "off", ""
    if plugin is None or plugin.status in ("off", "needs_settings"):
        # Not loaded yet (a change of a moment ago), or no scheduler at all.
        return ("on", "PaperPi is loading the change.") if running else ("on", "")
    status = plugin.status
    if status in ("next", "rotation") and plugin.shows_at is not None:
        return status, "Shows " + in_about(plugin.shows_at, now)
    if status == "paused":
        note = plugin.error or "Its updates failed."
        if plugin.paused_until is not None:
            note += f" PaperPi tries again at {clock(plugin.paused_until)}."
        return status, note
    if status == "waiting" and plugin.error:
        return status, plugin.error
    return status, ""


def now_part(summary: Summary | None, rows: list[Row], snapshots: Snapshots, now: datetime) -> Now:
    """The screen part: what is on screen, since when, and what comes next."""
    if summary is None or summary.on_screen is None:
        return Now(screen_problem=screen_problem(summary))
    names = {row.id: (row.name, row.type) for row in rows if row.id}
    name, plugin_type = names.get(summary.on_screen) or BUILT_IN.get(
        summary.on_screen, (summary.on_screen, "")
    )
    upcoming = ""
    if summary.next is not None:
        upcoming = (names.get(summary.next) or BUILT_IN.get(summary.next, (summary.next, "")))[0]
        if summary.next_at is not None:
            upcoming += ", " + in_about(summary.next_at, now)
    picture = summary.picture
    return Now(
        summary.on_screen,
        name,
        plugin_type,
        title_of(plugin_type) if plugin_type else "",
        since=clock(summary.since) if summary.since else "",
        next=upcoming,
        picture=snapshots.version("", picture) if picture is not None else None,
        width=picture.width if picture is not None else 0,
        height=picture.height if picture is not None else 0,
        extra=summary.extra,
        alert=summary.alert,
        screen_problem=screen_problem(summary),
    )


def screen_problem(summary: Summary | None) -> str:
    """What the pages say about a screen that does not answer ("": it answers)."""
    if summary is None or summary.screen in (None, "ok"):
        return ""
    if summary.screen == "paused" and summary.screen_retry_at is not None:
        return (
            f"The screen is not answering. PaperPi tries again at {clock(summary.screen_retry_at)}."
        )
    return "The screen is not answering; PaperPi keeps trying."


def clock(moment: datetime) -> str:
    """``14:05``."""
    return moment.strftime("%H:%M")


def in_about(moment: datetime, now: datetime) -> str:
    """``in about 5 minutes``: when ``moment`` comes, as people say it."""
    minutes = round((moment - now).total_seconds() / 60)
    if minutes < 1:
        return "in less than a minute"
    if minutes < 90:
        return f"in about {minutes} minute{'' if minutes == 1 else 's'}"
    return f"in about {round(minutes / 60)} hours"


class Snapshots:
    """The PNG files of the pictures the home page shows: the screen's (name ``""``) and
    each plugin's latest (name = its ID). Safe to use from several threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._kept: dict[str, tuple[Image.Image, int, bytes | None]] = {}
        # Counted on from the start time, so a picture a browser kept from an earlier run
        # of PaperPi never has the same number as a new one.
        self._count = int(time.time())

    def version(self, name: str, image: Image.Image) -> int:
        """The number of ``image``, the picture shown as ``name`` now: the same while it
        doesn't change, a new one for a new picture."""
        with self._lock:
            kept = self._kept.get(name)
            if kept is not None and kept[0] is image:
                return kept[1]
            self._count += 1
            self._kept[name] = (image, self._count, None)
            return self._count

    def png(self, name: str) -> tuple[int, bytes] | None:
        """The number and PNG file of the picture shown as ``name`` now, or ``None``."""
        with self._lock:
            kept = self._kept.get(name)
        if kept is None:
            return None
        image, number, made = kept
        if made is None:
            made = _png(image, None if name == "" else CARD_PICTURE)
            with self._lock:
                if self._kept.get(name, (None,))[0] is image:
                    self._kept[name] = (image, number, made)
        return number, made

    def keep_only(self, names: set[str]) -> None:
        """Forget the pictures of plugins that are gone."""
        with self._lock:
            for name in [n for n in self._kept if n and n not in names]:
                del self._kept[name]


def _png(image: Image.Image, largest: int | None) -> bytes:
    if image.mode in ("1", "P"):  # else made smaller without smoothing
        image = image.convert("L" if image.mode == "1" else "RGB")
    if largest is not None and max(image.size) > largest:
        image = image.copy()
        image.thumbnail((largest, largest))
    if image.mode not in ("1", "L", "P", "RGB", "RGBA"):
        image = image.convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
