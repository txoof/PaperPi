"""Keep these settings: new web settings are on trial after a restart (M5 part 5-3b).

When a new address or port is saved on the Screen & system page, the ones in use are kept
in :data:`PREVIOUS_FILE` in the state folder. At the next start the web interface opens at
the new address, and every page shows **Keep these settings** with the time left. When
nobody presses it within :data:`~paperpi.limits.KEEP_WEB` seconds, PaperPi writes the old
address and port back into the config file and moves the web interface there, without a
restart (it works the same when PaperPi was started by hand). When the new port can't be
opened at the start, it goes back at once. Either way, the Warnings page says so until it
is seen (:attr:`Keeper.note`).

A restart while the new settings wait starts the time again: the kept file is still there.
"""

from __future__ import annotations

import logging
import threading
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from .. import config, example, limits
from ..files import write_atomic
from .system import ADDRESSES

log = logging.getLogger(__name__)

#: The web address and port used before a new one was saved, in the state folder.
PREVIOUS_FILE = "previous-web.toml"
_KEPT = ("address", "port")


def previous(state_dir: Path | None, used: config.WebSettings) -> config.WebSettings | None:
    """``used`` with the address and port kept before a new one was saved; ``None``: none
    is kept."""
    if state_dir is None:
        return None
    try:
        found = tomllib.loads((state_dir / PREVIOUS_FILE).read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    kept = {key: found[key] for key in _KEPT if key in found}
    try:
        config.WebSettings.model_validate(kept)
    except ValidationError:
        return None
    return used.model_copy(update=kept) if len(kept) == len(_KEPT) else None


def remember(state_dir: Path | None, web: config.WebSettings) -> None:
    """Keep the address and port of ``web`` to go back to."""
    if state_dir is None:
        return
    lines = [f"{key} = {example.toml_value(getattr(web, key))}\n" for key in _KEPT]
    note = "# The web address used before a new one was saved (PaperPi writes this)\n"
    write_atomic(state_dir / PREVIOUS_FILE, (note + "".join(lines)).encode())


def forget(state_dir: Path | None) -> None:
    if state_dir is not None:
        (state_dir / PREVIOUS_FILE).unlink(missing_ok=True)


def same_address(a: config.WebSettings, b: config.WebSettings) -> bool:
    return (a.address, a.port) == (b.address, b.port)


def describe(web: config.WebSettings) -> str:
    """Where ``web`` puts the web interface, in words."""
    return f"port {web.port}, for {ADDRESSES.get(web.address, f'address {web.address}')}"


class Keeper:
    """The web settings in use, and the old ones to go back to while new ones are on
    trial. :class:`~paperpi.web.server.WebServer` sets :attr:`go_back`."""

    def __init__(self, used: config.WebSettings | None, state_dir: Path | None = None):
        self.used = used
        """The ``[web]`` settings of the address the web interface listens on now."""
        self.state_dir = state_dir
        self.old: config.WebSettings | None = None
        """The settings to go back to; ``None``: nothing is on trial."""
        self.note: str | None = None
        """Why the web interface went back, for the Warnings page; ``None`` once seen."""
        self.go_back: Callable[[str], None] | None = None
        """Writes :attr:`old` back and moves the web interface there; gets the reason."""
        self._deadline = 0.0
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def on_trial(self) -> bool:
        return self.old is not None

    def seconds_left(self) -> int:
        return max(0, round(self._deadline - time.monotonic()))

    def start_trial(self, old: config.WebSettings, seconds: float = limits.KEEP_WEB) -> None:
        with self._lock:
            self.old = old
            self._deadline = time.monotonic() + seconds
            self._timer = threading.Timer(seconds, self._ran_out)
            self._timer.daemon = True
            self._timer.start()

    def end_trial(self) -> config.WebSettings | None:
        """Stop the time; returns the settings that were kept to go back to."""
        with self._lock:
            old, self.old = self.old, None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            return old

    def keep(self) -> bool:
        """Keep the new settings (**Keep these settings**); False: none were on trial."""
        if self.end_trial() is None:
            return False
        forget(self.state_dir)
        log.info("the new web settings are kept: %s", describe(self.used))
        return True

    def back_now(self) -> None:
        """Go back in a moment (**Go back … now**): the answer to the browser goes first."""
        if self.on_trial and self.go_back is not None:
            later = threading.Timer(1.0, self.go_back, ("asked",))
            later.daemon = True
            later.start()

    def saved(self, file: config.WebSettings | None) -> None:
        """The config file's ``[web]`` settings are now ``file`` (after a save or Undo). A
        new address keeps the one in use, which works; while new settings are on trial,
        the old ones stay kept instead."""
        if file is None or self.used is None or self.on_trial:
            return
        if same_address(file, self.used):
            forget(self.state_dir)
        else:
            remember(self.state_dir, self.used)

    def stop(self) -> None:
        self.end_trial()

    def _ran_out(self) -> None:
        if self.on_trial and self.go_back is not None:
            self.go_back("time")


#: Why the web interface went back, for the Warnings page and the log.
REASONS = {
    "time": "nobody pressed Keep these settings within {minutes} minutes after the restart",
    "asked": "you pressed Go back now",
    "port": "the new address can't be used ({error})",
}


def reason(why: str, old: config.WebSettings, error: str = "") -> str:
    text = REASONS[why].format(minutes=round(limits.KEEP_WEB / 60), error=error)
    return f"The web interface went back to {describe(old)}: {text}."
