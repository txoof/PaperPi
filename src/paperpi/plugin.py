"""The plugin interface (v2).

A plugin puts something on the screen: a clock, the weather, the song that is playing. The
reasons behind this interface are in ``docs/decisions/plugin-interface.md``; how to write a
plugin is in ``docs/writing-plugins.md``.

A plugin is a folder in ``src/paperpi/plugins/<type>/`` whose ``__init__.py`` has a
:class:`Plugin` called ``PLUGIN``. One update is two steps:

1. ``fetch(context)`` gets the data (from the clock, the network, ...) and returns
   :data:`NOTHING`, :func:`ready` or :func:`alert`.
2. ``draw(data, context)`` turns the data into values for the blocks of the chosen layout.
   PaperPi draws the layout with epdlib.

For sample images and tests, step 1 is skipped and ``sample`` is drawn instead, so every
plugin can draw an image without network access. Each update runs in its own short-lived
process (see :mod:`paperpi.runner`); a plugin can't keep anything in memory between updates.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from epdlib import Layout, ScreenMode
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.fields import FieldInfo

from . import limits


class State(StrEnum):
    """What a plugin has to show (see ``docs/decisions/plugin-scheduling.md``)."""

    NOTHING = "nothing"
    """Nothing to show right now, e.g. the music is stopped."""
    READY = "ready"
    """Here is something to show."""
    ALERT = "alert"
    """Here is something to show, and it is an alert."""


@dataclass(frozen=True)
class Fetched:
    """What ``fetch`` returns: a state, and the data to draw (none for ``NOTHING``)."""

    state: State
    data: Any = None


#: ``fetch`` returns this when there is nothing to show.
NOTHING = Fetched(State.NOTHING)


def ready(data: Any) -> Fetched:
    """``fetch`` returns this when it has data to show."""
    return Fetched(State.READY, data)


def alert(data: Any) -> Fetched:
    """``fetch`` returns this when its data is an alert."""
    return Fetched(State.ALERT, data)


@dataclass(frozen=True)
class Drawn:
    """What ``draw`` returns when a plain dictionary of values is not enough."""

    values: Mapping[str, Any]
    """A value for each block of the layout, as ``draw`` normally returns."""
    seed: int | None = None
    """Makes epdlib's ``random`` alignment repeatable: the same seed puts the blocks in the
    same places. Without it, blocks with ``random`` alignment move at every update."""
    colors: tuple[str, str] | None = None
    """Text and background colour (names or ``#rrggbb``) for every block that has
    ``rgb_support``, in place of the colours in the layout. See :mod:`paperpi.colors`."""


class PluginSettings(BaseModel):
    """Base class for a plugin's own settings.

    Each setting is a field with a type, a default and a short help text::

        class Settings(PluginSettings):
            hours: Literal[12, 24] = Field(24, description="12- or 24-hour clock")

    The same description checks the config file, builds the web interface's forms (M5)
    and the docs. A plugin may not use the names of the shared settings
    (:data:`SHARED_SETTINGS`) for its own. Use :func:`setting` instead of ``Field`` for a
    setting PaperPi must know more about, such as one the user has to fill in.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)


#: The key under which :func:`setting` keeps PaperPi's own options in a pydantic field.
_OPTIONS = "paperpi"


def setting(default: Any = None, *, required: bool = False, **field: Any) -> Any:
    """A plugin setting: pydantic's ``Field`` (with the same ``description``, ``ge``,
    ``max_length``, ...) plus what PaperPi needs to know about it. This is the one place a
    setting asks PaperPi for help; later options (such as a helper that looks up a place's
    latitude and longitude in the web interface) are added here too::

        lat: float | None = setting(None, required=True, description="Latitude")

    ``required``: the plugin can't work until the user fills it in (a place, an email
    address, an API key). Its default must be "not set": ``None`` or ``""``. A plugin
    with a required setting that is not set is not shown; the config check and the web
    interface say which settings it needs.
    """
    options = {"required": True} if required else {}
    return Field(default, json_schema_extra={_OPTIONS: options} if options else None, **field)


def is_required(info: FieldInfo) -> bool:
    """True for a setting made with ``setting(required=True)``."""
    extra = info.json_schema_extra
    return isinstance(extra, dict) and bool(extra.get(_OPTIONS, {}).get("required"))


def is_set(value: Any) -> bool:
    """False for "not set": ``None``, ``""`` or an empty secret."""
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return value is not None and value != ""


