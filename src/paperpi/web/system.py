"""The Screen & system page: the screen PaperPi uses, the ``[display]`` settings that apply
at once, and facts about this Pi.

- The settings come in sections (:data:`SECTIONS`) in one form with one **Save and apply**
  (txoof 2026-10-23: a Save per section was easy to forget). :func:`form` gives the
  fields' values for the page, read from the config file; :func:`with_values` checks the
  sent form and writes it into ``[display]`` (:func:`config_file.set_display`).
  A value equal to its default is taken out of the file, as the file only holds values
  that differ from the defaults.
- **Change screen…** has a page of its own: :func:`screen_form` and :func:`with_screen`
  set the screen settings (:data:`SCREEN`). A new type, model, size or mode is used from
  the next start of PaperPi; until then the Screen & system page says a change is waiting
  (:func:`waiting`). The screen in use is kept in :data:`PREVIOUS_FILE` in the state
  folder, so "Go back to the previous screen" can put it back when the new one does not
  answer.
- The Web interface section sets ``[web]`` (:data:`WEB`): the log-in at once, the
  address and port at the next start. :func:`port_problem` tries the new port on this Pi
  before it is saved, so a port PaperPi can't use doesn't cost the web interface;
  :func:`web_waiting` tells when the file names another address or port than the ones in
  use.
- :func:`screen_facts` describes the screen in use (the type and model PaperPi started
  with, see ``docs/decisions/live-config-reload.md``) and :func:`pi_facts` measures this Pi
  when the page asks.
"""

from __future__ import annotations

import errno
import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from epdlib.drivers.it8951 import MODELS as IT8951_MODELS
from epdlib.drivers.it8951 import VCOM_RANGE
from pydantic import ValidationError

from .. import __version__, config, example, health
from ..files import write_atomic
from . import config_file

#: The page's sections and their ``[display]`` settings.
SECTIONS = {
    "picture": ("rotation", "color"),
    "care": ("max_refresh", "clean_every", "on_exit"),
    "splash": ("splash_time", "fallback_clock"),
}
#: The ``[display]`` settings of the screen itself, set on the Change screen page.
SCREEN = ("type", "model", "vcom", "width", "height", "mode")
#: The ``[web]`` settings of the Web interface section.
WEB = ("port", "address", "login")
#: Where the web interface can be reached from, in words.
ADDRESSES = {"0.0.0.0": "every device on your home network", "127.0.0.1": "only this Pi"}
#: The screen used before Change screen…, in the state folder.
PREVIOUS_FILE = "previous-screen.toml"
#: What a virtual screen can show, in words.
SHOWS = {
    "bw": "black and white",
    "gray4": "4 grays",
    "gray16": "16 grays",
    "7color": "7 colours",
    "rgb": "full colour",
}
#: The units "Clean the screen every" can be given in, in seconds.
CLEAN_UNITS = {"minutes": 60, "hours": 3600}
_FIELDS = config.DisplaySettings.model_fields
_WEB_FIELDS = config.WebSettings.model_fields
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
    web = web_values(text)
    shown |= {"port": _text(web["port"]), "address": str(web["address"])}
    shown["login"] = _check(web["login"])
    if clean == 0:
        return shown | {"clean_every": "1", "clean_unit": "hours", "clean_never": "true"}
    hours = isinstance(clean, int | float) and clean % 3600 == 0
    unit = "hours" if hours else "minutes"
    number = clean / CLEAN_UNITS[unit] if isinstance(clean, int | float) else clean
    return shown | {"clean_every": _text(number), "clean_unit": unit, "clean_never": "false"}


def web_values(text: str) -> dict[str, Any]:
    """The ``[web]`` settings of the config file ``text``, with the defaults for what it
    doesn't set."""
    found = config_file.load(text).get("web")
    every = {key: info.default for key, info in _WEB_FIELDS.items()}
    return every | (found if isinstance(found, dict) else {})


