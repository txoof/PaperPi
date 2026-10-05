"""Run one plugin update in a new, short-lived process, with a time limit.

See ``docs/decisions/plugin-interface.md``. Each update gets its own process: when it is
done, the process exits and its memory is given back. A plugin that hangs or crashes is
stopped without affecting PaperPi or other plugins.

To keep starts quick, processes are started by Python's "forkserver": one ready copy of
Python that has already loaded epdlib, Pillow and pydantic. Each update is a copy of it, so
these packages are not loaded again every time.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import time
import traceback
from dataclasses import dataclass
from multiprocessing.connection import Connection

from PIL import Image

from . import limits
from .plugin import Context, State

log = logging.getLogger(__name__)

#: Packages the ready copy loads once, so each update starts without loading them.
PRELOAD = ["epdlib", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "pydantic", "paperpi.plugin"]

_context = multiprocessing.get_context("forkserver")
_context.set_forkserver_preload(PRELOAD)


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
    for fake plugins). Raises :class:`PluginTimeout` when the limit
    runs out and :class:`PluginFailed` when the plugin raises an error or crashes.
    """
    time_limit = limits.PLUGIN_UPDATE if time_limit is None else time_limit
    start = time.monotonic()
    receiver, sender = _context.Pipe(duplex=False)
    process = _context.Process(
        target=_child,
        args=(sender, plugin_type, package, context, sample),
        name=f"paperpi-plugin-{plugin_type}",
        daemon=True,
    )
    finished = False
    try:
        process.start()
        sender.close()  # the child has its own copy; closing ours lets us notice a crash
        try:
            if not receiver.poll(time_limit):
                raise PluginTimeout(plugin_type, f"no result within {time_limit:g} s; stopped")
            message = receiver.recv()
            finished = True
        except EOFError:
            process.join(limits.PLUGIN_EXIT)
            raise PluginFailed(
                plugin_type, f"process ended without a result (exit code {process.exitcode})"
            ) from None
    finally:
        sender.close()
        receiver.close()
        _stop(process, wait=finished)
    seconds = time.monotonic() - start
    if message[0] == "error":
        _, reason, details = message
        raise PluginFailed(plugin_type, reason, details)
    _, state, image = message
    return UpdateResult(State(state), _unpack(image), seconds)


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
            pass
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
    sender: Connection, plugin_type: str, package: str, context: Context, sample: bool
) -> None:
    """Runs in the plugin process: one update, then send the result and exit."""
    os.setpgrp()  # own process group, so the parent can stop everything this plugin starts
    try:
        from . import plugins
        from .plugin import draw_update

        plugin = plugins.load(plugin_type, package)
        state, image = draw_update(plugin, context, sample=sample)
        sender.send(("ok", state.value, _pack(image)))
    except BaseException as error:  # noqa: BLE001 - report everything, then exit
        reason = f"{type(error).__name__}: {error}"
        sender.send(("error", reason, traceback.format_exc()))
    finally:
        sender.close()


def _pack(image: Image.Image | None):
    return None if image is None else (image.mode, image.size, image.tobytes())


def _unpack(packed) -> Image.Image | None:
    if packed is None:
        return None
    mode, size, data = packed
    return Image.frombytes(mode, size, data)
