"""The screen: writes run in a separate helper process, watched by a time limit.

See ``docs/decisions/display-driver-interface.md`` and ``errors-and-time-limits.md``.

The screen driver (from epdlib) is made and used only in a small helper process. PaperPi
sends it each image and waits for the answer, at most the time limit. A write that hangs is
not waited for: the helper process is stopped, which makes the operating system release the
screen's data line (SPI) and pins (GPIO). The next write starts a new helper process, and the
driver's ``init`` resets the screen (the IT8951 driver pulses its reset pin). After every
write and clear the screen is put to sleep (low power); the next one wakes it without a reset,
so the driver still knows what is on screen and a fast write sends only the changed part.

:class:`Screen` adds the rules for a screen that keeps failing ("the screen watchdog"):

- Every :data:`~paperpi.limits.SCREEN_FAILURES_BEFORE_RESET` failed writes in a row, the
  helper process is restarted, which resets the screen.
- When the write after :data:`~paperpi.limits.SCREEN_RESETS_BEFORE_REST` such resets fails
  too, writes pause: the next try is after :data:`~paperpi.limits.SCREEN_REST` seconds, and
  each failed try doubles the wait, up to :data:`~paperpi.limits.SCREEN_REST_LONGEST`. A
  wrong setting or a switched-off SPI is not fixed by trying again, so trying less often
  keeps the log short. PaperPi keeps running.
- When a helper process can't be stopped (it is stuck inside the operating system), only a
  restart of PaperPi can help: :class:`ScreenStuck` is raised, so PaperPi exits and systemd
  or Docker starts it again. At most once per :data:`~paperpi.limits.SCREEN_STUCK_EXIT`
  seconds, remembered in a file, so this can't become a restart loop.
"""

from __future__ import annotations

import logging
import math
import multiprocessing
import os
import signal
import threading
import time
from collections.abc import Callable
from functools import partial
from multiprocessing.connection import Connection
from pathlib import Path

from epdlib.drivers import Driver
from PIL import Image

from . import limits
from .config import MODES, VIRTUAL_MODE, DisplaySettings
from .files import write_atomic

log = logging.getLogger(__name__)

#: Makes the driver, in the helper process. It is sent there, so it must be picklable, e.g.
#: ``functools.partial(VirtualDriver, 1200, 825, mode, folder)``.
MakeDriver = Callable[[], Driver]

# "spawn": the helper process is a direct child of PaperPi, so PaperPi can always stop it.
# (A process started by the forkserver, as plugin processes are, can't be stopped once the
# forkserver has ended, e.g. because the system ran out of memory.) Starting takes a second
# or two, once.
_context = multiprocessing.get_context("spawn")


