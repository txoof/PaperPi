"""The Screen & system page: the screen PaperPi uses, the ``[display]`` settings that apply
at once, and facts about this Pi.

- The settings come in sections (:data:`SECTIONS`) in one form with one **Save and apply**
  (txoof 2026-10-23: a Save per section was easy to forget). :func:`form` gives the
  fields' values for the page, read from the config file; :func:`with_values` checks the
  sent form and writes it into ``[display]`` (:func:`config_file.set_display`).
  A value equal to its default is taken out of the file, as the file only holds values
  that differ from the defaults.
- :func:`screen_facts` describes the screen in use (the type and model PaperPi started
  with, see ``docs/decisions/live-config-reload.md``) and :func:`pi_facts` measures this Pi
  when the page asks.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from epdlib.drivers.it8951 import MODELS as IT8951_MODELS
from pydantic import ValidationError

from .. import __version__, config, health
from . import config_file

#: The page's sections and their ``[display]`` settings.
SECTIONS = {
    "picture": ("rotation", "color"),
    "care": ("max_refresh", "clean_every", "on_exit"),
    "splash": ("splash_time", "fallback_clock"),
}
#: The units "Clean the screen every" can be given in, in seconds.
CLEAN_UNITS = {"minutes": 60, "hours": 3600}
_FIELDS = config.DisplaySettings.model_fields
_TEMPERATURE = Path("/sys/class/thermal/thermal_zone0/temp")


class SectionErrors(config_file.EditError):
    """Some values of the sent form can't be used; nothing was saved."""

    def __init__(self, errors: dict[str, str], values: dict[str, str]):
        super().__init__("Some values can't be used. Nothing was saved.")
        self.errors = errors
        """Setting -> what is wrong with it."""
        self.values = values
        """The sent values, to show them again."""


def defaults() -> dict[str, Any]:
    """The default of every ``[display]`` setting that has one."""
    return {key: info.default for key, info in _FIELDS.items() if not info.is_required()}


def file_display(text: str) -> config.DisplaySettings | None:
    """The ``[display]`` settings in the config file ``text``; ``None``: they can't be
    used."""
    try:
        return config.DisplaySettings.model_validate(config_file.load(text).get("display"))
    except (ValidationError, config_file.EditError):
        return None


def form(text: str) -> dict[str, str]:
    """The values of every section's fields for the page, from the config file ``text``
    (defaults for what it doesn't set)."""
    found = config_file.load(text).get("display")
    values = defaults() | (found if isinstance(found, dict) else {})
    clean = values.get("clean_every")
    shown = {
        "rotation": str(values.get("rotation")),
        "color": _check(values.get("color")),
        "max_refresh": _text(values.get("max_refresh")),
        "on_exit": str(values.get("on_exit")),
        "splash_time": _text(values.get("splash_time")),
        "fallback_clock": _check(values.get("fallback_clock")),
    }
    if clean == 0:
        return shown | {"clean_every": "1", "clean_unit": "hours", "clean_never": "true"}
    hours = isinstance(clean, int | float) and clean % 3600 == 0
    unit = "hours" if hours else "minutes"
    number = clean / CLEAN_UNITS[unit] if isinstance(clean, int | float) else clean
    return shown | {"clean_every": _text(number), "clean_unit": unit, "clean_never": "false"}


def with_values(text: str, sent: Mapping[str, Sequence[str]]) -> str:
    """``text`` with the values of the sent form ``sent`` written into ``[display]``.
    Raises :class:`SectionErrors` when a value can't be used and
    :class:`config_file.EditError` when the file can't be changed."""
    one = {key: (texts[-1] if texts else "") for key, texts in sent.items()}
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key in (key for keys in SECTIONS.values() for key in keys):
        try:
            values[key] = _value(key, one)
        except ValueError as error:
            errors[key] = str(error)
        except KeyError:
            pass  # not on the form (colour on a screen without colour)
    found = config_file.load(text).get("display")
    current = found if isinstance(found, dict) else {}
    try:
        config.DisplaySettings.model_validate(current | values)
    except ValidationError as error:
        for problem in error.errors():
            key = str(problem["loc"][0]) if problem["loc"] else ""
            if key == "clean_every":
                errors.setdefault(key, "must be at least 10 minutes, or Never")
            elif key in values:
                errors.setdefault(key, _message(problem["msg"]))
            elif key not in errors:
                raise config_file.EditError(
                    f"[display] {key} in the config file can't be used ({problem['msg']}). "
                    "Fix it in the config file first."
                ) from None
    if errors:
        raise SectionErrors(errors, one)
    every = defaults()
    changes = {
        key: None if value == every.get(key) else value
        for key, value in values.items()
        # Unchanged settings keep their lines as written (with a comment at the end).
        if value != current.get(key, every.get(key))
    }
    if not changes:
        return text
    return config_file.set_display(text, changes, every)


