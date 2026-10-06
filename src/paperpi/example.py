"""Config file text made from the settings descriptions, so it is always up to date.

- :func:`plugin_block` writes one ``[[plugin]]`` block for a plugin: the values given, and
  every other setting as a comment with its default and help text. A config manager (the
  web interface, M5) can use it to add a plugin to a config file.
- :func:`example_config` writes ``paperpi.example.toml``: a short config that works as it
  is. ``paperpi example-config`` prints it; a test checks that the file in the repository
  is the same.
"""

from __future__ import annotations

import textwrap
import types
import typing
from collections.abc import Iterable, Mapping
from typing import Any, Literal

import tomlkit
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from . import plugins
from .config import CONFIG_VERSION, VIRTUAL_HEIGHT, VIRTUAL_MODE, VIRTUAL_WIDTH, DisplaySettings
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
# PaperPi example config, made by "paperpi example-config". Don't edit this file: it is
# made again from the program. Copy it to /etc/paperpi/paperpi.toml and change the copy.
#
# The file only needs the settings that differ from the default. Every other setting is
# shown as a comment with its default: remove the # in front of it to change it.
# Each [[plugin]] block is one plugin on the screen; the same plugin type can be used
# more than once, with a different name.
"""

#: Settings whose default is "empty", but that mean a known value; shown with that value.
_DISPLAY_SHOWN = {"width": VIRTUAL_WIDTH, "height": VIRTUAL_HEIGHT, "mode": VIRTUAL_MODE}


def plugin_block(
    plugin: Plugin, name: str, values: Mapping[str, Any] | None = None, *, shared: bool = False
) -> str:
    """One ``[[plugin]]`` block for ``plugin``, called ``name``.

    ``values`` are the settings that are set (the plugin's own or shared ones). Every other
    setting of the plugin follows as a comment with its default. With ``shared``, all
    shared settings (level, display time, ...) are listed too; otherwise only ``refresh``
    and ``layout``, whose defaults depend on the plugin.
    """
    values = dict(values or {})
    layouts = ", ".join(plugin.layouts)
    lines = [
        f"# {plugin.type}: {plugin.description}",
        f"# Layouts: {layouts}",
        "[[plugin]]",
        f"name = {_toml(name)}",
        f"type = {_toml(plugin.type)}",
    ]
    own = plugin.settings.model_fields
    entry = PluginEntry.model_fields
    for key, value in values.items():
        lines += _setting(key, (own | entry)[key], value)
    shown = {"refresh": plugin.refresh, "layout": plugin.default_layout}
    lines += _settings(own, values, {})
    if shared:
        keys = [k for k in entry if k not in ("name", "type")]
        lines.append("# --- Settings every plugin has ---")
    else:
        keys = ["refresh", "layout"]
        lines.append("# --- Settings every plugin has (all of them are in the first block) ---")
    lines += _settings({k: entry[k] for k in keys}, values, shown)
    return "\n".join(lines) + "\n"


def display_part(values: Mapping[str, Any]) -> str:
    """The ``[display]`` part, with ``values`` set and every other setting as a comment."""
    lines = ["[display]"]
    for key, value in values.items():
        lines += _setting(key, DisplaySettings.model_fields[key], value)
    lines += _settings(DisplaySettings.model_fields, values, _DISPLAY_SHOWN)
    return "\n".join(lines) + "\n"


def example_config() -> str:
    """The text of ``paperpi.example.toml``."""
    parts = [_HEADER, f"config_version = {CONFIG_VERSION}\n", display_part({"type": "virtual"})]
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
            lines += _setting(key, info, shown.get(key, info.default), comment=True)
    return lines


def _setting(key: str, info: FieldInfo, value: Any, *, comment: bool = False) -> list[str]:
    """The help line and the ``key = value`` line of one setting."""
    help_text = info.description or key
    choices = _choices(info.annotation)
    if choices and not all(str(c) in help_text for c in choices):
        help_text += f". One of: {', '.join(_toml(c) for c in choices)}"
    line = f"{key} = {_toml(value)}" if value is not None else f"{key} ="
    help_lines = textwrap.wrap(help_text, width=100, initial_indent="# ", subsequent_indent="# ")
    return [*help_lines, f"# {line}" if comment else line]


def _choices(annotation: Any) -> tuple:
    """The allowed values of a ``Literal`` setting (also inside ``... | None``)."""
    if typing.get_origin(annotation) is Literal:
        return typing.get_args(annotation)
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        for part in typing.get_args(annotation):
            if typing.get_origin(part) is Literal:
                return typing.get_args(part)
    return ()


def _toml(value: Any) -> str:
    """``value`` written as in a TOML file: ``24``, ``true``, ``"Berlin"``, ``[1, 2]``."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # 120, not 120.0
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return tomlkit.item(value).as_string()