def driver_for(display: DisplaySettings, folder: Path) -> MakeDriver:
    """How to make the driver for ``display``; a virtual screen writes its PNGs to ``folder``."""
    if display.type == "it8951":
        from epdlib.drivers.it8951 import IT8951Driver

        return partial(
            IT8951Driver, display.model, vcom=display.vcom, max_refresh=display.max_refresh
        )
    from epdlib.drivers.virtual import VirtualDriver

    width, height = display.size
    return partial(VirtualDriver, width, height, MODES[display.mode or VIRTUAL_MODE], folder)


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
        self._stuck: list[multiprocessing.process.BaseProcess] = []
        """Helper processes that could not be stopped."""
        self._killed = False
        """:meth:`kill` was called; a helper process that is starting is stopped too."""

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self, limit: float) -> None:
        """Start the helper process, which makes the driver and calls its ``init``."""
        self._stuck = [p for p in self._stuck if p.exitcode is None]
        if self._stuck:
            # It may still hold the screen's pins; a new one would only add to the pile.
            raise ScreenError(f"the stuck screen helper process {self._stuck[0].pid} still runs")
        pipe, child = _context.Pipe()
        process = _context.Process(
            target=_child, args=(child, self.make_driver), name="paperpi-screen", daemon=True
        )
        try:
            process.start()
        except Exception as error:  # noqa: BLE001 - e.g. too many open files
            pipe.close()
            raise ScreenError(f"can't start the screen helper process: {error}") from error
        finally:
            child.close()  # the child has its own copy; closing ours lets us notice a crash
        self._process, self._pipe = process, pipe
        if self._killed:
            self.stop()
            raise ScreenError("the screen was closed while its helper process started")
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
            self._stuck.append(process)
            raise ScreenStuck(f"the screen helper process {process.pid} can't be stopped")
        process.close()

    def kill(self) -> None:
        """Kill the helper process now; safe to call from another thread."""
        self._killed = True
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
    # Ctrl+C in a terminal, and systemd's stop signal, reach every process; the main process
    # closes this one (and can always kill it).
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    driver = None
    try:
        start = time.monotonic()
        try:
            driver = make_driver()
            driver.init()
        except Exception as error:  # noqa: BLE001 - reported to the main process
            pipe.send(("error", f"{type(error).__name__}: {error}"))
            return
        _sleep(driver)  # until the first write, which may be a while
        pipe.send(("ok", time.monotonic() - start))
        while True:
            command, *args = pipe.recv()
            start = time.monotonic()
            try:
                if command == "close":
                    driver, closing = None, driver
                    _sleep(closing)
                    closing.close()
                elif command == "write":
                    mode, size, data, fast = args
                    try:
                        driver.write(Image.frombytes(mode, size, data), fast=fast)
                    finally:
                        _sleep(driver)  # also after a failed write; the next write wakes it
                elif command == "clear":
                    try:
                        driver.clear()
                    finally:
                        _sleep(driver)
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


