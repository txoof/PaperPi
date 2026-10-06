"""The screen: writes run in a separate helper process, watched by a time limit.

See ``docs/decisions/display-driver-interface.md`` and ``errors-and-time-limits.md``.

The screen driver (from epdlib) is made and used only in a small helper process. PaperPi
sends it each image and waits for the answer, at most the time limit. A write that hangs is
not waited for: the helper process is stopped, which makes the operating system release the
screen's data line (SPI) and pins (GPIO). The next write starts a new helper process, and the
driver's ``init`` resets the screen (the IT8951 driver pulses its reset pin).

:class:`Screen` adds the rules for a screen that keeps failing ("the screen watchdog"):

- Every :data:`~paperpi.limits.SCREEN_FAILURES_BEFORE_RESET` failed writes in a row, the
  helper process is restarted, which resets the screen.
- When the write after :data:`~paperpi.limits.SCREEN_RESETS_BEFORE_REST` such resets fails
  too, writes pause: one try every :data:`~paperpi.limits.SCREEN_REST` seconds. PaperPi
  keeps running.
- When a helper process can't be stopped (it is stuck inside the operating system), only a
  restart of PaperPi can help: :class:`ScreenStuck` is raised, so PaperPi exits and systemd
  or Docker starts it again. At most once per :data:`~paperpi.limits.SCREEN_STUCK_EXIT`
  seconds, remembered in a file, so this can't become a restart loop.
"""

from __future__ import annotations

import logging
import multiprocessing
import signal
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path

from epdlib.drivers import Driver
from PIL import Image

from . import limits
from .files import write_atomic

log = logging.getLogger(__name__)

#: Makes the driver, in the helper process. It is sent there, so it must be picklable, e.g.
#: ``functools.partial(VirtualDriver, 1200, 825, mode, folder)``.
MakeDriver = Callable[[], Driver]

_context = multiprocessing.get_context("forkserver")


class ScreenError(RuntimeError):
    """A screen operation did not work."""


class ScreenTimeout(ScreenError):
    """A screen operation took longer than its time limit; the helper process was stopped."""


class ScreenResting(ScreenError):
    """Writes are paused, because resetting the screen did not help."""

    def __init__(self, message: str, wait: float):
        super().__init__(message)
        self.wait = wait
        """Seconds until the next try."""


class ScreenStuck(ScreenError):
    """A helper process could not be stopped. Only a restart of PaperPi can help."""


class Helper:
    """One helper process that holds the screen driver.

    Not for use from several threads at once, except :meth:`kill`.
    """

    def __init__(self, make_driver: MakeDriver):
        self.make_driver = make_driver
        self._process: multiprocessing.process.BaseProcess | None = None
        self._pipe: Connection | None = None

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self, limit: float) -> None:
        """Start the helper process, which makes the driver and calls its ``init``."""
        pipe, child = _context.Pipe()
        process = _context.Process(
            target=_child, args=(child, self.make_driver), name="paperpi-screen", daemon=True
        )
        process.start()
        child.close()  # the child has its own copy; closing ours lets us notice a crash
        self._process, self._pipe = process, pipe
        self._answer("init", limit)

    def call(self, command: str, *args, limit: float) -> float:
        """Run ``command`` in the helper process; returns the seconds it took there."""
        try:
            self._pipe.send((command, *args))
        except OSError:
            self._ended(command)
        return self._answer(command, limit)

    def stop(self, *, close: bool = False) -> None:
        """End the helper process. ``close``: first ask the driver to close the screen."""
        process, pipe = self._process, self._pipe
        if process is None:
            return
        if close:
            try:
                pipe.send(("close",))
                if pipe.poll(limits.SCREEN_CLOSE):
                    pipe.recv()
            except (EOFError, OSError):
                pass
        self._process = self._pipe = None
        pipe.close()
        process.join(limits.SCREEN_STOP if close else 0)
        if process.exitcode is None:
            process.kill()
            process.join(limits.SCREEN_STOP)
        if process.exitcode is None:
            raise ScreenStuck(f"the screen helper process {process.pid} can't be stopped")
        process.close()

    def kill(self) -> None:
        """Kill the helper process now; safe to call from another thread."""
        process = self._process
        if process is not None:
            try:
                process.kill()
            except (OSError, ValueError):
                pass

    def _answer(self, what: str, limit: float) -> float:
        try:
            if not self._pipe.poll(limit):
                self.stop()
                raise ScreenTimeout(f"{what} took longer than {limit:g} s; helper process stopped")
            status, value = self._pipe.recv()
        except (EOFError, OSError):
            self._ended(what)
        if status == "error":
            if what == "init":
                self.stop()  # the helper process ends after a failed init
            raise ScreenError(f"{what} failed: {value}")
        return value

    def _ended(self, what: str):
        code = None if self._process is None else self._process.exitcode
        self.stop()
        raise ScreenError(f"the screen helper process ended during {what} (exit code {code})")


