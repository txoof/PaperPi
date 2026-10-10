"""Previews: draw a plugin with the settings in its form, before they are saved.

See ``docs/decisions/web-interface.md``. A preview runs one update in its own process with a
time limit, as the scheduler does (:func:`paperpi.runner.run_update`), at the screen's size
and for the screen's type. The real screen is not touched. Each preview gets a new, empty
storage folder that is deleted afterwards, so a preview can't change the plugin's saved
files.

A preview first tries the plugin's real data, for at most :data:`~paperpi.limits.PREVIEW_LIVE`
seconds (or the plugin's own time limit, if that is shorter). When that fails, takes too long
or has nothing to show, or a required setting is missing, it draws the plugin's sample data
instead and says why.

Only one preview is drawn at a time: each one starts a Python process and may wait for a
web server, and a phone may press the button more than once. A second preview meanwhile gets
:class:`Busy`.
"""

from __future__ import annotations

import base64
import io
import logging
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from epdlib import ScreenMode

from .. import limits
from ..config import PluginConfig
from ..plugin import Context, State
from ..runner import PluginFailed, PluginTimeout, UpdateResult, run_update

log = logging.getLogger(__name__)

#: Runs one update: ``update(plugin_type, context, sample=..., time_limit=...)``, as
#: :func:`paperpi.runner.run_update`. Tests pass a quick fake.
Update = Callable[..., UpdateResult]


class Busy(RuntimeError):
    """Another preview is being drawn now."""


class PreviewFailed(RuntimeError):
    """Neither the real data nor the sample data could be drawn."""


@dataclass(frozen=True)
class Job:
    """What to draw: one checked plugin block, as Save would write it, and the screen."""

    found: PluginConfig
    width: int
    height: int
    mode: ScreenMode


@dataclass(frozen=True)
class Preview:
    """A drawn preview."""

    png: bytes
    sample: bool
    """Drawn from the plugin's sample data, not real data."""
    note: str
    """Why the sample data was drawn (empty for real data)."""
    alert: bool
    """The plugin said its picture is an alert."""
    seconds: float
    """How long drawing took, in all."""

    @property
    def data_url(self) -> str:
        """The picture as a ``data:`` address, to show it in the page itself."""
        return "data:image/png;base64," + base64.b64encode(self.png).decode("ascii")


class Previewer:
    """Draws previews, one at a time."""

    def __init__(self, update: Update = run_update):
        self._update = update
        self._lock = threading.Lock()
        self._stopped = threading.Event()

    def stop(self) -> None:
        """PaperPi stops: start no more plugin processes for previews. (A running one is
        stopped by :func:`paperpi.runner.stop_all`.)"""
        self._stopped.set()

    def draw(self, job: Job) -> Preview:
        """Draw ``job``. Raises :class:`Busy` while another preview is drawn and
        :class:`PreviewFailed` when nothing could be drawn. Can take up to about
        :data:`~paperpi.limits.PREVIEW_LIVE` + :data:`~paperpi.limits.PREVIEW_SAMPLE`
        seconds, so call it from a worker thread."""
        if not self._lock.acquire(blocking=False):
            raise Busy("Another preview is being drawn. Wait a moment, then try again.")
        try:
            self._check_stopped()
            with tempfile.TemporaryDirectory(prefix="paperpi-preview-") as storage:
                return self._draw(job, Path(storage))
        finally:
            self._lock.release()

    def _check_stopped(self) -> None:
        if self._stopped.is_set():
            raise PreviewFailed("PaperPi is stopping, so no preview can be drawn now.")

    def _draw(self, job: Job, storage: Path) -> Preview:
        found = job.found
        plugin_type = found.plugin.type
        context = Context(found.settings, job.width, job.height, job.mode, storage, found.layout)
        start = time.monotonic()
        failed = False  # the real data failed (not: it wasn't tried, or had nothing)
        if found.missing:
            note = f"Real data needs these settings first: {', '.join(found.missing)}."
        else:
            time_limit = min(found.entry.time_limit, limits.PREVIEW_LIVE)
            try:
                result = self._update(plugin_type, context, sample=False, time_limit=time_limit)
            except PluginTimeout as error:
                note = f"The real data took longer than {time_limit:g} seconds."
                failed = True
                _log_details(found, error)
            except PluginFailed as error:
                note = f"The real data could not be drawn: {_sentence(error.reason)}"
                failed = True
                _log_details(found, error)
            else:
                if result.state is not State.NOTHING and result.image is not None:
                    return _preview(result, sample=False, note="", start=start)
                note = "The plugin has nothing to show right now, so the screen would skip it."
        self._check_stopped()  # e.g. stop_all ended the real data's process
        try:
            result = self._update(
                plugin_type, context, sample=True, time_limit=limits.PREVIEW_SAMPLE
            )
        except PluginFailed as error:
            _log_details(found, error)
            either = " either" if failed else ""
            raise PreviewFailed(
                f"{note} The sample data could not be drawn{either}: {_sentence(error.reason)}"
            ) from None
        if result.image is None:
            raise PreviewFailed(f"{note} The sample data gives no picture.")
        return _preview(result, sample=True, note=note, start=start)


def _preview(result: UpdateResult, *, sample: bool, note: str, start: float) -> Preview:
    png = io.BytesIO()
    result.image.save(png, format="PNG")
    alert = result.state is State.ALERT
    return Preview(png.getvalue(), sample, note, alert, time.monotonic() - start)


def _sentence(text: str) -> str:
    """``text`` ending with a full stop, so another sentence can follow."""
    text = text.rstrip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _log_details(found: PluginConfig, error: PluginFailed) -> None:
    log.info("preview of %s: %s", found.entry.id, error)
    if error.details:
        log.debug("%s", error.details)
