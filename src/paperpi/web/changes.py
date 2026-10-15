"""The Review changes page: hand edits to the config file that PaperPi does not use yet.

PaperPi keeps using the config text it loaded last
(:attr:`~paperpi.scheduler.Summary.config_text`) until it is told to load the file again
(see ``docs/decisions/live-config-reload.md``). When the file on disk holds other settings,
and it is not the text the web interface saved itself, it was changed by hand. Every page
then shows a bar that links to the Review changes page, which lists the changes: per plugin
(matched by its ID), the screen, the web interface and the rest of the file, each setting
with its old and new value.

Only the settings count: a change to a comment or a blank line is not one.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import Any, Literal

from .. import config, example, plugins
from ..config import (
    NEXT_START,
    WEB_NEXT_START,
    ConfigError,
    DisplaySettings,
    WebSettings,
    folder_name,
)
from ..plugin import PluginEntry, holds_secret
from .forms import defaults

#: Values longer than this many characters are cut short on the page.
LONGEST_VALUE = 80
NEXT_START_NOTE = "Applies at the next start of PaperPi, not now."
HIDDEN = "(hidden)"


@dataclass(frozen=True)
class Change:
    """One setting that changed."""

    key: str
    old: str | None
    """The value as written in the file; ``None``: not set."""
    new: str | None
    note: str = ""
    default: str | None = None
    """The value it has when it is not set; ``None``: not known (or no value)."""


@dataclass(frozen=True)
class Group:
    """The changes in one part of the file: a plugin block, ``[display]``, ``[web]``, ..."""

    title: str
    kind: str
    """The plugin type, or the part of the file (``[display]``)."""
    changes: tuple[Change, ...] = ()
    status: Literal["", "added", "removed"] = ""
    note: str = ""
    index: int | None = None
    """A plugin's place in the edited file (for its settings page); ``None``: no page."""
    plugin_id: str = ""


@dataclass(frozen=True)
class Review:
    groups: tuple[Group, ...]
    mistakes: tuple[str, ...] = ()
    """Why the edited file can't be used at all; it can't be applied then."""
    problems: tuple[str, ...] = ()
    """Errors in single plugin blocks: those plugins are left out until they are fixed."""


def waiting(applied: str, edited: str) -> bool:
    """True when the edited file text holds other settings than the one PaperPi uses."""
    if applied == edited:
        return False
    try:
        return _toml(applied) != _toml(edited)
    except ValueError:
        return True  # a file that is not valid TOML: the page names the mistake


def review(applied: str, edited: str, source: str = "paperpi.toml") -> Review:
    """What changed from the ``applied`` config text to the ``edited`` one, and whether the
    edited text can be used (``source``: the file name the mistakes name)."""
    try:
        checked = config.parse(edited, source)
    except ConfigError as error:
        mistakes = tuple(str(p) for p in error.problems if p.level == "error")
        return Review((), mistakes or (str(error),))
    problems = tuple(str(p) for p in checked.errors)
    try:
        old = _toml(applied)
    except ValueError:
        old = {}
    return Review(tuple(compare(old, _toml(edited))), problems=problems)


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[Group]:
    """The changed parts from ``old`` to ``new`` (both as TOML reads them), in file order."""
    groups = []
    for key in dict.fromkeys([*new, *old]):
        if key == "plugin":
            groups += _plugins(_blocks(old), _blocks(new))
        elif key == "display":
            changes = _changes(
                old.get(key), new.get(key), notes=_notes(NEXT_START), shown=_model(DisplaySettings)
            )
            groups.append(Group("Screen", "[display]", changes))
        elif key == "web":
            notes = _notes(WEB_NEXT_START) | {
                "password_hash": "The web password changes: log in with the new one."
            }
            changes = _changes(
                old.get(key), new.get(key), {"password_hash"}, notes, _model(WebSettings)
            )
            groups.append(Group("Web interface", "[web]", changes))
    other = {k: v for k, v in old.items() if k not in _OWN_PARTS}
    changes = _changes(other, {k: v for k, v in new.items() if k not in _OWN_PARTS})
    groups.append(Group("Other settings", "", changes))
    return [g for g in groups if g.changes or g.status or g.note]


_OWN_PARTS = ("plugin", "display", "web")


