"""Config file text made from the settings descriptions, so it is always up to date.

- :func:`plugin_block` writes one ``[[plugin]]`` block for a plugin: the values given, and
  every other setting as a comment with its default and help text. A config manager (the
  web interface, M5) can use it to add a plugin to a config file.
- :func:`example_config` writes ``paperpi.example.toml``: a short config that works as it
  is. ``paperpi example-config`` prints it; a test checks that the file in the repository
  is the same.
"""

from __future__ import annotations

import re
import textwrap
import tomllib
import types
import typing
from collections.abc import Iterable, Mapping
from typing import Any, Literal

import tomlkit
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import to_jsonable_python

from . import plugins
from .config import (
    CONFIG_VERSION,
    VIRTUAL_HEIGHT,
    VIRTUAL_MODE,
    VIRTUAL_WIDTH,
    DisplaySettings,
    WebSettings,
)
from .plugin import Plugin, PluginEntry

#: The blocks of the example file: name, plugin type and the settings that are set.
#: Weather twice, to show that one plugin type can be used more than once.
EXAMPLE_PLUGINS = (
    ("Clock", "basic_clock", {}),
    (
        "Weather Berlin",
        "met_no",
        {"lat": 52.52, "lon": 13.40, "place": "Berlin", "email": "you@example.com"},
    ),
    (
        "Weather Rio",
        "met_no",
        {"lat": -22.91, "lon": -43.17, "place": "Rio", "email": "you@example.com"},
    ),
)

_HEADER = """\
# PaperPi example config, made by "paperpi example-config". Save it as your config file
# (PaperPi reads /etc/paperpi/paperpi.toml unless you give --config) and change it there.
#
# The file only needs the settings that differ from the default. Every other setting is
# shown as a comment with its default: remove the # in front of it to change it.
# Each [[plugin]] block is one plugin on the screen; the same plugin type can be used
# more than once, with a different name. The weather blocks need your own email address
# in "email": met.no asks every program for a way to contact its user.
"""

#: Settings whose default is "empty", but that mean a known value; shown with that value.
_DISPLAY_SHOWN = {
    "width": VIRTUAL_WIDTH,
    "height": VIRTUAL_HEIGHT,
    "mode": VIRTUAL_MODE,
    # Examples for a real screen: the 9.7" IT8951 and the vcom printed on its cable.
    "model": "9.7",
    "vcom": -1.90,
}


def plugin_block(
    plugin: Plugin, name: str, values: Mapping[str, Any] | None = None, *, shared: bool = False
) -> str:
    """One ``[[plugin]]`` block for ``plugin``, called ``name``.

    ``values`` are the settings that are set (the plugin's own or shared ones); ``None``
    means "not set". Every other setting of the plugin follows as a comment with its
    default. With ``shared``, all shared settings (level, display time, ...) are listed too;
    otherwise only ``refresh`` and ``layout``, whose defaults depend on the plugin.

    Raises ``ValueError`` for an unknown setting or a value the plugin would not accept, so
    a config manager never writes a block that is switched off when the file loads. The
    text can hold secrets the user set (API keys): treat it like the config file.
    """
    own = plugin.settings.model_fields
    entry = PluginEntry.model_fields
    values = {k: v for k, v in (values or {}).items() if v is not None}
    for key in values:
        if key in ("name", "type") or key not in own | entry:
            known = ", ".join(k for k in own | entry if k not in ("name", "type"))
            raise ValueError(f"{plugin.type} has no setting {key!r}; it has: {known}")
    PluginEntry.model_validate(
        {"name": name, "type": plugin.type} | {k: v for k, v in values.items() if k in entry}
    )
    plugin.settings.model_validate({k: v for k, v in values.items() if k in own})
    if "layout" in values and values["layout"] not in plugin.layouts:
        raise ValueError(f"{plugin.type} has no layout {values['layout']!r}")
    lines = [
        *_comment(f"{plugin.type}: {plugin.description}"),
        *_comment(f'Layouts (values for "layout"): {", ".join(plugin.layouts)}'),
        "[[plugin]]",
        f"name = {_toml(name)}",
        f"type = {_toml(plugin.type)}",
    ]
    for key, value in values.items():
        lines += _setting(key, (own | entry)[key], value)
    shown = {
        "refresh": plugin.refresh,
        "layout": plugin.default_layout,
        "storage_mb": plugin.storage_mb,
        "storage_days": plugin.storage_days,
    }
    lines += _settings(own, values, {})
    if shared:
        keys = [k for k in entry if k not in ("name", "type")]
        lines.append("# --- Settings every plugin has ---")
    else:
        keys = ["refresh", "layout"]
        lines.append("# --- Settings every plugin has (all of them are in the first block) ---")
    lines += _settings({k: entry[k] for k in keys}, values, shown)
    text = "\n".join(lines) + "\n"
    _check_reads_back(text, {"name": name, "type": plugin.type} | values)
    return text


