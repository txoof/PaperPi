"""Config file text made from the settings descriptions, so it is always up to date.

- :func:`plugin_block` writes one ``[[plugin]]`` block for a plugin: the values given, and
  every other setting as a comment with its default and help text. A config manager (the
  web interface, M5) can use it to add a plugin to a config file.
- :func:`example_config` writes ``paperpi.example.toml``: a short config that works as it
  is. A test checks that the file in the repository is the same. ``paperpi example-config``
  prints it with new random plugin IDs, so two installs never share one (#263).
- :func:`setup_config` writes the first config of a new install: a clock and the set-up
  screen, which asks to set PaperPi up in the web interface (``paperpi example-config
  --setup``; the installer uses it).
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
from .plugin import Plugin, PluginEntry, is_required, new_id

#: The blocks of the example file: ID, plugin type and the settings that are set.
#: Weather twice, to show that one plugin type can be used more than once. The IDs have the
#: form the Plugin Library makes (:func:`paperpi.plugin.new_id`), fixed here so the file in
#: the repository stays the same.
EXAMPLE_PLUGINS = (
    ("basic_clock-5c1e0a7b", "basic_clock", {"name": "Clock"}),
    (
        "met_no-3a91d2f4",
        "met_no",
        {"name": "Weather Berlin", "lat": 52.52, "lon": 13.40, "place": "Berlin"},
    ),
    (
        "met_no-b7e40c19",
        "met_no",
        {"name": "Weather Rio", "lat": -22.91, "lon": -43.17, "place": "Rio"},
    ),
)

#: The blocks of the first config after installing: the clock, and the set-up screen with
#: the web address, until the user chooses their own plugins in the web interface.
SETUP_PLUGINS = (
    ("basic_clock-8d2f6e30", "basic_clock", {"name": "Clock"}),
    ("splash_screen-1b4c9a57", "splash_screen", {"name": "Set up PaperPi", "layout": "setup"}),
)

_SETUP_HEADER = """\
# PaperPi config, made by "paperpi example-config --setup" when PaperPi was installed. It
# shows a clock and a screen that asks to set PaperPi up: open the web interface (the address
# is on the screen), set a password and choose which plugins to display.
#
# The file only needs the settings that differ from the default. Every other setting is
# shown as a comment with its default: remove the # in front of it to change it.
"""

_HEADER = """\
# PaperPi example config, made by "paperpi example-config". Save it as your config file
# (PaperPi reads /etc/paperpi/paperpi.toml unless you give --config) and change it there.
#
# The file only needs the settings that differ from the default. Every other setting is
# shown as a comment with its default: remove the # in front of it to change it.
# Each [[plugin]] block is one plugin on the screen; the same plugin type can be used
# more than once, with a different id. PaperPi made each id: the plugin type and 8 random
# letters and digits. Keep it as it is, because it names the plugin's storage folder.
# The weather blocks are not shown until you remove the # in front of "email" and fill in
# your own, real email address: met.no asks every program for a way to contact its user.
# Settings marked "(required)" must be filled in before a plugin is shown.
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


#: Settings of a ``[[plugin]]`` block that :func:`plugin_block` takes as its own arguments.
_FIXED = ("id", "type")


def plugin_block(
    plugin: Plugin, plugin_id: str, values: Mapping[str, Any] | None = None, *, shared: bool = False
) -> str:
    """One ``[[plugin]]`` block for ``plugin``, with ID ``plugin_id``.

    ``values`` are the settings that are set (the plugin's own or shared ones, also the
    ``name`` it is shown with); ``None`` means "not set". Every other setting of the plugin
    follows as a comment with its default. With ``shared``, all shared settings (display
    time, ...) are listed too; otherwise only ``refresh``, ``level`` and ``layout``, whose
    defaults depend on the plugin.

    Raises ``ValueError`` for an unknown setting or a value the plugin would not accept, so
    a config manager never writes a block that is switched off when the file loads. The
    text can hold secrets the user set (API keys): treat it like the config file.
    """
    own = plugin.settings.model_fields
    entry = PluginEntry.model_fields
    values = {k: v for k, v in (values or {}).items() if v is not None}
    for key in values:
        if key in _FIXED or key not in own | entry:
            known = ", ".join(k for k in own | entry if k not in _FIXED)
            raise ValueError(f"{plugin.type} has no setting {key!r}; it has: {known}")
    PluginEntry.model_validate(
        {"id": plugin_id, "type": plugin.type} | {k: v for k, v in values.items() if k in entry}
    )
    plugin.settings.model_validate({k: v for k, v in values.items() if k in own})
    if "layout" in values and values["layout"] not in plugin.layouts:
        raise ValueError(f"{plugin.type} has no layout {values['layout']!r}")
    lines = [
        *_comment(f"{plugin.type}: {plugin.description}"),
        *_comment(f'Layouts (values for "layout"): {", ".join(plugin.layouts)}'),
        "[[plugin]]",
    ]
    if shared:
        lines += _comment(entry["id"].description or "")
    lines.append(f"id = {toml_value(plugin_id)}")
    named = "name" in values
    if shared:
        lines += _setting("name", entry["name"], values.get("name", ""), comment=not named)
    elif named:
        lines.append(f"name = {toml_value(values['name'])}")
    lines.append(f"type = {toml_value(plugin.type)}")
    for key, value in values.items():
        if key == "name":
            continue
        lines += _setting(key, (own | entry)[key], value)
    shown = suggested(plugin)
    lines += _settings(own, values, {})
    if shared:
        keys = [k for k in entry if k not in (*_FIXED, "name")]
        lines.append("# --- Settings every plugin has ---")
    else:
        keys = ["refresh", "level", "layout"]
        lines.append("# --- Settings every plugin has (all of them are in the first block) ---")
    lines += _settings({k: entry[k] for k in keys}, values, shown)
    text = "\n".join(lines) + "\n"
    _check_reads_back(text, {"id": plugin_id, "type": plugin.type} | values)
    return text