def with_values(
    text: str,
    sent: Mapping[str, Sequence[str]],
    started: config.WebSettings | None = None,
) -> str:
    """``text`` with the values of the sent form ``sent`` written into ``[display]`` and
    ``[web]``. ``started``: the ``[web]`` settings the web interface runs with now (see
    :func:`port_problem`). Raises :class:`SectionErrors` when a value can't be used and
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
    web = _web_changes(text, one, started, errors)
    if errors:
        raise SectionErrors(errors, one)
    every = defaults()
    changes = {
        key: None if value == every.get(key) else value
        for key, value in values.items()
        # Unchanged settings keep their lines as written (with a comment at the end).
        if value != current.get(key, every.get(key))
    }
    if changes:
        text = config_file.set_display(text, changes, every)
    if web:
        text = config_file.set_web(text, web, _web_defaults())
    return text


def _web_changes(
    text: str, sent: dict[str, str], started: config.WebSettings | None, errors: dict[str, str]
) -> dict[str, Any]:
    """The ``[web]`` settings to change for the sent form ``sent`` (``None``: back to the
    default). What can't be used goes into ``errors``."""
    current = web_values(text)
    values: dict[str, Any] = {}
    if "port" in sent:
        try:
            port = int(sent["port"].strip())
        except ValueError:
            port = 0
        if not 0 < port <= 65535:
            errors["port"] = "must be a whole number from 1 to 65535"
        values["port"] = port
    if "address" in sent:
        address = sent["address"].strip()
        # The two choices, or what the config file says now (an address set by hand).
        if address not in ADDRESSES and address != current["address"]:
            errors["address"] = "choose where the web interface can be reached from"
        values["address"] = address
    if "login" in sent:
        values["login"] = sent["login"] == "true"
    if "port" in errors or "address" in errors:
        return {}
    new = {key: value for key, value in values.items() if value != current[key]}
    if "port" in new or "address" in new:
        address, port = new.get("address", current["address"]), new.get("port", current["port"])
        problem = port_problem(address, port, started)
        if problem is not None:
            errors["port"] = problem
    if new.get("login") is True:
        # Switched on again: a password from before goes, and the next visitor sets a new
        # one (txoof 2026-10-23).
        new["password_hash"] = None
    every = _web_defaults()
    return {key: None if value == every.get(key) else value for key, value in new.items()}


def _web_defaults() -> dict[str, Any]:
    # Without password_hash: a removed password leaves no "# password_hash =" behind.
    return {key: info.default for key, info in _WEB_FIELDS.items() if key != "password_hash"}


def port_problem(address: str, port: int, started: config.WebSettings | None) -> str | None:
    """Why the web interface could not listen on ``port`` at ``address`` at the next start,
    found by trying it now; ``None``: it can. The port the web interface uses now
    (``started``) is fine: it is free again when PaperPi restarts."""
    if started is not None and port == started.port:
        return None
    from .server import listen  # here: the server module needs this one

    try:
        listen(address, port).close()
    except PermissionError:
        return (
            f"port {port} needs administrator rights, which PaperPi doesn't have. Choose "
            "1024 or higher, for example 8081"
        )
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            return (
                f"port {port} is used by another program. PaperPi couldn't use it, and you "
                "would lose this page. Choose another port"
            )
        if error.errno == errno.EADDRNOTAVAIL:
            return f"this Pi has no network address {address}"
        return f"PaperPi can't use port {port} ({error.strerror or error})"
    return None


def file_web(text: str) -> config.WebSettings | None:
    """The ``[web]`` settings in the config file ``text``; ``None``: they can't be used."""
    try:
        return config.WebSettings.model_validate(config_file.load(text).get("web") or {})
    except (ValidationError, config_file.EditError):
        return None


def web_waiting(
    file: config.WebSettings | None, used: config.WebSettings | None
) -> config.WebSettings | None:
    """The file's ``[web]`` settings when they name another address or port than the ones
    in use, so a restart is needed; else ``None``."""
    if file is None or used is None:
        return None
    if (file.address, file.port) == (used.address, used.port):
        return None
    return file


def set_web_address(text: str, used: config.WebSettings) -> str:
    """``text`` with the address and port of ``used`` in ``[web]`` again (Undo)."""
    every = _web_defaults()
    values = {key: getattr(used, key) for key in ("address", "port")}
    current = web_values(text)
    changes = {
        key: None if value == every[key] else value
        for key, value in values.items()
        if value != current[key]
    }
    return config_file.set_web(text, changes, every) if changes else text


def web_address(host: str, web: config.WebSettings) -> str:
    """The web interface's address with the settings ``web``, as a browser opens it;
    ``host`` is the Pi's address as the browser knows it now."""
    if web.address not in ("0.0.0.0", "::"):
        host = web.address
    return f"http://{f'[{host}]' if ':' in host else host}:{web.port}"


def screen_of(display: config.DisplaySettings) -> dict[str, Any]:
    """The screen settings of ``display`` that are set."""
    values = display.model_dump(include=set(SCREEN))
    return {key: value for key, value in values.items() if value is not None}


def screen_form(display: config.DisplaySettings | None) -> dict[str, str]:
    """The values of the Change screen page's fields for the screen ``display``."""
    shown = {
        "type": "it8951",
        "model": "9.7",
        "vcom": "",
        "width": str(config.VIRTUAL_WIDTH),
        "height": str(config.VIRTUAL_HEIGHT),
        "mode": config.VIRTUAL_MODE,
    }
    if display is None:
        return shown
    values = screen_of(display)
    if "vcom" in values:
        values["vcom"] = f"{values['vcom']:.2f}"
    return shown | {key: str(value) for key, value in values.items()}