class PluginEntry(BaseModel):
    """The settings every ``[[plugin]]`` block in the config file has.

    The plugin's own settings sit in the same block; they are checked by its
    :class:`PluginSettings`.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = Field(min_length=1, max_length=100, description="Unique name of this plugin")
    type: str = Field(description="Which plugin, e.g. basic_clock")
    enabled: bool = Field(True, description="Show this plugin")
    level: Literal["alert", "interrupt", "rotation"] = Field(
        "rotation", description="When it is shown: alert, interrupt or rotation"
    )
    display_time: float = Field(
        120,
        gt=0,
        le=limits.LONGEST_SETTING,
        description="Seconds on screen per turn, when several plugins take turns",
    )
    refresh: float | None = Field(
        None,
        ge=limits.SHORTEST_REFRESH,
        le=limits.LONGEST_SETTING,
        description="Seconds between updates (at least 5). Leave it out to use the plugin's "
        "suggestion (shown below)",
    )
    time_limit: float = Field(
        limits.PLUGIN_UPDATE,
        gt=0,
        le=limits.PLUGIN_UPDATE_MAX,
        description="Seconds one update may take before it is stopped",
    )
    layout: str | None = Field(
        None, description='Which layout (see "Layouts" above). Leave it out to use the first'
    )
    alert_reminder: float = Field(
        limits.ALERT_REMINDER,
        gt=0,
        le=limits.LONGEST_SETTING,
        description="Alert plugins only: seconds before a dismissed alert comes back, "
        "if the plugin still reports it",
    )
    alert_max_time: float = Field(
        limits.ALERT_MAX_TIME,
        gt=0,
        le=limits.LONGEST_SETTING,
        description="Alert plugins only: seconds after which an alert is dismissed by itself, "
        "in case the plugin is stuck",
    )

    storage_mb: int | None = Field(
        None,
        ge=1,
        le=limits.STORAGE_MB_MAX,
        description="Most megabytes this plugin may keep in its storage folder; over it, the files "
        "changed longest ago are removed first. Leave it out to use the plugin's suggestion "
        "(shown below)",
    )
    storage_days: int | None = Field(
        None,
        ge=0,
        le=limits.STORAGE_DAYS_MAX,
        description="Files the plugin has not changed for this many days are removed (0 = keep "
        "them). Leave it out to use the plugin's suggestion (shown below)",
    )

    @field_validator("name")
    @classmethod
    def _no_control_characters(cls, name: str) -> str:
        # They can't be written back to the file reliably, and would change the terminal's
        # output in ``paperpi list``.
        if re.search(r"[\x00-\x1f\x7f]", name):
            raise ValueError("must not hold control characters (such as tab or new line)")
        return name


#: Names a plugin may not use for its own settings.
SHARED_SETTINGS = frozenset(PluginEntry.model_fields)

_TYPE_NAME = re.compile(r"[a-z][a-z0-9_]*")

#: A layout is an epdlib layout dictionary, or a function that makes one from the settings
#: (for layouts that depend on a setting, such as a 12- or 24-hour clock).
LayoutSource = Mapping[str, Any] | Callable[[PluginSettings], Mapping[str, Any]]


@dataclass(frozen=True)
class PluginsStatus:
    """How many plugins are not working. The scheduler gives this to the ``default`` plugin."""

    failing: int
    """Plugins that failed their last update, or are left out after failing again and again."""
    total: int
    """Plugins that are switched on."""


@dataclass(frozen=True)
class Context:
    """What one update gets from PaperPi."""

    settings: PluginSettings
    """The plugin's own settings, already checked."""
    width: int
    """Width of the area to draw, in pixels. In v2.0 always the whole screen."""
    height: int
    """Height of the area to draw, in pixels."""
    mode: ScreenMode
    """What the screen can show: black and white, gray levels or colours."""
    storage: Path
    """The plugin's own folder for saved files, e.g. downloaded data."""
    layout: str
    """The name of the layout to draw."""
    status: PluginsStatus | None = None
    """Only for the ``default`` plugin: how many plugins are not working."""
    low_disk: bool = False
    """Less than :data:`~paperpi.limits.FREE_DISK_MB` is free on the disk that holds
    PaperPi's state folder (``/var/lib/paperpi``): don't save more
    files (e.g. don't download new photos). Files can still be replaced."""


class PluginDefinitionError(ValueError):
    """A plugin's ``PLUGIN`` breaks the rules of this interface. A bug in the plugin."""


