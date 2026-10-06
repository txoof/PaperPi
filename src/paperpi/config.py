"""The config file: reading it, checking it, and the last good copy.

The reasons behind this design are in ``docs/decisions/config-format.md``. In short:

- One TOML file, ``/etc/paperpi/paperpi.toml``, that holds only values that differ from
  the defaults.
- It is checked when it is loaded. Every problem names the line and the setting.
- What happens when something is wrong:

  ========================================  ==================================================
  Problem                                   What PaperPi does
  ========================================  ==================================================
  file can't be read, is not valid TOML,    :func:`load` uses the last good copy and reports
  or ``config_version``, ``[display]`` or   the problems; with no last good copy it raises
  ``web`` is wrong                          :class:`ConfigError`
  one ``[[plugin]]`` block is wrong         only that plugin is left out
  unknown setting                           a warning, with "did you mean ...?"
  ``refresh`` equals ``display_time``       a hint (see ``plugin-scheduling.md``)
  ========================================  ==================================================

- Each time the file loads without errors, a copy is saved as the last good copy.
"""

from __future__ import annotations

import difflib
import logging
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from epdlib import ScreenMode
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import limits, plugins
from .files import write_atomic
from .plugin import SHARED_SETTINGS, Plugin, PluginDefinitionError, PluginEntry, PluginSettings

log = logging.getLogger(__name__)

CONFIG_FILE = Path("/etc/paperpi/paperpi.toml")
STATE_DIR = Path("/var/lib/paperpi")
LAST_GOOD_NAME = "paperpi.last-good.toml"

#: The config file layout this PaperPi reads (``config_version`` in the file).
CONFIG_VERSION = 1

#: Screen types PaperPi knows. Real screens are added with their drivers (M4 part 2).
DISPLAY_TYPES = ("virtual",)

#: Colour modes a virtual screen can have, and what they mean in epdlib.
MODES = {
    "bw": ScreenMode.bw(),
    "gray4": ScreenMode.gray(4),
    "gray16": ScreenMode.gray(16),
    "7color": ScreenMode.palette(),
    "rgb": ScreenMode.rgb(),
}


def mode_name(mode: ScreenMode) -> str:
    """The short name of a screen mode, as in the config file: ``gray16``, ``7color``, ..."""
    for name, known in MODES.items():
        if known == mode:
            return name
    return f"{mode.kind}{mode.levels}"


#: A virtual screen without a size or mode is like the 9.7" IT8951 screen.
VIRTUAL_WIDTH, VIRTUAL_HEIGHT, VIRTUAL_MODE = 1200, 825, "gray16"

_TOP_LEVEL = ("config_version", "display", "web", "plugin")
_VIRTUAL_ONLY = ("width", "height", "mode")


class DisplaySettings(BaseModel):
    """The ``[display]`` part of the config file."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    type: str = Field(description='The screen model, or "virtual" (writes PNG files)')
    rotation: Literal[0, 90, 180, 270] = Field(0, description="Turn the picture, in degrees")
    color: bool = Field(True, description="false: draw in gray, even on a color screen")
    fallback_clock: bool = Field(
        True,
        description="Show a small clock when no plugin has anything to show (strongly "
        "recommended: without it, an empty screen looks like a broken one)",
    )
    width: int | None = Field(
        None, gt=0, le=10_000, description="Virtual screen only: width in pixels"
    )
    height: int | None = Field(
        None, gt=0, le=10_000, description="Virtual screen only: height in pixels"
    )
    mode: Literal["bw", "gray4", "gray16", "7color", "rgb"] | None = Field(
        None, description="Virtual screen only: what it can show"
    )

    @property
    def size(self) -> tuple[int, int]:
        """The screen's width and height in pixels, before rotation."""
        return (self.width or VIRTUAL_WIDTH, self.height or VIRTUAL_HEIGHT)

    @property
    def layout_size(self) -> tuple[int, int]:
        """The width and height plugins draw at: turned when the screen is rotated 90 or 270."""
        width, height = self.size
        return (height, width) if self.rotation in (90, 270) else (width, height)

    @property
    def screen_mode(self) -> ScreenMode:
        """What plugins draw in, with ``color = false`` applied."""
        mode = MODES[self.mode or VIRTUAL_MODE]
        if not self.color and mode.kind == "palette":
            return ScreenMode.bw()
        if not self.color and mode.kind == "rgb":
            return ScreenMode.gray(256)
        return mode