def _value(key: str, sent: dict[str, str]) -> Any:
    if key == "clean_every":
        if sent.get("clean_never") == "true":
            return 0
        unit = sent.get("clean_unit", "")
        if unit not in CLEAN_UNITS:
            raise ValueError("choose minutes or hours")
        return _number(sent[key], whole=False) * CLEAN_UNITS[unit]
    text = sent[key].strip()
    if key in ("color", "fallback_clock"):
        return text == "true"
    if key == "rotation":
        if text not in ("0", "90", "180", "270"):
            raise ValueError("choose one of the four turns")
        return int(text)
    if key == "on_exit":
        return text
    return _number(text, whole=key == "max_refresh")


def _number(text: str, whole: bool) -> float | int:
    text = text.strip().replace(",", ".")
    try:
        number = int(text) if whole else float(text)
    except ValueError:
        raise ValueError("must be a whole number" if whole else "must be a number") from None
    if not whole and number.is_integer():
        return int(number)
    return number


def _message(text: str) -> str:
    # Pydantic's "Value error, must be ..." -> "must be ..."
    return text.removeprefix("Value error, ")


def _text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _check(value: Any) -> str:
    return "true" if value is True else "false"


@dataclass(frozen=True)
class ScreenFacts:
    """The screen in use, for the Screen section."""

    type: str
    model: str
    vcom: str | None
    shows_color: bool
    """The screen can show colour, so the Colour setting is offered."""
    shows: str
    """What it can show, e.g. "16 grays"."""


def screen_facts(display: config.DisplaySettings) -> ScreenFacts:
    width, height = display.size
    if display.type == "it8951":
        mode = IT8951_MODELS[display.model or "9.7"].mode
        kind, model = "Waveshare IT8951 board", f"{display.model} inch, {width} × {height}"
    else:
        mode = config.MODES[display.mode or config.VIRTUAL_MODE]
        kind, model = "Virtual screen (writes PNG files)", f"{width} × {height}"
    shows = {
        "bw": "black and white",
        "gray": f"{mode.levels} grays",
        "palette": f"{mode.levels} colours",
        "rgb": "full colour",
    }.get(mode.kind, config.mode_name(mode))
    vcom = None if display.vcom is None else f"{display.vcom:.2f} V".replace("-", "−")
    return ScreenFacts(kind, f"{model}, {shows}", vcom, mode.kind in ("palette", "rgb"), shows)


@dataclass(frozen=True)
class PiFacts:
    """This Pi and PaperPi, measured when the page asks. ``None``: can't be measured."""

    version: str
    running_for: str | None
    last_write: str | None
    memory: str | None
    free_disk: str | None
    temperature: str | None


def pi_facts(state_dir: Path | None, written_at: datetime | None) -> PiFacts:
    """Measure this Pi now; ``written_at`` is the last screen write (from the scheduler)."""
    disk = health.free_disk_mb(state_dir) if state_dir is not None else None
    memory = health.memory_mb()
    return PiFacts(
        version=__version__,
        running_for=_duration(_running_seconds()),
        last_write=_when(written_at),
        memory=None if memory is None else f"{memory:.0f} MB",
        free_disk=None if disk is None else _size(disk),
        temperature=_temperature(),
    )


def _running_seconds() -> float | None:
    """How long this process has run, from Linux's process table."""
    try:
        stat = Path("/proc/self/stat").read_text()
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        # The fields after the program name, which is in brackets and may hold spaces.
        start_ticks = int(stat.rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        return None
    return uptime - start_ticks / os.sysconf("SC_CLK_TCK")


def _duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    minutes = int(seconds // 60)
    days, hours, minutes = minutes // 1440, minutes // 60 % 24, minutes % 60
    if days:
        return f"{days} d {hours} h"
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


def _when(at: datetime | None) -> str | None:
    if at is None:
        return None
    if at.date() == datetime.now().date():
        return at.strftime("%H:%M")
    return at.strftime("%d %b %H:%M")


def _size(megabytes: float) -> str:
    return f"{megabytes / 1000:.1f} GB" if megabytes >= 1000 else f"{megabytes:.0f} MB"


def _temperature() -> str | None:
    try:
        return f"{int(_TEMPERATURE.read_text()) / 1000:.0f} °C"
    except (OSError, ValueError):
        return None