@dataclass(frozen=True)
class Plugin:
    """Everything PaperPi needs to know about one plugin type."""

    type: str
    """The plugin type, the same as its folder name, e.g. ``basic_clock``."""
    description: str
    """One sentence: what it shows."""
    settings: type[PluginSettings]
    """Its own settings."""
    layouts: Mapping[str, LayoutSource]
    """Named layouts. The first is the default."""
    fetch: Callable[[Context], Fetched]
    """Gets the data and says whether there is something to show."""
    draw: Callable[[Any, Context], Mapping[str, Any] | Drawn]
    """Turns the data into values for the layout's blocks (or a :class:`Drawn`)."""
    sample: Any
    """Fixed example data for ``draw``, used for tests and sample images."""
    refresh: float
    """Suggested seconds between updates."""
    refresh_on_minute: bool = False
    """Updates should start just after the minute changes (for clocks)."""
    storage_mb: int = limits.STORAGE_MB
    """Suggested most megabytes in its storage folder (e.g. more for a photo album)."""
    storage_days: int = limits.STORAGE_DAYS
    """Suggested days after which its saved files are removed (0 = keep them)."""

    def __post_init__(self) -> None:
        problems = []
        if not _TYPE_NAME.fullmatch(self.type):
            problems.append("type must be lowercase letters, digits and _")
        if not (isinstance(self.settings, type) and issubclass(self.settings, PluginSettings)):
            problems.append("settings must be a subclass of PluginSettings")
        else:
            clash = sorted(SHARED_SETTINGS & set(self.settings.model_fields))
            if clash:
                problems.append(f"settings use the names of shared settings: {', '.join(clash)}")
            try:
                defaults = self.settings()
            except ValueError:
                problems.append("every setting needs a default")
            else:
                if self.missing(defaults) != self.required:
                    problems.append('a required setting\'s default must be "not set" (None or "")')
        if not self.layouts:
            problems.append("needs at least one layout")
        if not limits.SHORTEST_REFRESH <= self.refresh <= limits.LONGEST_SETTING:
            problems.append(
                f"refresh must be between {limits.SHORTEST_REFRESH:g} "
                f"and {limits.LONGEST_SETTING:g} seconds"
            )
        if not 1 <= self.storage_mb <= limits.STORAGE_MB_MAX:
            problems.append(f"storage_mb must be between 1 and {limits.STORAGE_MB_MAX}")
        if not 0 <= self.storage_days <= limits.STORAGE_DAYS_MAX:
            problems.append(f"storage_days must be between 0 and {limits.STORAGE_DAYS_MAX}")
        if problems:
            raise PluginDefinitionError(f"plugin {self.type!r}: " + "; ".join(problems))

    @property
    def default_layout(self) -> str:
        return next(iter(self.layouts))

    @property
    def required(self) -> tuple[str, ...]:
        """The settings the user has to fill in (see :func:`setting`)."""
        return tuple(k for k, info in self.settings.model_fields.items() if is_required(info))

    def missing(self, settings: PluginSettings) -> tuple[str, ...]:
        """The required settings that are not set in ``settings``."""
        return tuple(k for k in self.required if not is_set(getattr(settings, k)))

    def layout(
        self, name: str, settings: PluginSettings, colors: tuple[str, str] | None = None
    ) -> Layout:
        """The epdlib layout called ``name``, for these settings. ``colors`` (text,
        background) replaces the colours of every block that has ``rgb_support``."""
        source = self.layouts[name]
        description = source(settings) if callable(source) else source
        if colors:
            description = _recolor(description, *colors)
        return Layout(description)


def _recolor(node: Any, fill: str, background: str) -> Any:
    """A copy of a layout description with new colours for the ``rgb_support`` blocks."""
    if isinstance(node, Mapping):
        copy = {key: _recolor(value, fill, background) for key, value in node.items()}
        if copy.get("rgb_support"):
            # ``inverse`` swaps the two when drawing; swap them here too, so the block still
            # gets the text colour for its text.
            pair = (background, fill) if copy.get("inverse") else (fill, background)
            copy |= {"fill": pair[0], "background": pair[1]}
        return copy
    if isinstance(node, list | tuple):
        return type(node)(_recolor(item, fill, background) for item in node)
    return node


def draw_update(
    plugin: Plugin, context: Context, *, sample: bool
) -> tuple[State, Image.Image | None]:
    """Run one update in this process: fetch (or take the sample data) and draw.

    Returns the state and the image (``None`` when there is nothing to show). Normally this
    runs inside a plugin process started by :mod:`paperpi.runner`.
    """
    fetched = Fetched(State.READY, plugin.sample) if sample else plugin.fetch(context)
    if not isinstance(fetched, Fetched):
        raise TypeError(
            f"fetch returned {type(fetched).__name__}; use NOTHING, ready(data) or alert(data)"
        )
    if fetched.state is State.NOTHING:
        return fetched.state, None
    drawn = plugin.draw(fetched.data, context)
    if not isinstance(drawn, Drawn):
        drawn = Drawn(drawn)
    layout = plugin.layout(context.layout, context.settings, drawn.colors)
    prepared = layout.prepare(context.width, context.height, context.mode)
    image = prepared.render(dict(drawn.values), seed=drawn.seed)
    return fetched.state, image