@dataclass(frozen=True)
class Problem:
    """One thing wrong with the config file."""

    level: Literal["error", "warning", "hint"]
    message: str
    source: str = "config"
    """The file name."""
    line: int | None = None
    where: str = ""
    """Which part of the file: ``[display]``, ``[[plugin]] 'Clock'``, ..."""

    def __str__(self) -> str:
        place = self.source if self.line is None else f"{self.source} line {self.line}"
        where = f" {self.where}" if self.where else ""
        return f"{place}{where}: {self.message}"


class ConfigError(ValueError):
    """The config file can't be used at all."""

    def __init__(self, problems: list[Problem]):
        super().__init__("\n".join(str(p) for p in problems))
        self.problems = problems


@dataclass(frozen=True)
class PluginConfig:
    """One checked ``[[plugin]]`` block."""

    entry: PluginEntry
    """The shared settings: name, type, level, ..."""
    settings: PluginSettings
    """The plugin's own settings."""
    plugin: Plugin
    line: int | None = None

    @property
    def refresh(self) -> float:
        """Seconds between updates: the user's choice, or the plugin's suggestion."""
        return self.entry.refresh if self.entry.refresh is not None else self.plugin.refresh

    @property
    def layout(self) -> str:
        return self.entry.layout or self.plugin.default_layout

    @property
    def folder_name(self) -> str:
        """The name of this plugin's storage folder, made from its name."""
        return folder_name(self.entry.name)


@dataclass
class Config:
    """A loaded config file."""

    display: DisplaySettings
    plugins: list[PluginConfig]
    """The plugin blocks without errors, in file order (also the ones switched off)."""
    problems: list[Problem] = field(default_factory=list)
    from_last_good: bool = False
    """True when the file was wrong and the last good copy is used instead."""

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level == "error"]

    def plugin(self, name: str) -> PluginConfig:
        """The plugin block called ``name``. Raises ``KeyError`` if there is none."""
        for plugin in self.plugins:
            if plugin.entry.name == name:
                return plugin
        raise KeyError(name)


@dataclass(frozen=True)
class PluginRow:
    """One configured plugin, as the plugin list shows it."""

    name: str
    type: str
    enabled: bool
    level: str
    display_time: float
    refresh: float
    """As used: the setting, or the plugin's suggestion."""
    layout: str
    """As used: the setting, or the plugin's first layout."""


def plugin_rows(config: Config) -> list[PluginRow]:
    """The plugins of ``config``, in file order: for ``paperpi list`` and the web
    interface's plugin list. Blocks with errors are not in it; ``config.problems`` says
    what is wrong with them."""
    return [
        PluginRow(
            name=p.entry.name,
            type=p.plugin.type,
            enabled=p.entry.enabled,
            level=p.entry.level,
            display_time=p.entry.display_time,
            refresh=p.refresh,
            layout=p.layout,
        )
        for p in config.plugins
    ]


def folder_name(name: str) -> str:
    """A safe folder name for a plugin name: ``"Weather Berlin"`` -> ``weather-berlin``."""
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "plugin"


def load(path: Path = CONFIG_FILE, *, state_dir: Path | None = STATE_DIR) -> Config:
    """Read and check the config file.

    When the file can't be used, the last good copy in ``state_dir`` is used instead and
    ``from_last_good`` is set; the file's problems are in ``problems``. Without a last good
    copy, :class:`ConfigError` is raised. Each load without errors saves a new last good
    copy. ``state_dir=None`` turns the last good copy off (for previews and tests).
    """
    path = Path(path)
    last_good = None if state_dir is None else Path(state_dir) / LAST_GOOD_NAME
    try:
        text = read_text(path)
        config = parse(text, path.name)
    except ConfigError as error:
        if last_good is None or not last_good.is_file():
            raise
        try:
            config = parse(read_text(last_good), last_good.name)
        except ConfigError:
            log.error("the last good copy %s can't be used either", last_good)
            raise error from None
        config.from_last_good = True
        config.problems = [
            *error.problems,
            Problem("warning", f"{path} can't be used; running on the last good copy", path.name),
        ]
        _log_problems(config.problems)
        return config
    _log_problems(config.problems)
    if last_good is not None and not config.errors:
        _save_last_good(text, last_good)
    return config


