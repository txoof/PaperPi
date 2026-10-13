"""Run one plugin update (or one search of a setting helper) in a new, short-lived process,
with a time limit.

See ``docs/decisions/plugin-interface.md``. Each update gets its own process: when it is
done, the process exits and its memory is given back. A plugin that hangs or crashes is
stopped without affecting PaperPi or other plugins.

To keep starts quick, processes are started by Python's "forkserver": one ready copy of
Python that has already loaded epdlib, Pillow and pydantic. Each update is a copy of it, so
these packages are not loaded again every time.

Log lines of the plugin process are sent to PaperPi with the result (at most
:data:`~paperpi.limits.PLUGIN_LOG_LINES` per update, secret settings replaced with ``****``)
and logged there, so they are in PaperPi's log like its own (see :mod:`paperpi.logbook`).
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import multiprocessing
import os
import signal
import threading
import time
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from multiprocessing.connection import Connection
from urllib.parse import quote, quote_plus

from PIL import Image
from pydantic import SecretBytes, SecretStr

from . import limits
from .helper import Found, HelperProblem, Query
from .plugin import Context, PluginSettings, State, holds_secret

log = logging.getLogger(__name__)

#: Packages the ready copy loads once, so each update starts without loading them.
PRELOAD = ["epdlib", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "pydantic", "paperpi.plugin"]

_context = multiprocessing.get_context("forkserver")
_context.set_forkserver_preload(PRELOAD)

# Plugin processes running now, so stop_all can end them when PaperPi stops.
_running: set[multiprocessing.process.BaseProcess] = set()
_running_lock = threading.Lock()


class PluginFailed(RuntimeError):
    """An update did not finish: the plugin raised an error, crashed or took too long."""

    def __init__(self, plugin_type: str, reason: str, details: str = ""):
        super().__init__(f"plugin {plugin_type!r}: {reason}")
        self.plugin_type = plugin_type
        self.reason = reason
        self.details = details
        """The plugin's traceback, when there is one."""


class PluginTimeout(PluginFailed):
    """An update took longer than its time limit and was stopped."""


@dataclass(frozen=True)
class UpdateResult:
    state: State
    image: Image.Image | None
    seconds: float
    """How long the update took, including starting the process."""


def run_update(
    plugin_type: str,
    context: Context,
    *,
    sample: bool = False,
    time_limit: float | None = None,
    package: str = "paperpi.plugins",
) -> UpdateResult:
    """Run one update of ``plugin_type`` in its own process and return its state and image.

    ``sample`` draws the plugin's sample data instead of fetching. ``time_limit`` defaults
    to :data:`paperpi.limits.PLUGIN_UPDATE`. ``package`` is where the plugin is (tests use it
    for fake plugins). Raises :class:`PluginTimeout` when the limit runs out and
    :class:`PluginFailed` when the plugin raises an error or crashes. Secret settings
    (``SecretStr``) are replaced with ``****`` in error messages.

    The time limit covers everything, also starting the process. The very first update
    also starts the ready copy (about a second on a Pi 4).
    """
    time_limit = limits.PLUGIN_UPDATE if time_limit is None else time_limit
    start = time.monotonic()
    # The settings travel as plain data: unpacking a settings object would import the plugin
    # before the child is in its own process group, where a hang can't be stopped cleanly.
    settings = context.settings.model_dump()
    bare = dataclasses.replace(context, settings=None)
    args = (plugin_type, package, bare, settings, sample)
    message = _run(plugin_type, _child, args, time_limit)
    seconds = time.monotonic() - start
    _, state, image = message
    return UpdateResult(State(state), _unpack(image), seconds)


def run_helper(
    plugin_type: str,
    name: str,
    text: str,
    settings: PluginSettings,
    *,
    time_limit: float | None = None,
    language: str = "en",
    package: str = "paperpi.plugins",
) -> Found:
    """Run one search of the plugin's helper ``name`` (see :mod:`paperpi.helper`) in its own
    process, for the typed ``text``, the form's ``settings`` and the user's ``language``
    (see :class:`~paperpi.helper.Query`), and return its checked result.

    ``time_limit`` defaults to :data:`paperpi.limits.HELPER_SEARCH`. Raises
    :class:`HelperProblem` with the helper's message for the user, and otherwise the same
    errors as :func:`run_update`.
    """
    time_limit = limits.HELPER_SEARCH if time_limit is None else time_limit
    args = (plugin_type, package, name, text, settings.model_dump(), language)
    return _run(plugin_type, _helper_child, args, time_limit)[1]