def with_screen(text: str, sent: Mapping[str, Sequence[str]]) -> str:
    """``text`` with the screen of the Change screen form ``sent`` in ``[display]``. Raises
    :class:`SectionErrors` when a value can't be used and :class:`config_file.EditError`
    when the file can't be changed."""
    one = {key: (texts[-1] if texts else "").strip() for key, texts in sent.items()}
    errors: dict[str, str] = {}
    kind = one.get("type", "")
    values: dict[str, Any] = {"type": kind}
    if kind == "it8951":
        if one.get("model") not in IT8951_MODELS:
            errors["model"] = "choose one of the models"
        values["model"] = one.get("model")
        try:
            values["vcom"] = float(one.get("vcom", "").replace(",", ".").replace("−", "-"))
        except ValueError:
            values["vcom"] = None
        low, high = VCOM_RANGE
        if values["vcom"] is None or not low <= values["vcom"] <= high:
            errors["vcom"] = f"must be a number from {low:.2f} to {high:.2f}, e.g. -1.90"
    elif kind == "virtual":
        for key in ("width", "height"):
            try:
                values[key] = int(one.get(key, ""))
            except ValueError:
                values[key] = None
            if values[key] is None or not 0 < values[key] <= 10_000:
                errors[key] = "must be a whole number from 1 to 10000"
        if one.get("mode") not in SHOWS:
            errors["mode"] = "choose what the screen shows"
        values["mode"] = one.get("mode")
    else:
        errors["type"] = "choose a type"
    if errors:
        raise SectionErrors(errors, one)
    return set_screen(text, values)


def set_screen(text: str, screen: Mapping[str, Any]) -> str:
    """``text`` with ``screen`` (see :func:`screen_of`) as the screen in ``[display]``:
    screen settings it doesn't hold are taken out."""
    found = config_file.load(text).get("display")
    current = found if isinstance(found, dict) else {}
    values = {key: screen.get(key) for key in SCREEN}
    new = {key: value for key, value in (current | values).items() if value is not None}
    try:
        config.DisplaySettings.model_validate(new)
    except ValidationError as error:
        problem = error.errors()[0]
        key = str(problem["loc"][0]) if problem["loc"] else ""
        raise config_file.EditError(
            f"[display] {key} in the config file can't be used ({problem['msg']}). "
            "Fix it in the config file first."
        ) from None
    changes = {key: value for key, value in values.items() if current.get(key) != value}
    if not changes:
        return text
    # A setting that doesn't belong to the new screen goes without a comment in its place.
    every = {key: value for key, value in defaults().items() if value is not None}
    return config_file.set_display(text, changes, every)


def waiting(file: config.DisplaySettings | None, used: config.DisplaySettings | None) -> bool:
    """The config file names another screen than the one in use, so a restart is needed."""
    if file is None or used is None:
        return False
    return any(getattr(file, key) != getattr(used, key) for key in config.NEXT_START)


def describe(screen: Mapping[str, Any]) -> str:
    """A screen (see :func:`screen_of`) in a few words."""
    if screen.get("type") == "it8951":
        vcom = screen.get("vcom")
        volts = "" if vcom is None else f", {vcom:.2f} V".replace("-", "−")
        return f"IT8951, {screen.get('model')} inch{volts}"
    width = screen.get("width") or config.VIRTUAL_WIDTH
    height = screen.get("height") or config.VIRTUAL_HEIGHT
    shows = SHOWS.get(screen.get("mode") or config.VIRTUAL_MODE, "")
    return f"virtual screen, {width} × {height}, {shows}"


def previous(state_dir: Path | None) -> dict[str, Any] | None:
    """The screen used before Change screen…; ``None``: none is kept."""
    if state_dir is None:
        return None
    try:
        found = tomllib.loads((state_dir / PREVIOUS_FILE).read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    screen = {key: found[key] for key in SCREEN if key in found}
    try:
        config.DisplaySettings.model_validate(screen)
    except ValidationError:
        return None
    return screen


def keep_previous(state_dir: Path | None, screen: Mapping[str, Any]) -> None:
    """Keep ``screen`` for "Go back to the previous screen"."""
    if state_dir is None:
        return
    lines = [f"{key} = {example.toml_value(value)}\n" for key, value in screen.items()]
    note = "# The screen used before Change screen… in the web interface (PaperPi writes this)\n"
    write_atomic(state_dir / PREVIOUS_FILE, (note + "".join(lines)).encode())


def forget_previous(state_dir: Path | None) -> None:
    if state_dir is not None:
        (state_dir / PREVIOUS_FILE).unlink(missing_ok=True)


def _value(key: str, sent: dict[str, str]) -> Any:
    if key == "clean_every":
        if key not in sent and "clean_never" not in sent:
            raise KeyError(key)  # not on the form
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