def read_text(path: Path) -> str:
    """Read a config file as text, with a size limit. Problems raise :class:`ConfigError`."""
    try:
        with open(path, "rb") as file:
            data = file.read(limits.CONFIG_FILE_BYTES + 1)
    except FileNotFoundError:
        raise ConfigError([Problem("error", "file not found", str(path))]) from None
    except OSError as error:
        raise ConfigError([Problem("error", f"can't read: {error}", str(path))]) from None
    if len(data) > limits.CONFIG_FILE_BYTES:
        problem = f"file is larger than {limits.CONFIG_FILE_BYTES} bytes"
        raise ConfigError([Problem("error", problem, str(path))])
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        problem = f"not UTF-8 text (byte {error.start})"
        raise ConfigError([Problem("error", problem, str(path))]) from None


def parse(text: str, source: str = "config") -> Config:
    """Check config file text. Raises :class:`ConfigError` when it can't be used at all."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        found = re.search(r"\(at line (\d+), column \d+\)", str(error))
        line = int(found.group(1)) if found else None
        problem = f"not valid TOML: {error}"
        raise ConfigError([Problem("error", problem, source, line)]) from None
    except (RecursionError, ValueError) as error:
        # E.g. lists nested thousands deep, or a number with thousands of digits.
        problem = f"not valid TOML: {type(error).__name__}: {str(error)[:200]}"
        raise ConfigError([Problem("error", problem, source)]) from None
    return _Checker(text, source).check(data)


def _log_problems(problems: list[Problem]) -> None:
    for problem in problems:
        if problem.level == "error":
            log.error("%s", problem)
        elif problem.level == "hint":
            log.warning("hint: %s", problem)
        else:
            log.warning("%s", problem)


def _save_last_good(text: str, last_good: Path) -> None:
    try:
        last_good.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Temporary files left by a power cut during an earlier save.
        for old in last_good.parent.glob(f".{last_good.name}.*.tmp"):
            old.unlink(missing_ok=True)
        if last_good.is_file() and last_good.read_bytes() == text.encode("utf-8"):
            return
        write_atomic(last_good, text.encode("utf-8"))
    except OSError as error:
        log.warning("can't save the last good copy of the config to %s: %s", last_good, error)


def _is_secret(model: type[BaseModel], key: str) -> bool:
    """True for settings such as API keys and passwords, whose values are never shown."""
    field = model.model_fields.get(key)
    annotation = repr(field.annotation) if field else ""
    return "SecretStr" in annotation or "SecretBytes" in annotation


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _did_you_mean(word: str, choices: Iterable[str]) -> str:
    close = difflib.get_close_matches(word, list(choices), n=1, cutoff=0.6)
    return f" (did you mean {close[0]!r}?)" if close else ""


class _Checker:
    """Checks the data of one config file and collects the problems."""

    def __init__(self, text: str, source: str):
        self.source = source
        self.lines = _key_lines(text)
        self.problems: list[Problem] = []
        self.available = plugins.available()

    def add(self, level, message, section=(), key=None, where="") -> None:
        line = self.lines.get((*section, key)) or self.lines.get(section)
        self.problems.append(Problem(level, message, self.source, line, where))

    def add_validation(
        self, error: ValidationError, model: type[BaseModel], section=(), where="", input_keys=()
    ) -> None:
        for item in error.errors():
            key = str(item["loc"][0]) if item["loc"] else None
            if item["type"] == "missing":
                message = f"{key}: required setting is missing"
            else:
                message = f"{key}: {item['msg']}" if key else item["msg"]
                if key in input_keys and not _is_secret(model, key):
                    message += f" (got {_short(item['input'])})"
            self.add("error", message, section, key, where)

    def check(self, data: dict[str, Any]) -> Config:
        for key in data:
            if key not in _TOP_LEVEL:
                self.add(
                    "warning", f"unknown setting {key!r}{_did_you_mean(key, _TOP_LEVEL)}", key=key
                )
        display = self.check_file_level(data)
        if any(p.level == "error" for p in self.problems):
            raise ConfigError(self.problems)
        found = self.check_plugins(data.get("plugin", []))
        return Config(display, found, self.problems)

    def check_file_level(self, data: dict[str, Any]) -> DisplaySettings | None:
        version = data.get("config_version")
        if version is None:
            self.add("error", f"config_version = {CONFIG_VERSION} is missing at the top")
        elif not isinstance(version, int) or isinstance(version, bool) or version < 1:
            self.add(
                "error",
                f"config_version must be a whole number, got {version!r}",
                key="config_version",
            )
        elif version > CONFIG_VERSION:
            self.add(
                "error",
                f"config_version {version} was written by a newer PaperPi; "
                f"this one reads version {CONFIG_VERSION}",
                key="config_version",
            )

        section = ("display",)
        display = data.get("display")
        if not isinstance(display, dict):
            self.add("error", 'a [display] part is needed, e.g. type = "virtual"')
            return None
        for key in display:
            if key not in DisplaySettings.model_fields:
                hint = _did_you_mean(key, DisplaySettings.model_fields)
                self.add("warning", f"unknown setting {key!r}{hint}", section, key, "[display]")
        try:
            settings = DisplaySettings.model_validate(display)
        except ValidationError as error:
            self.add_validation(error, DisplaySettings, section, "[display]", display.keys())
            return None
        if settings.type not in DISPLAY_TYPES:
            known = ", ".join(DISPLAY_TYPES)
            hint = _did_you_mean(settings.type, DISPLAY_TYPES)
            self.add(
                "error",
                f"unknown screen type {settings.type!r}{hint}; known: {known}",
                section,
                "type",
                "[display]",
            )
        elif settings.type != "virtual":
            for key in _VIRTUAL_ONLY:
                if key in display:
                    self.add(
                        "error",
                        f'{key} is only for type = "virtual"; a real screen\'s '
                        "size and colours come from its model",
                        section,
                        key,
                        "[display]",
                    )
        if not settings.fallback_clock:
            self.add(
                "hint",
                "fallback_clock = false is not recommended: when no plugin has anything to "
                "show, the screen keeps its last picture, which can't be told apart from a "
                "screen that stopped working",
                section,
                "fallback_clock",
                "[display]",
            )
        if "web" in data and not isinstance(data["web"], dict):
            self.add("error", "web must be a [web] part", key="web")
        return settings

    def check_plugins(self, blocks: Any) -> list[PluginConfig]:
        if not isinstance(blocks, list):
            self.add("error", "write [[plugin]] (two brackets) above each plugin", key="plugin")
            return []
        if len(blocks) > limits.PLUGIN_BLOCKS:
            self.add(
                "error",
                f"{len(blocks)} plugin blocks; at most {limits.PLUGIN_BLOCKS} are used, "
                "the rest are left out",
                key="plugin",
            )
            blocks = blocks[: limits.PLUGIN_BLOCKS]
        found: list[PluginConfig] = []
        names: dict[str, int | None] = {}
        for index, block in enumerate(blocks):
            section = ("plugin", index)
            if not isinstance(block, dict):
                self.add("error", "each plugin must be a [[plugin]] block", key="plugin")
                continue
            name = block.get("name")
            if isinstance(name, str):
                # Checked for every block, also broken ones, so fixing one block can't
                # silently switch off another.
                folder = folder_name(name)
                if folder in names:
                    used = names[folder]
                    at = f" at line {used}" if used else ""
                    self.add(
                        "error",
                        f"name {name!r} is already used by the plugin block{at}; "
                        "names must be different (also ignoring capitals and punctuation)",
                        section,
                        "name",
                        f"[[plugin]] {name!r}",
                    )
                    continue
                names[folder] = self.lines.get(section)
            checked = self.check_plugin(block, section)
            if checked is not None:
                found.append(checked)
        return found

    def check_plugin(self, block: dict[str, Any], section: tuple) -> PluginConfig | None:
        name = block.get("name")
        where = f"[[plugin]] {name!r}" if isinstance(name, str) else f"[[plugin]] {section[1] + 1}"
        errors_before = len(self.problems)

        def failed() -> bool:
            return any(p.level == "error" for p in self.problems[errors_before:])

        try:
            entry = PluginEntry.model_validate(block)
        except ValidationError as error:
            self.add_validation(error, PluginEntry, section, where, block.keys())
            entry = None
        plugin_type = block.get("type")
        plugin = None
        if isinstance(plugin_type, str):
            try:
                if plugin_type not in self.available:
                    raise KeyError(plugin_type)
                plugin = plugins.load(plugin_type)
            except KeyError:
                hint = _did_you_mean(plugin_type, self.available)
                self.add(
                    "error",
                    f"unknown plugin type {plugin_type!r}{hint}; known: "
                    f"{', '.join(self.available)}",
                    section,
                    "type",
                    where,
                )
            except PluginDefinitionError as error:
                self.add("error", f"the plugin itself is broken: {error}", section, "type", where)
            except Exception as error:  # noqa: BLE001 - a bug in one plugin only stops that one
                message = f"the plugin itself is broken: {type(error).__name__}: {error}"
                self.add("error", message, section, "type", where)
        if plugin is None:
            return None

        own = {k: v for k, v in block.items() if k not in SHARED_SETTINGS}
        for key in own:
            if key not in plugin.settings.model_fields:
                choices = [*SHARED_SETTINGS, *plugin.settings.model_fields]
                hint = _did_you_mean(key, choices)
                self.add("warning", f"unknown setting {key!r}{hint}", section, key, where)
        try:
            settings = plugin.settings.model_validate(own)
        except ValidationError as error:
            self.add_validation(error, plugin.settings, section, where, own.keys())
            settings = None
        if entry is not None and entry.layout is not None and entry.layout not in plugin.layouts:
            self.add(
                "error",
                f"unknown layout {entry.layout!r}; choose from: {', '.join(plugin.layouts)}",
                section,
                "layout",
                where,
            )
        if entry is None or settings is None or failed():
            return None

        checked = PluginConfig(entry, settings, plugin, self.lines.get(section))
        if entry.level == "rotation" and checked.refresh == entry.display_time:
            key = "refresh" if "refresh" in block else "display_time"
            self.add(
                "hint",
                "refresh equals display time: the plugin may redraw just as it is "
                "swapped out; make refresh slightly longer, or a fraction of the display "
                "time",
                section,
                key,
                where,
            )
        return checked


_HEADER = re.compile(r"\s*(\[\[?)\s*([A-Za-z0-9_.-]+)\s*\]\]?\s*(#.*)?")
_KEY = re.compile(r"\s*([A-Za-z0-9_-]+)\s*=")


def _key_lines(text: str) -> dict[tuple, int]:
    """Line numbers of the parts and settings in a TOML file, for error messages.

    Keys: ``("display",)`` for the ``[display]`` header, ``("display", "type")`` for a
    setting in it, ``("plugin", 0)`` for the first ``[[plugin]]`` and ``("plugin", 0,
    "name")`` for a setting in it; settings at the top have just their name. Simple on
    purpose: it understands the plain ``key = value`` lines people write. For anything else
    the messages fall back to the line of the part the setting is in.
    """
    lines: dict[tuple, int] = {}
    counts: dict[str, int] = {}
    section: tuple = ()
    quote = None  # inside a multi-line string: the quotes it started with (""" or ''')
    for number, line in enumerate(text.splitlines(), start=1):
        starts_inside = quote is not None
        for found in re.finditer(r'"""|\'\'\'', line):
            if quote is None:
                quote = found.group()
            elif found.group() == quote:
                quote = None
        if starts_inside:
            continue
        header = _HEADER.fullmatch(line)
        if header:
            brackets, name = header.group(1), header.group(2)
            if brackets == "[[":
                counts[name] = counts.get(name, -1) + 1
                section = (name, counts[name])
            else:
                section = (name,)
            lines.setdefault(section, number)
            continue
        key = _KEY.match(line)
        if key:
            lines.setdefault((*section, key.group(1)), number)
    return lines