def suggested(plugin: Plugin) -> dict[str, Any]:
    """The shared settings whose default is the plugin's suggestion, with that suggestion."""
    return {
        "refresh": plugin.refresh,
        "level": plugin.level,
        "layout": plugin.default_layout,
        "storage_mb": plugin.storage_mb,
        "storage_days": plugin.storage_days,
    }


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


def example_config(display: Mapping[str, Any] | None = None, *, fresh: bool = False) -> str:
    """The text of ``paperpi.example.toml``; ``display``: the ``[display]`` settings to set
    (default: the virtual screen). With ``fresh``, each plugin gets a new random ID instead
    of the fixed one (for a user's own config file)."""
    return _config(_HEADER, display, EXAMPLE_PLUGINS, fresh)


def setup_config(display: Mapping[str, Any] | None = None, *, fresh: bool = False) -> str:
    """The first config of a new install: :data:`SETUP_PLUGINS`. ``display`` and ``fresh``
    as in :func:`example_config`."""
    return _config(_SETUP_HEADER, display, SETUP_PLUGINS, fresh)


def _config(
    header: str, display: Mapping[str, Any] | None, blocks: Iterable[tuple], fresh: bool
) -> str:
    parts = [
        header,
        f"config_version = {CONFIG_VERSION}\n",
        display_part(display or {"type": "virtual"}),
        web_part(),
    ]
    for index, (plugin_id, plugin_type, values) in enumerate(blocks):
        plugin = plugins.load(plugin_type)
        if fresh:
            plugin_id = new_id(plugin_type)
        parts.append(plugin_block(plugin, plugin_id, values, shared=index == 0))
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
    if is_required(info):
        help_text += " (required)"
    allowed = choices(info.annotation)
    named = all(re.search(rf"\b{re.escape(str(c))}\b", help_text) for c in allowed)
    if allowed and not named:
        help_text += f". One of: {', '.join(toml_value(c) for c in allowed)}"
    line = f"{key} = {toml_value(value)}" if value is not None else f"{key} ="
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
    expected = {"plugin": [{k: plain(v) for k, v in values.items()}]}
    try:
        read = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"can't be written so that PaperPi reads it back: {error}") from None
    if read != expected:
        raise ValueError("can't be written so that PaperPi reads it back the same")


def choices(annotation: Any) -> tuple:
    """The allowed values of a ``Literal`` setting (also inside ``... | None``)."""
    if typing.get_origin(annotation) is Literal:
        return typing.get_args(annotation)
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        for part in typing.get_args(annotation):
            if typing.get_origin(part) is Literal:
                return typing.get_args(part)
    return ()


def plain(value: Any) -> Any:
    """``value`` as plain data: text, numbers, true/false, lists and dictionaries."""
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return to_jsonable_python(value)


def toml_value(value: Any) -> str:
    """``value`` written as in a TOML file: ``24``, ``true``, ``"Berlin"``, ``[1, 2]``,
    ``{a = 1}`` (a group of settings on one line)."""
    value = plain(value)
    if isinstance(value, dict):
        items = (f"{tomlkit.key(k).as_string()} = {toml_value(v)}" for k, v in value.items())
        return "{" + ", ".join(items) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # 120, not 120.0
    return tomlkit.item(value).as_string()
