"""The plugin settings form: its fields, made from the plugin's settings description, and
the values a sent form holds, checked the same way as the config file.

- :func:`fields` lists the settings the form shows, in groups: the plugin's ``name``, its
  own settings, the shared ones people change most (:data:`COMMON`), and the rest
  ("More settings"). Each field shows the setting's value, or its default when the config
  file doesn't set it. ``id`` and ``type`` can't change; ``enabled`` is switched on the
  Active Plugins page.
- :func:`read` turns a sent form into the changes to save, or an error per field (then
  nothing is saved). An empty field means "the default" (for a check box: off; for a list:
  nothing picked). A value changed to its default is taken out of the file, which only holds
  the settings that differ from the default (``docs/decisions/config-format.md``). An empty
  secret (an API key, ...) keeps the one that is saved, so the page never has to show it.
- Browsers send nothing for a check box that is off or a list with nothing picked. So the
  page adds a hidden empty field for each, and a field that is missing from the form is
  left as it is.
- A setting of a kind the form can't show (a group of settings, a list of numbers) is shown
  as it is in the file, to be changed there.
"""

from __future__ import annotations

import re
import types
import typing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, SecretStr, ValidationError
from pydantic.fields import FieldInfo

from .. import example
from ..plugin import Plugin, PluginEntry, is_required

#: The shared settings shown right after the plugin's own ones; the others are folded away
#: under "More settings" (agreed with txoof, M5 part 3a).
COMMON = ("display_time", "refresh", "layout", "level")
#: Settings of a ``[[plugin]]`` block the form doesn't change.
NOT_IN_FORM = ("id", "type", "enabled")

Kind = Literal["choice", "check", "number", "text", "secret", "choices", "file"]
Group = Literal["name", "own", "common", "more"]


@dataclass(frozen=True)
class FormField:
    """One setting on the form."""

    key: str
    help: str
    kind: Kind
    """``choice``: pick one; ``check``: on or off; ``number``; ``text``; ``secret``: text
    that is never shown; ``choices``: pick several; ``file``: change it in the file."""
    group: Group
    value: str = ""
    """The value as text (``""``: not set). ``check``: ``"true"`` or ``"false"``."""
    selected: tuple[str, ...] = ()
    """``choices``: the ones picked, as text."""
    choices: tuple[str, ...] = ()
    """``choice`` and ``choices``: every value it may have, as text."""
    values: tuple[Any, ...] = ()
    """The values of ``choices`` themselves (``12`` for ``"12"``)."""
    default: str = ""
    """The default, as text (``""``: none)."""
    required: bool = False
    """The plugin is not shown until this is filled in (see ``paperpi.plugin.setting``)."""
    is_set: bool = False
    """``secret``: a value is saved."""
    minimum: float | None = None
    maximum: float | None = None
    whole: bool = False
    """``number``: whole numbers only."""
    max_length: int | None = None
    error: str = ""


@dataclass(frozen=True)
class Read:
    """What :func:`read` found in a sent form."""

    changes: dict[str, Any]
    """Each setting to change, with its new value; ``None`` takes it out of the file."""
    errors: dict[str, str] = field(default_factory=dict)
    """Why a setting's value can't be used, by setting (``""``: not one field)."""
    sent: dict[str, Sequence[str]] = field(default_factory=dict)
    """The form as sent, to show it again with the errors."""


def defaults(plugin: Plugin) -> dict[str, Any]:
    """The value each setting has when the file doesn't set it: the shared settings' and
    the plugin's own defaults, and the plugin's suggestions (``refresh``, the first layout,
    the storage limits)."""
    found = {key: info.default for key, info in _infos(plugin).items()}
    return found | {
        "refresh": plugin.refresh,
        "layout": plugin.default_layout,
        "storage_mb": plugin.storage_mb,
        "storage_days": plugin.storage_days,
    }