def display_part(values: Mapping[str, Any]) -> str:
    """The ``[display]`` part, with ``values`` set and every other setting as a comment."""
    values = {k: v for k, v in values.items() if v is not None}
    DisplaySettings.model_validate(values)
    lines = ["[display]"]
    for key, value in values.items():
        lines += _setting(key, DisplaySettings.model_fields[key], value)
    lines += _settings(DisplaySettings.model_fields, values, _DISPLAY_SHOWN)
    return "\n".join(lines) + "\n"


def web_part() -> str:
    """The ``[web]`` part, with every setting as a comment (the password is set in the web
    interface itself)."""
    lines = ["[web]", *_settings(WebSettings.model_fields, ("password_hash",), {})]
    lines += _comment(
        "The web interface saves the web password here as password_hash. For a new "
        "password: run sudo paperpi reset-password, restart or reload PaperPi, and open "
        "the web interface"
    )
    return "\n".join(lines) + "\n"


def example_config() -> str:
    """The text of ``paperpi.example.toml``."""
    parts = [
        _HEADER,
        f"config_version = {CONFIG_VERSION}\n",
        display_part({"type": "virtual"}),
        web_part(),
    ]
    for index, (name, plugin_type, values) in enumerate(EXAMPLE_PLUGINS):
        plugin = plugins.load(plugin_type)
        parts.append(plugin_block(plugin, name, values, shared=index == 0))
    return "\n".join(parts)


def _settings(
    fields: Mapping[str, FieldInfo], skip: Iterable[str], shown: Mapping[str, Any]
) -> list[str]:
    """Each setting in ``fields`` that is not in ``skip``, as a comment with its default."""
    lines = []
    for key, info in fields.items():
        if key not in skip:
            value = shown.get(key, info.get_default(call_default_factory=True))
            if hasattr(value, "get_secret_value"):
                value = ""  # never write a secret default, even in a comment
            lines += _setting(key, info, value, comment=True)
    return lines


def _setting(key: str, info: FieldInfo, value: Any, *, comment: bool = False) -> list[str]:
    """The help line and the ``key = value`` line of one setting."""
    help_text = info.description or key
    choices = _choices(info.annotation)
    named = all(re.search(rf"\b{re.escape(str(c))}\b", help_text) for c in choices)
    if choices and not named:
        help_text += f". One of: {', '.join(_toml(c) for c in choices)}"
    line = f"{key} = {_toml(value)}" if value is not None else f"{key} ="
    return [*_comment(help_text), f"# {line}" if comment else line]


def _comment(text: str) -> list[str]:
    """``text`` as comment lines of at most 100 characters (line breaks become spaces)."""
    return textwrap.wrap(text, width=100, initial_indent="# ", subsequent_indent="# ")


def _check_reads_back(text: str, values: Mapping[str, Any]) -> None:
    """Raise ``ValueError`` unless PaperPi reads ``text`` back as exactly ``values``.

    tomlkit writes a few things (such as the control character ESC) in a newer form of
    TOML than Python's reader understands; such a block would make the whole file
    unreadable.
    """
    expected = {"plugin": [{k: _plain(v) for k, v in values.items()}]}
    try:
        read = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"can't be written so that PaperPi reads it back: {error}") from None
    if read != expected:
        raise ValueError("can't be written so that PaperPi reads it back the same")


def _choices(annotation: Any) -> tuple:
    """The allowed values of a ``Literal`` setting (also inside ``... | None``)."""
    if typing.get_origin(annotation) is Literal:
        return typing.get_args(annotation)
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        for part in typing.get_args(annotation):
            if typing.get_origin(part) is Literal:
                return typing.get_args(part)
    return ()


def _plain(value: Any) -> Any:
    """``value`` as plain data: text, numbers, true/false, lists and dictionaries."""
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return to_jsonable_python(value)


def _toml(value: Any) -> str:
    """``value`` written as in a TOML file: ``24``, ``true``, ``"Berlin"``, ``[1, 2]``,
    ``{a = 1}`` (a group of settings on one line)."""
    value = _plain(value)
    if isinstance(value, dict):
        items = (f"{tomlkit.key(k).as_string()} = {_toml(v)}" for k, v in value.items())
        return "{" + ", ".join(items) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # 120, not 120.0
    return tomlkit.item(value).as_string()