def _run(plugin_type: str, target: Callable, args: tuple, time_limit: float) -> tuple:
    """Run ``target(sender, *args)`` in a new plugin process and return the message it sends:
    ``("ok", ...)``. Raises for the others: ``("error", reason, details)`` and
    ``("problem", message)`` (a helper's message for the user)."""
    receiver, sender = _context.Pipe(duplex=False)
    level = logging.getLogger().getEffectiveLevel()
    process = _context.Process(
        target=target,
        args=(sender, level, *args),
        name=f"paperpi-plugin-{plugin_type}",
        daemon=True,
    )
    finished = False
    try:
        process.start()
        with _running_lock:
            _running.add(process)
        sender.close()  # the child has its own copy; closing ours lets us notice a crash
        try:
            message = _receive(receiver, plugin_type, time_limit)
            finished = True
        except (EOFError, OSError):
            process.join(limits.PLUGIN_EXIT)
            raise PluginFailed(
                plugin_type, f"process ended without a result (exit code {process.exitcode})"
            ) from None
    finally:
        with _running_lock:
            _running.discard(process)
        sender.close()
        receiver.close()
        _stop(process, wait=finished)
    if message[0] == "error":
        _, reason, details = message
        raise PluginFailed(plugin_type, reason, details)
    if message[0] == "problem":
        raise HelperProblem(message[1])
    return message


def _receive(receiver: Connection, plugin_type: str, time_limit: float) -> tuple:
    """The plugin process's result. The log lines it sends before it are logged here."""
    end = time.monotonic() + time_limit
    while True:
        if not receiver.poll(max(0.0, end - time.monotonic())):
            raise PluginTimeout(plugin_type, f"no result within {time_limit:g} s; stopped")
        message = receiver.recv()
        if message[0] != "log":
            return message
        try:
            _, level, name, text, created = message
            level = min(max(int(level), logging.DEBUG), logging.CRITICAL)
            created = float(created)
        except (TypeError, ValueError):
            raise PluginFailed(plugin_type, "sent a log line that can't be read") from None
        logger = logging.getLogger(str(name))
        if logger.isEnabledFor(level):
            # With the time the plugin logged it, which may be a while before it arrives.
            values = {"name": logger.name, "levelno": level, "msg": str(text), "created": created}
            logger.handle(
                logging.makeLogRecord(values | {"levelname": logging.getLevelName(level)})
            )


def stop_all() -> None:
    """Stop every plugin update that is running now, e.g. because PaperPi stops.

    Each stopped update raises :class:`PluginFailed` in the thread that waits for it, so
    nothing waits for a hanging plugin's time limit.
    """
    with _running_lock:
        processes = list(_running)
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            # It has ended, or has not made its own process group yet.
            try:
                process.kill()
            except (OSError, ValueError):
                pass


def _stop(process: multiprocessing.process.BaseProcess, *, wait: bool) -> None:
    """Make sure the plugin process, and anything it started, has ended.

    ``wait``: the plugin has handed over its result, so give it a moment to exit by itself.
    """
    if process.pid is None:  # never started
        return
    if wait:
        process.join(limits.PLUGIN_EXIT)
    if process.exitcode is None or _group_alive(process.pid):
        # The child made itself a process group, so this also stops programs it started.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            # The time limit ran out before the child had made its own process group.
            process.kill()
        process.join(limits.PLUGIN_EXIT)
    if process.exitcode is None:
        log.error("plugin process %s did not stop", process.pid)
    else:
        process.close()


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _child(
    sender: Connection,
    level: int,
    plugin_type: str,
    package: str,
    context: Context,
    settings: dict,
    sample: bool,
) -> None:
    """Runs in the plugin process: one update, then send the result and exit."""
    sender = _OneAtATime(sender)
    with _reporting(sender, level) as secrets:
        from .plugin import draw_update

        plugin, checked = _load(plugin_type, package, settings, secrets)
        context = dataclasses.replace(context, settings=checked)
        state, image = draw_update(plugin, context, sample=sample)
        sender.send(("ok", state.value, _pack(image)))