def _sleep(driver: Driver) -> None:
    """Put the screen into low power. A failure is not reported: the picture is on screen,
    and a screen that really fails shows it at the next write."""
    try:
        driver.sleep()
    except Exception:  # noqa: BLE001, S110 - see above
        pass


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
        self.rests = 0
        """Failed tries while paused; each one doubles the wait before the next."""
        self._paused_since: float | None = None
        """When writes paused (real time), for the log."""
        self._lock = threading.Lock()
        self._closed = False

    @property
    def time_limit(self) -> float:
        """The longest one write may take: 3 × the measured redraw, within the bounds."""
        if self.redraw is None:
            return self._first_limit
        limit = limits.SCREEN_REDRAW_FACTOR * self.redraw
        return min(max(limit, limits.SCREEN_SHORTEST), limits.SCREEN_LONGEST)

    def check(self) -> None:
        """Start the screen, if it is not running yet, to check that it answers. Raises
        :class:`ScreenError` when it does not."""
        self._run("check")

    def write(self, image: Image.Image, *, fast: bool = False) -> None:
        """Show ``image``. Raises :class:`ScreenError` when it did not work."""
        self._run("write", image, fast)

    def clear(self) -> None:
        """Make the screen blank."""
        self._run("clear")

    def clear_before_exit(self) -> None:
        """Make the screen blank when PaperPi stops, within a short time limit. Skipped when
        a write is still running, writes are paused, or no helper process runs (the screen
        would first need a reset). Raises :class:`ScreenStuck` when the helper process can't
        be stopped; other problems are only logged."""
        if not self._lock.acquire(timeout=limits.SCREEN_EXIT_WAIT):
            log.warning("the screen is not cleared before exit: a write is still running")
            return
        try:
            if self._closed or self.retry_at is not None or not self._helper.running:
                log.info("the screen is not cleared before exit: it is not answering")
                return
            limit = min(self.time_limit, limits.SCREEN_EXIT_CLEAR)
            self._helper.call("clear", limit=limit)
            log.info("screen cleared")
        except ScreenStuck:
            raise
        except ScreenError as error:
            log.warning("the screen could not be cleared before exit: %s", error)
        finally:
            self._lock.release()

    def abort(self) -> None:
        """End a running screen operation at once (e.g. a second Ctrl+C while clearing)."""
        self._helper.kill()

    def close(self) -> None:
        """Close the screen and end the helper process. Never raises."""
        self._closed = True
        if not self._lock.acquire(timeout=1):
            self._helper.kill()  # a write is in progress: end it, so closing doesn't wait
            if not self._lock.acquire(timeout=limits.SCREEN_CLOSE):
                log.error("the screen could not be closed: a write does not end")
                return
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
            if self._closed:
                raise ScreenError("the screen is closed")
            now = self.clock()
            if self.retry_at is not None and now < self.retry_at:
                wait = self.retry_at - now
                raise ScreenResting(f"screen not answering; next try in {wait:.0f} s", wait)
            if command == "write":  # the image travels as plain data
                image, fast = args
                args = (image.mode, image.size, image.tobytes(), fast)
            try:
                if not self._helper.running:
                    self._helper.start(self.time_limit)
                if command != "check":
                    seconds = self._helper.call(command, *args, limit=self.time_limit)
            except ScreenStuck:
                self._stuck()
                raise
            except ScreenError as error:
                self._failed(error)
                if self.retry_at is not None:  # this failure started (or continues) a pause
                    raise ScreenResting(f"{error}; writes paused", self.retry_at - now) from error
                raise
            if command == "write":
                self.redraw = seconds
            if self.failures:
                log.warning("the screen answers again, after %d failures", self.failures)
            self.failures = self.resets = self.rests = 0
            self.retry_at = self._paused_since = None

    def _failed(self, error: ScreenError) -> None:
        self.failures += 1
        if self.retry_at is not None or self.resets >= limits.SCREEN_RESETS_BEFORE_REST:
            first = self.retry_at is None
            self._rest()
            wait = _minutes(self.retry_at - self.clock())
            if first:
                log.error(
                    "the screen does not answer after %d resets: %s; next try in %s",
                    self.resets,
                    error,
                    wait,
                )
            else:  # the full message is above; one short line per try
                since = time.strftime("%H:%M", time.localtime(self._paused_since))
                log.warning("screen still not answering (since %s); next try in %s", since, wait)
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
        # First: a stuck helper process counts the wait itself (in _stuck), only once.
        self._stop_helper()  # releases the pins while writes are paused
        self.retry_at = self.clock() + self._next_wait()

    def _stop_helper(self) -> None:
        try:
            self._helper.stop()
        except ScreenStuck:
            self._stuck()
            raise

    def _stuck(self) -> None:
        """A helper process can't be stopped: exit PaperPi, unless it did so recently."""
        now = self.wall()
        last = _read_time(self.stuck_file, now)
        if self.stuck_file is not None and (last is None or now - last >= limits.SCREEN_STUCK_EXIT):
            try:
                write_atomic(self.stuck_file, f"{now}\n".encode())
            except OSError as error:
                # Without the file, the next start would not know: pause instead of exiting,
                # so this can't become a restart loop.
                log.error("can't write %s: %s", self.stuck_file, error)
            else:
                log.critical("a screen helper process is stuck; PaperPi exits to be started again")
                return
        log.error("a screen helper process is stuck; writes pause (no exit within the hour)")
        self.failures += 1
        wait = self._next_wait()
        self.retry_at = self.clock() + wait
        raise ScreenResting("screen helper process stuck", wait)

    def _next_wait(self) -> float:
        """The wait before the next try while paused: it doubles after each failed try."""
        if self._paused_since is None:
            self._paused_since = self.wall()
        # 2**6 × 10 minutes is past the longest wait; capped so the number can't grow forever.
        self.rests = min(self.rests + 1, 7)
        return min(limits.SCREEN_REST * 2 ** (self.rests - 1), limits.SCREEN_REST_LONGEST)


def _minutes(seconds: float) -> str:
    """``40 minutes``, ``2 hours``, ``5 hours 20 minutes``."""
    minutes = round(seconds / 60)
    if minutes < 120:
        return f"{minutes} minutes"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hours" + (f" {minutes} minutes" if minutes else "")


def _read_time(path: Path | None, now: float) -> float | None:
    """The time in ``path``; ``None`` when there is none, or it is not a sensible time."""
    if path is None:
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            when = float(os.read(fd, 64))
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None
    return when if math.isfinite(when) and when <= now else None
