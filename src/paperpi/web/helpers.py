"""Setting helpers on the settings page: the search box under a setting, its choices and their
Use buttons (see ``docs/specs/plugins.md`` and :mod:`paperpi.helper`).

A search runs the plugin's helper in its own process with a time limit
(:func:`paperpi.runner.run_helper`), with the settings in the form as Save would write them.
Only one search runs at a time, as with previews: each one starts a Python process and may
wait for a web server. Use puts a choice's ``fill`` into the form's fields; nothing is saved.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .. import limits
from ..config import PluginConfig
from ..helper import Found, Helper, HelperProblem
from ..plugin import is_set
from ..runner import PluginFailed, PluginTimeout, run_helper
from .preview import Busy

log = logging.getLogger(__name__)

#: Runs one search: ``search(plugin_type, name, text, settings, time_limit=..., language=...)``,
#: as :func:`paperpi.runner.run_helper`. Tests pass a quick fake.
Search = Callable[..., Found]


def language(accept_language: str | None) -> str:
    """The language a browser asks for first, from its ``Accept-Language`` header (e.g.
    ``nl-NL,nl;q=0.9,en;q=0.8`` gives ``nl``), or ``en``. Only 2 or 3 letters are taken, so
    the header can't put anything else into a helper's web request."""
    first = (accept_language or "").split(",")[0].split(";")[0].strip()
    code = first.split("-")[0].lower()
    return code if code.isascii() and code.isalpha() and 2 <= len(code) <= 3 else "en"


class SearchFailed(RuntimeError):
    """The search could not be done or gave no answer; the message says why."""


@dataclass(frozen=True)
class Job:
    """One search: the plugin block as Save would write it, the setting and the typed text."""

    found: PluginConfig
    key: str
    """The setting whose helper this is."""
    name: str
    """The helper's name in the plugin's ``helpers``."""
    helper: Helper
    text: str
    language: str = "en"
    """The language the browser asks for first (see :func:`language`)."""


class Searcher:
    """Runs helpers' searches, one at a time."""

    def __init__(self, search: Search = run_helper):
        self._search = search
        self._lock = threading.Lock()
        self._stopped = threading.Event()

    def stop(self) -> None:
        """PaperPi stops: start no more plugin processes for searches. (A running one is
        stopped by :func:`paperpi.runner.stop_all`.)"""
        self._stopped.set()

    def find(self, job: Job) -> Found:
        """Search. Raises :class:`~paperpi.web.preview.Busy` while another search runs and
        :class:`SearchFailed` with a message for the user. Can take up to
        :data:`~paperpi.limits.HELPER_SEARCH` seconds, so call it from a worker thread."""
        if job.helper.typed and not job.text:
            raise SearchFailed("Type what to search for first.")
        if len(job.text) > limits.HELPER_TEXT:
            raise SearchFailed(f"Type at most {limits.HELPER_TEXT} characters.")
        settings = job.found.settings
        missing = [key for key in job.helper.needs if not is_set(getattr(settings, key))]
        if missing:
            raise SearchFailed(f"Fill in these settings first: {', '.join(missing)}.")
        if not self._lock.acquire(blocking=False):
            raise Busy("Another search is running. Wait a moment, then try again.")
        try:
            if self._stopped.is_set():
                raise SearchFailed("PaperPi is stopping, so no search can be done now.")
            plugin_type = job.found.plugin.type
            try:
                found = self._search(
                    plugin_type,
                    job.name,
                    job.text,
                    settings,
                    time_limit=limits.HELPER_SEARCH,
                    language=job.language,
                )
            except PluginTimeout:
                raise SearchFailed(
                    f"The search took longer than {limits.HELPER_SEARCH:g} seconds. "
                    "Try again later, or fill in the settings by hand."
                ) from None
            except HelperProblem as problem:
                raise SearchFailed(str(problem)) from None
            except PluginFailed as error:
                log.warning("search of %s, %s: %s", job.found.entry.id, job.key, error)
                if error.details:
                    log.debug("%s", error.details)
                raise SearchFailed("The search failed. PaperPi's log has the details.") from None
        finally:
            self._lock.release()
        if found.left_out:
            log.info("search of %s left out: %s", job.found.entry.id, "; ".join(found.left_out))
        return found