def _helper_child(
    sender: Connection,
    level: int,
    plugin_type: str,
    package: str,
    name: str,
    text: str,
    settings: dict,
    language: str,
) -> None:
    """Runs in the plugin process: one search of a helper, then send the result and exit."""
    sender = _OneAtATime(sender)
    with _reporting(sender, level) as secrets:
        from .helper import clean

        plugin, checked = _load(plugin_type, package, settings, secrets)
        try:
            result = plugin.helpers[name].find(Query(text, checked, language))
        except HelperProblem as problem:  # only here: in an update it is an ordinary error
            sender.send(("problem", _hide(str(problem), secrets)))
            return
        # A secret (an API key) can't be filled in, and is never shown or logged.
        fields = plugin.settings.model_fields.items()
        fillable = [key for key, info in fields if not holds_secret(info.annotation)]
        sender.send(("ok", clean(result, fillable, lambda text: _hide(text, secrets))))


@contextlib.contextmanager
def _reporting(sender: _OneAtATime, level: int) -> Iterator[list[str]]:
    """In the plugin process: send log lines of ``level`` and up, and any error, as messages,
    with secret settings (filled into the list it gives) replaced with ``****``. Also closes
    ``sender``."""
    os.setpgrp()  # own process group, so the parent can stop everything this plugin starts
    secrets: list[str] = []
    root = logging.getLogger()
    handler = _LogSender(sender, secrets)
    root.addHandler(handler)
    root.setLevel(level)
    try:
        yield secrets
    except BaseException as error:  # noqa: BLE001 - report everything, then exit
        reason = _hide(f"{type(error).__name__}: {error}", secrets)
        sender.send(("error", reason, _hide(traceback.format_exc(), secrets)))
    finally:
        root.removeHandler(handler)
        sender.close()


class _OneAtATime:
    """In the plugin process: the pipe to PaperPi, for one message at a time. A log line from
    another thread of the plugin must not be written into the middle of the result."""

    def __init__(self, sender: Connection) -> None:
        self._sender = sender
        self._lock = threading.Lock()

    def send(self, message: tuple) -> None:
        with self._lock:
            self._sender.send(message)

    def close(self) -> None:
        with self._lock:
            self._sender.close()


class _LogSender(logging.Handler):
    """In the plugin process: sends each log line to PaperPi, at most
    :data:`~paperpi.limits.PLUGIN_LOG_LINES`, then one that says the rest are left out."""

    def __init__(self, sender: _OneAtATime, secrets: list[str]) -> None:
        super().__init__()
        self.sender = sender
        self.secrets = secrets
        self.sent = 0
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        # logging calls this with the handler's lock held, also when a plugin uses threads.
        try:
            if self.sent > limits.PLUGIN_LOG_LINES:
                return
            self.sent += 1
            if self.sent > limits.PLUGIN_LOG_LINES:
                level = logging.WARNING
                text = f"more than {limits.PLUGIN_LOG_LINES} log lines; the rest are left out"
            else:
                level, text = record.levelno, _hide(self.format(record), self.secrets)
            self.sender.send(("log", level, record.name, text, record.created))
        except Exception:  # noqa: BLE001 - a log line must never break the update
            self.handleError(record)


def _load(plugin_type: str, package: str, settings: dict, secrets: list[str]):
    """The plugin and its checked settings; their secrets are added to ``secrets``."""
    from . import plugins

    plugin = plugins.load(plugin_type, package)
    checked = plugin.settings.model_validate(settings)
    secrets += [v.get_secret_value() for v in dict(checked).values() if _is_secret(v)]
    return plugin, checked


def _is_secret(value) -> bool:
    return isinstance(value, SecretStr | SecretBytes)


def _hide(text: str, secrets: list) -> str:
    """Replace secret settings (API keys, passwords) in an error message with ****."""
    for secret in secrets:
        if isinstance(secret, bytes):
            secret = secret.decode("utf-8", "replace")
        if not secret:
            continue
        # Also the forms a web address uses, e.g. in the message of a failed request.
        for form in sorted({secret, quote(secret, safe=""), quote_plus(secret)}, key=len)[::-1]:
            text = text.replace(form, "****")
    return text


def _pack(image: Image.Image | None):
    return None if image is None else (image.mode, image.size, image.tobytes())


def _unpack(packed) -> Image.Image | None:
    if packed is None:
        return None
    mode, size, data = packed
    return Image.frombytes(mode, size, data)