def fields(
    plugin: Plugin,
    block: Mapping[str, Any],
    sent: Mapping[str, Sequence[str]] | None = None,
    errors: Mapping[str, str] | None = None,
) -> list[FormField]:
    """The fields of the form for ``plugin``, whose ``[[plugin]]`` block holds ``block``.
    With ``sent`` (a form that had ``errors``), they show what was sent."""
    shown = defaults(plugin)
    errors = errors or {}
    found = []
    for key, info in _infos(plugin).items():
        kind, allowed = _kind(info.annotation)
        if key == "layout":
            kind, allowed = "choice", tuple(plugin.layouts)
        value = block.get(key, shown[key])
        texts = [_text(v) for v in value] if isinstance(value, list | tuple) else [_text(value)]
        if kind == "file":
            texts = [example.toml_value(value) if value is not None else ""]
        if sent is not None and key in sent and kind not in ("secret", "file"):
            # Without the empty value the page sends for a check box or list.
            texts = [t for t in sent[key] if t] or [""]
            if kind == "check":
                texts = ["true" if texts[-1] not in ("", "false") else "false"]
            elif kind == "choices":
                texts = [t for t in texts if t]
        found.append(
            FormField(
                key=key,
                help=info.description or key,
                kind=kind,
                group=_group(key, plugin),
                value="" if kind in ("secret", "choices") else (texts[-1] if texts else ""),
                selected=tuple(texts) if kind == "choices" else (),
                choices=tuple(_text(c) for c in allowed),
                values=tuple(allowed),
                default="" if kind == "secret" else _text(shown[key]),
                required=is_required(info),
                is_set=kind == "secret" and bool(_text(value)),
                minimum=_limit(info, "ge", "gt"),
                maximum=_limit(info, "le", "lt"),
                whole=_plain_type(info.annotation) is int,
                max_length=_limit(info, "max_length"),
                error=errors.get(key, ""),
            )
        )
    order: list[Group] = ["name", "own", "common", "more"]
    return sorted(
        found,
        key=lambda f: (order.index(f.group), COMMON.index(f.key) if f.group == "common" else 0),
    )


def read(plugin: Plugin, block: Mapping[str, Any], form: Mapping[str, Sequence[str]]) -> Read:
    """The changes a sent ``form`` makes to the ``[[plugin]]`` block holding ``block``, each
    value checked by the plugin's settings description. ``form`` maps a field to the texts
    sent for it (several for a ``choices`` field)."""
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    sent = {key: list(texts) for key, texts in form.items()}
    for item in fields(plugin, block):
        # A field that is not in the form stays as it is (see the top of this file).
        if item.key not in sent:
            continue
        texts = [t.strip() for t in sent[item.key]]
        if item.kind == "choices":
            texts = [t for t in texts if t]
        text = texts[-1] if texts else ""
        if item.kind == "file" or (item.kind == "secret" and not text):
            continue
        try:
            values[item.key] = _value(item, text, texts)
        except ValueError as error:
            errors[item.key] = str(error)
    shared = {k: v for k, v in values.items() if k in PluginEntry.model_fields}
    own = {k: v for k, v in values.items() if k not in shared}
    entry = {k: block[k] for k in ("id", "type") if k in block}
    _check(PluginEntry, entry | _set(block, shared, PluginEntry), errors)
    _check(plugin.settings, _set(block, own, plugin.settings), errors)
    if errors:
        # Shown again on the page, so without what was typed into a secret field.
        secrets = {item.key for item in fields(plugin, block) if item.kind == "secret"}
        return Read({}, errors, {k: v for k, v in sent.items() if k not in secrets})
    shown = defaults(plugin)
    changes = {}
    for key, value in values.items():
        # As plain data: the file gives a list where the form gives a tuple. A value as it
        # is in the file stays, also one written there that equals the default.
        if key in block and example.plain(value) == example.plain(block[key]):
            continue
        new = None if example.plain(value) == example.plain(shown[key]) else value
        if example.plain(new) != example.plain(block.get(key)):
            changes[key] = new
    return Read(changes)