def _plugins(old: list[dict], new: list[dict]) -> list[Group]:
    keys_old, keys_new = _keys(old), _keys(new)
    places_old = {k: n for n, k in enumerate(k for k in keys_old if k in keys_new)}
    places_new = {k: n for n, k in enumerate(k for k in keys_new if k in keys_old)}
    groups = []
    for index, (key, block) in enumerate(zip(keys_new, new, strict=True)):
        before = old[keys_old.index(key)] if key in keys_old else None
        title, kind = _title(block), str(block.get("type", ""))
        plugin_id = block.get("id") if isinstance(block.get("id"), str) else ""
        secret, shown = _plugin_info(kind)
        place = _place(index, new)
        if before is None:
            note = f"Joins the order at place {place} (where it is in the file)."
            if block.get("enabled", True) is False:
                note = "Switched off."
            changes = _changes({}, _without(block, "id", "type"), secret)  # no old values
            groups.append(Group(title, kind, changes, "added", note, index, plugin_id))
            continue
        changes = _changes(before, block, secret, {"id": _NEW_ID}, shown)
        note = ""
        # Moved among the other plugins, not only pushed along by an added or removed one.
        if places_old[key] != places_new[key] and _place(keys_old.index(key), old) != place:
            note = f"Moves to place {place} in the order."
        if changes or note:
            groups.append(Group(title, kind, changes, "", note, index, plugin_id))
    for key, block in zip(keys_old, old, strict=True):
        if key not in keys_new:
            note = "Its storage folder is kept (it may hold photos): remove it by hand if needed."
            groups.append(Group(_title(block), str(block.get("type", "")), (), "removed", note))
    return groups


_NEW_ID = "A new ID starts with an empty storage folder."


def _blocks(data: dict[str, Any]) -> list[dict]:
    found = data.get("plugin", [])
    if not isinstance(found, list):
        return []
    return [b if isinstance(b, dict) else {} for b in found]


def _keys(blocks: list[dict]) -> list[tuple]:
    """What a block is matched by: its ID (as IDs are compared), else its place."""
    keys = []
    for index, block in enumerate(blocks):
        found = block.get("id")
        key = ("id", folder_name(found)) if isinstance(found, str) and found else ("at", index)
        # Two blocks with one ID (a mistake the page names): the second one by its place.
        keys.append(key if key not in keys else ("at", index))
    return keys


def _title(block: dict) -> str:
    for key in ("name", "id"):
        if isinstance(block.get(key), str) and block[key].strip():
            return block[key]
    return "A plugin without an ID"


def _place(index: int, blocks: list[dict]) -> int:
    """The place in the order (counted from 1) of block ``index``; ``default`` takes none."""
    return 1 + sum(1 for b in blocks[:index] if b.get("type") != "default")


def _plugin_info(plugin_type: str) -> tuple[set[str], dict[str, Any]]:
    """The settings of ``plugin_type`` that hold a secret (an API key, ...), and the value
    of each setting when it is not set."""
    if plugin_type not in plugins.available():
        return set(), {}
    try:
        plugin = plugins.load(plugin_type)
    except Exception:  # noqa: BLE001 - a plugin that can't be loaded is named elsewhere
        return set(), {}
    found = plugin.settings.model_fields
    secret = {k for k, info in found.items() if holds_secret(info.annotation)}
    return secret, _model(PluginEntry) | defaults(plugin)


def _model(model: type) -> dict[str, Any]:
    """The value of each setting of a part of the file (a pydantic model) when it is not set."""
    return {key: info.default for key, info in model.model_fields.items()}


def _notes(next_start: tuple[str, ...]) -> dict[str, str]:
    return dict.fromkeys(next_start, NEXT_START_NOTE)


def _without(block: dict, *keys: str) -> dict:
    return {k: v for k, v in block.items() if k not in keys}


def _changes(
    old: Any,
    new: Any,
    secret: set[str] = frozenset(),
    notes: dict[str, str] | None = None,
    shown: dict[str, Any] | None = None,
) -> tuple[Change, ...]:
    """The changed settings; ``shown``: the value of each when it is not set."""
    old, new = _flat(old), _flat(new)
    notes, shown = notes or {}, shown or {}
    found = []
    for key in dict.fromkeys([*new, *old]):
        if old.get(key, _UNSET) == new.get(key, _UNSET):
            continue
        hidden = key.partition(".")[0] in secret
        found.append(
            Change(
                key,
                _shown(old.get(key, _UNSET), hidden),
                _shown(new.get(key, _UNSET), hidden),
                notes.get(key, ""),
                _default(shown.get(key), hidden),
            )
        )
    return tuple(found)


_UNSET = object()


def _flat(value: Any, prefix: str = "") -> dict[str, Any]:
    """The settings of a part of the file: ``{"a.b": 1}`` for ``[x.a] b = 1``."""
    if not isinstance(value, dict):
        return {} if value is None else {prefix.rstrip("."): value}
    found = {}
    for key, item in value.items():
        if isinstance(item, dict) and item:
            found |= _flat(item, f"{prefix}{key}.")
        else:
            found[f"{prefix}{key}"] = item
    return found


def _shown(value: Any, hidden: bool) -> str | None:
    if value is _UNSET:
        return None
    if hidden:
        return HIDDEN
    text = example.toml_value(value)
    return text if len(text) <= LONGEST_VALUE else text[: LONGEST_VALUE - 1] + "…"


def _default(value: Any, hidden: bool) -> str | None:
    if value is None or hidden:
        return None
    try:
        return _shown(value, False)
    except Exception:  # noqa: BLE001 - e.g. a value TOML can't hold: then it is not shown
        return None


def _toml(text: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, RecursionError, ValueError) as error:
        raise ValueError(str(error)) from None
