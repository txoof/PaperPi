"""Setting helpers: a search a plugin offers on its settings page, such as finding a place's
latitude and longitude from its name (see ``docs/decisions/setting-helpers.md``).

A helper is a :class:`Helper` in the plugin's ``helpers``. A setting names it with
``setting(..., helper="<name>")`` and the settings page shows a search box under that
setting. The helper's ``find`` gets a :class:`Query` (the typed text and the form's settings)
and returns choices: a list of dictionaries, or ``{"choices": [...], "note": "..."}``. Each
choice is a dictionary whose keys are **kinds** that say what PaperPi does with the value:

- ``fill``: settings put into the form when the user presses Use (nothing is saved yet);
- ``show``: label and text, shown to help the user choose; the first one is the heading;
- ``link``: label and web address (``http`` or ``https``) the user can open.

``note`` is a message for the whole result. A kind PaperPi doesn't know is left out and
logged, so a plugin made for a newer PaperPi still works. :func:`clean` checks a result.
A helper runs in its own process with a time limit (:func:`paperpi.runner.run_helper`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from . import limits

if TYPE_CHECKING:
    from .plugin import PluginSettings

#: The kinds of a choice PaperPi knows; the others are left out (see the top).
KINDS = ("fill", "show", "link")
#: The kinds of web address a helper may link to.
WEB = ("http", "https")
#: The longest text PaperPi shows from a choice.
LONGEST_TEXT = 200


@dataclass(frozen=True)
class Query:
    """What a helper's ``find`` gets."""

    text: str
    """What the user typed, without spaces around it (``""`` for a helper with ``typed=False``)."""
    settings: PluginSettings
    """The settings in the form, checked as Save checks them. An empty secret field (an API
    key) gives the saved secret."""


@dataclass(frozen=True)
class Helper:
    """A search a plugin offers for one of its settings."""

    find: Callable[[Query], Sequence[Mapping[str, Any]] | Mapping[str, Any]]
    """Returns the choices (see the top). Raises :class:`HelperProblem` with a message for
    the user; any other error shows "The search failed" and goes to the log."""
    prompt: str
    """The text above the search box, e.g. "Place name, e.g. Berlin or Morrison, Colorado"."""
    button: str = "Search"
    typed: bool = True
    """False for a helper that needs no typed text (e.g. "Find servers"): only a button."""
    source: str = ""
    """Where the answers come from, shown under them, e.g. "Search by Open-Meteo". Say it
    when the typed text goes to an outside service."""
    source_link: str = ""
    """A web address for ``source``."""
    needs: tuple[str, ...] = ()
    """Settings that must be filled in before a search, e.g. an API key."""


class HelperProblem(Exception):
    """Raised by a helper's ``find`` to stop with a message for the user, such as "The API
    key was not accepted"."""


@dataclass(frozen=True)
class Choice:
    """One checked choice."""

    show: tuple[tuple[str, str], ...]
    """Label and text; the first is the heading."""
    fill: Mapping[str, Any]
    """Setting and value."""
    links: tuple[tuple[str, str], ...] = ()
    """Label and web address."""

    @property
    def heading(self) -> str:
        return self.show[0][1]


@dataclass(frozen=True)
class Found:
    """A checked result."""

    choices: tuple[Choice, ...]
    note: str = ""
    more: bool = False
    """The helper found more than :data:`~paperpi.limits.HELPER_CHOICES`; only those are kept."""
    left_out: tuple[str, ...] = ()
    """What was left out (kinds PaperPi doesn't know, links that are not ``http``), to log."""


def clean(result: Any, settings: Sequence[str]) -> Found:
    """Check what a helper's ``find`` returned. ``settings`` are the names a ``fill`` may
    use. Raises ``TypeError`` for a result that breaks the rules (a bug in the plugin)."""
    note: Any = ""
    left_out: list[str] = []
    if isinstance(result, Mapping):
        left_out += [f"result kind {k!r}" for k in result if k not in ("choices", "note")]
        note, result = result.get("note", ""), result.get("choices", ())
    if isinstance(result, str | bytes) or not isinstance(result, Sequence):
        raise TypeError("a helper returns a list of choices or {'choices': [...], 'note': ...}")
    if not isinstance(note, str):
        raise TypeError("a result's note must be text")
    choices = []
    for number, raw in enumerate(result[: limits.HELPER_CHOICES], 1):
        if not isinstance(raw, Mapping):
            raise TypeError(f"choice {number} is not a dictionary")
        left_out += [f"choice kind {k!r}" for k in raw if k not in KINDS]
        show = _pairs(raw.get("show", {}), f"choice {number}: show")
        if not show:
            raise TypeError(f"choice {number} has nothing to show")
        fill = raw.get("fill", {})
        if not isinstance(fill, Mapping):
            raise TypeError(f"choice {number}: fill must be a dictionary")
        unknown = [str(k) for k in fill if k not in settings]
        if unknown:
            raise TypeError(f"choice {number} fills settings it doesn't have: {', '.join(unknown)}")
        links = []
        for label, address in _pairs(raw.get("link", {}), f"choice {number}: link"):
            if urlsplit(address).scheme in WEB:
                links.append((label, address))
            else:
                left_out.append(f"link {address!r} (only http and https)")
        choices.append(Choice(show, dict(fill), tuple(links)))
    more = len(result) > limits.HELPER_CHOICES
    return Found(tuple(choices), _short(note), more, tuple(left_out))


def _pairs(raw: Any, what: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, Mapping):
        raise TypeError(f"{what} must be a dictionary")
    return tuple((_short(str(k)), _short(str(v))) for k, v in raw.items())


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LONGEST_TEXT else text[: LONGEST_TEXT - 1] + "…"