def _child(pipe: Connection, make_driver: MakeDriver) -> None:
    """Runs in the helper process: make the driver, then run commands until "close"."""
    # Ctrl+C in a terminal reaches every process; the main process closes this one.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    driver = None
    try:
        start = time.monotonic()
        try:
            driver = make_driver()
            driver.init()
        except Exception as error:  # noqa: BLE001 - reported to the main process
            pipe.send(("error", f"{type(error).__name__}: {error}"))
            return
        pipe.send(("ok", time.monotonic() - start))
        while True:
            command, *args = pipe.recv()
            start = time.monotonic()
            try:
                if command == "close":
                    driver, closing = None, driver
                    closing.close()
                elif command == "write":
                    mode, size, data, fast = args
                    driver.write(Image.frombytes(mode, size, data), fast=fast)
                elif command == "clear":
                    driver.clear()
                else:
                    raise ValueError(f"unknown command {command!r}")
            except Exception as error:  # noqa: BLE001 - reported to the main process
                pipe.send(("error", f"{type(error).__name__}: {error}"))
            else:
                pipe.send(("ok", time.monotonic() - start))
            if command == "close":
                return
    except (EOFError, OSError):
        pass  # the main process is gone or stopped this one
    finally:
        if driver is not None:
            driver.close()  # safe to call more than once


class Screen:
    """The screen as the scheduler sees it: writes with a time limit, and the watchdog rules.

    ``color``: a colour screen, which gets a longer time limit before its first redraw is
    measured. ``stuck_file`` remembers when PaperPi last exited because of a stuck helper
    process (``None``: never exit). ``clock`` and ``wall`` (monotonic and real time) and
    ``helper`` are for tests.
    """

    def __init__(
        self,
        make_driver: MakeDriver,
        *,
        color: bool = False,
        stuck_file: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        helper: Helper | None = None,
    ):
        self._helper = helper or Helper(make_driver)
        self._first_limit = limits.SCREEN_FIRST_COLOR if color else limits.SCREEN_FIRST
        self.stuck_file = stuck_file
        self.clock = clock
        self.wall = wall
        self.redraw: float | None = None
        """How long the last good write took in the helper process (``None``: none yet)."""
        self.failures = 0
        """Failed operations in a row."""
        self.resets = 0
        """Resets in a row that did not help yet."""
        self.retry_at: float | None = None
        """While writes are paused: when the next try is allowed (monotonic clock)."""
        self._lock = threading.Lock()

    @property
    def time_limit(self) -> float:
        """The longest one write may take: 3 × the measured redraw, within the bounds."""
        if self.redraw is None:
            return self._first_limit
        limit = limits.SCREEN_REDRAW_FACTOR * self.redraw
        return min(max(limit, limits.SCREEN_SHORTEST), limits.SCREEN_LONGEST)

    def write(self, image: Image.Image, *, fast: bool = False) -> None:
        """Show ``image``. Raises :class:`ScreenError` when it did not work."""
        self._run("write", image.mode, image.size, image.tobytes(), fast)

    def clear(self) -> None:
        """Make the screen blank."""
        self._run("clear")

    def close(self) -> None:
        """Close the screen and end the helper process. Never raises."""
        if not self._lock.acquire(timeout=1):
            self._helper.kill()  # a write is in progress: end it, so closing doesn't wait
            self._lock.acquire()
        try:
            self._helper.stop(close=True)
        except ScreenStuck as error:
            log.error("%s", error)
        finally:
            self._lock.release()

    def __enter__(self) -> Screen:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _run(self, command: str, *args) -> None:
        with self._lock:
            now = self.clock()
            if self.retry_at is not None and now < self.retry_at:
                wait = self.retry_at - now
                raise ScreenResting(f"screen not answering; next try in {wait:.0f} s", wait)
            try:
                if not self._helper.running:
                    self._helper.start(self.time_limit)
                seconds = self._helper.call(command, *args, limit=self.time_limit)
            except ScreenStuck:
                self._stuck()
                raise
            except ScreenError:
                self._failed()
                raise
            if command == "write":
                self.redraw = seconds
            if self.failures:
                log.warning("the screen answers again, after %d failures", self.failures)
            self.failures = self.resets = 0
            self.retry_at = None

    def _failed(self) -> None:
        self.failures += 1
        if self.retry_at is not None or self.resets >= limits.SCREEN_RESETS_BEFORE_REST:
            if self.retry_at is None:
                log.error(
                    "the screen does not answer after %d resets; trying again every %g minutes",
                    self.resets,
                    limits.SCREEN_REST / 60,
                )
            self._rest()
        elif self.failures % limits.SCREEN_FAILURES_BEFORE_RESET == 0:
            self.resets += 1
            log.warning(
                "screen failed %d times in a row; resetting it (reset %d of %d)",
                self.failures,
                self.resets,
                limits.SCREEN_RESETS_BEFORE_REST,
            )
            self._stop_helper()  # the next write starts a new one, whose init resets the screen

    def _rest(self) -> None:
        self.retry_at = self.clock() + limits.SCREEN_REST
        self._stop_helper()  # releases the pins while writes are paused

    def _stop_helper(self) -> None:
        try:
            self._helper.stop()
        except ScreenStuck:
            self._stuck()
            raise

    def _stuck(self) -> None:
        """A helper process can't be stopped: exit PaperPi, unless it did so recently."""
        now = self.wall()
        last = _read_time(self.stuck_file)
        if self.stuck_file is not None and (last is None or now - last >= limits.SCREEN_STUCK_EXIT):
            log.critical("a screen helper process is stuck; PaperPi exits so it can be restarted")
            try:
                write_atomic(self.stuck_file, f"{now}\n".encode())
            except OSError as error:
                log.error("can't write %s: %s", self.stuck_file, error)
            return
        log.error("a screen helper process is stuck; not exiting again so soon")
        self.failures += 1
        self.retry_at = self.clock() + limits.SCREEN_REST
        raise ScreenResting("screen helper process stuck", limits.SCREEN_REST)


def _read_time(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return float(path.read_text()[:50])
    except (OSError, ValueError):
        return None