def _infos(plugin: Plugin) -> dict[str, FieldInfo]:
    """Every setting the form shows, with its description."""
    entry = {k: v for k, v in PluginEntry.model_fields.items() if k not in NOT_IN_FORM}
    return entry | dict(plugin.settings.model_fields)


def _group(key: str, plugin: Plugin) -> Group:
    if key == "name":
        return "name"
    if key in plugin.settings.model_fields:
        return "own"
    return "common" if key in COMMON else "more"


def _kind(annotation: Any) -> tuple[Kind, tuple]:
    """The kind of field for a setting of this type, and the values it may have."""
    allowed = example.choices(annotation)
    if allowed:
        return "choice", allowed
    plain = _plain_type(annotation)
    if typing.get_origin(plain) in (tuple, list):
        inner = typing.get_args(plain)
        allowed = example.choices(inner[0]) if inner else ()
        return ("choices", allowed) if allowed else ("file", ())
    if plain is bool:
        return "check", ()
    if plain in (int, float):
        return "number", ()
    if plain is SecretStr:
        return "secret", ()
    if plain is str:
        return "text", ()
    return "file", ()


def _plain_type(annotation: Any) -> Any:
    """``annotation`` without ``| None``."""
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        parts = [a for a in typing.get_args(annotation) if a is not type(None)]
        return parts[0] if len(parts) == 1 else annotation
    return annotation


def _limit(info: FieldInfo, *names: str) -> Any:
    """The first of the limits ``names`` (``ge``, ``max_length``, ...) the setting has."""
    for part in info.metadata:
        for name in names:
            found = getattr(part, name, None)
            if found is not None:
                return found
    return None


def _text(value: Any) -> str:
    """``value`` as the form shows it."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)


def _value(item: FormField, text: str, texts: list[str]) -> Any:
    """The value of a field, from the text sent for it. Raises ``ValueError``."""
    if item.kind == "check":
        return text not in ("", "false")
    if item.kind == "choices":
        if any(t not in item.choices for t in texts):
            raise ValueError(f"choose from: {', '.join(item.choices)}")
        # Each one once, in the order of the choices (a form can't send more).
        return tuple(_choice(item, t) for t in item.choices if t in texts)
    if not text:
        return None
    if item.kind == "number":
        # Plain digits only: int() and float() also take "1_0", "nan" and other scripts' digits.
        pattern = r"-?[0-9]{1,18}" if item.whole else r"-?[0-9]{1,18}(\.[0-9]{1,18})?"
        if not re.fullmatch(pattern, text):
            raise ValueError("enter a whole number" if item.whole else "enter a number")
        return int(text) if item.whole else float(text)
    if item.kind == "choice":
        if text not in item.choices:
            raise ValueError(f"choose one of: {', '.join(item.choices)}")
        return _choice(item, text)
    return text


def _choice(item: FormField, text: str) -> Any:
    """The value of a choice from its text, e.g. ``12`` for ``"12"`` (hours)."""
    return item.values[item.choices.index(text)]


def _set(
    block: Mapping[str, Any], values: Mapping[str, Any], model: type[BaseModel]
) -> dict[str, Any]:
    """The settings of ``model`` in ``block`` with ``values`` changed (``None``: not set)."""
    merged = {k: v for k, v in block.items() if k in model.model_fields} | dict(values)
    return {k: v for k, v in merged.items() if v is not None}


def _check(model: type[BaseModel], values: Mapping[str, Any], errors: dict[str, str]) -> None:
    """Add what ``model`` finds wrong with ``values`` to ``errors``, by setting."""
    try:
        model.model_validate(values)
    except ValidationError as error:
        for found in error.errors():
            key = str(found["loc"][0]) if found["loc"] else ""
            errors.setdefault(key, found["msg"].removeprefix("Value error, "))
