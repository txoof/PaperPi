"""The scheduler: decides which plugin is on screen, and is the only part that writes to it.

The reasons behind these rules are in ``docs/decisions/plugin-scheduling.md``. In short:

- Every plugin updates on its own refresh timer, all the time, whether it is on screen or
  not. So when a turn changes, the next plugin's image is ready and is shown at once. Each
  update runs in its own process (:mod:`paperpi.runner`), at most
  :data:`~paperpi.limits.PARALLEL_UPDATES` at the same time.
- Each plugin has a level:

  =========  ===========================================================================
  alert      Shown while the plugin has something, unless someone dismissed it. Nothing
             interrupts it. Several alerts take turns.
  interrupt  Shown while the plugin has something (e.g. a song is playing). Several take
             turns. When it ends, the rotation goes on with the next plugin.
  rotation   When no alert or interrupt is shown, these take turns in config order, each
             for its ``display_time``.
  =========  ===========================================================================

  The level decides. A plugin's state only says whether it has something: "ready" and
  "alert" mean the same.
- The screen is written only when the image changes. A new image from the plugin on screen
  is not written when its turn ends sooner than a screen write takes.
- Before each update the plugin is told whether the disk is low (``low_disk``,
  :mod:`paperpi.storage`). After each update, also a failed one, its storage folder is
  cleaned up in the worker thread, before the result reaches the loop.
- A write is a fast one (only the changed part, no flash) when the plugin on screen shows a
  new image, and a full one when another plugin comes on screen. The screen driver makes
  every ``max_refresh``-th fast write in a row a full one. Every ``[display] clean_every``
  seconds, at the next write (and at the first write after a start), the screen is first
  cleared, which removes all leftovers of earlier images, and the image is drawn in full.
- At start, a check in the writer thread starts the screen (the driver's ``init``) to see
  that it answers; when it does not, the error is logged and PaperPi keeps running.
- Screen writes run in their own thread (and, with :class:`paperpi.screen.Screen`, in a
  helper process with a time limit), so the loop keeps reporting "still running" during a
  slow write. Nothing new is chosen until the write has finished. A failed write is tried
  again at the next update of the plugin on screen; while the screen watchdog pauses writes,
  at the end of the pause. When a helper process is stuck, :meth:`Scheduler.run` raises
  :class:`~paperpi.screen.ScreenStuck`, so PaperPi exits and is started again.
- A failed update is skipped and tried again at the next refresh. After
  :data:`~paperpi.limits.FAILURES_BEFORE_LEFT_OUT` failures in a row the plugin is left out
  for :data:`~paperpi.limits.LEFT_OUT` seconds. When nothing can be shown because plugins
  fail, or no plugin is switched on, the ``default`` plugin says so. When no plugin has
  anything to show and none fail, a small fallback clock is shown (``[display]
  fallback_clock``), so an empty screen is never mistaken for a broken one.

One loop (:meth:`Scheduler.run`) makes every decision, in one thread, so two decisions can
never happen at the same moment. Finished updates and screen writes, "stop", "reload" and
"dismiss" reach it as events in one queue. The loop sleeps until the next event or the next
moment something is due, and at least every :data:`~paperpi.limits.HEALTH_REPORT` seconds it
reports "still running" (:mod:`paperpi.health`), so a stuck loop is noticed and PaperPi
restarted. The clock, the executor (what runs the updates) and the writer (what runs the
screen writes) are passed in, so tests can use a fake clock and check hours of switching in a
fraction of a second.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import queue
import time
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops

from . import limits, plugins
from .config import Config, PluginConfig
from .plugin import Context, PluginEntry, PluginsStatus, State
from .runner import UpdateResult, run_update, stop_all
from .screen import Screen, ScreenResting, ScreenStuck
from .storage import LowDisk, clean

log = logging.getLogger(__name__)

#: Runs one update: ``update(plugin_type, context, time_limit)``. Raises on failure.
Update = Callable[[str, Context, float], UpdateResult]

#: Says "still running": ``report(seconds since the last screen write or None, screen state)``.
#: The screen state is ``None`` before the first write, then "ok", "failing" or "paused".
Report = Callable[[float | None, str | None], None]


class Clock:
    """Real time. Tests pass a fake clock with the same three methods."""

    def monotonic(self) -> float:
        """Seconds from a clock that only counts forward. Used for every duration."""
        return time.monotonic()

    def now(self) -> datetime:
        """The local time. Used only to start updates "on the minute"."""
        return datetime.now()

    def wait(self, events: queue.SimpleQueue, timeout: float | None):
        """The next event, or ``None`` when ``timeout`` seconds pass first (``None``: no limit)."""
        if timeout is not None:
            # Very long waits are cut short: the queue can't wait longer than about 290 years,
            # and waking up once an hour costs nothing.
            timeout = min(max(timeout, 0), limits.LONGEST_WAIT)
        try:
            return events.get(timeout=timeout)
        except queue.Empty:
            return None


@dataclass(frozen=True)
class _Finished:
    slot: _Slot
    result: UpdateResult | None
    error: BaseException | None


@dataclass(frozen=True)
class _Written:
    seconds: float
    error: Exception | None
    new_turn: bool
    name: str | None = None
    """The plugin whose image was written."""
    cleared: bool = False
    """The screen was cleared first (also when the write after it failed)."""
    check: bool = False
    """The check at start, not a write."""


@dataclass(frozen=True)
class _Dismiss:
    name: str


_STOP = "stop"
_RELOAD = "reload"


@dataclass(eq=False)
class _Slot:
    """One plugin, and what the scheduler knows about it."""

    config: PluginConfig
    due: float = 0.0
    """When the next update starts (monotonic clock)."""
    running: bool = False
    state: State = State.NOTHING
    image: Image.Image | None = None
    """The latest image; ``None`` when it has nothing, or its last update failed."""
    failures: int = 0
    """Failed updates in a row."""
    alert_since: float | None = None
    """Alert plugins: when the current alert began."""
    dismissed_at: float | None = None
    expired: bool = False
    """Alert plugins: held for ``alert_max_time`` and dismissed; no reminders until a new alert."""
    status: PluginsStatus | None = None
    """``default`` only: the status its latest update was asked to show."""
    reported: bool = False
    """It has finished at least one update (so its state is known)."""
    waits_for: _Slot | None = None
    """After a reload: the old version of this plugin, still updating. This one starts
    when that update has finished, so two updates never use the same storage folder."""

    @property
    def name(self) -> str:
        return self.config.entry.name

    @property
    def level(self) -> str:
        return self.config.entry.level

    @property
    def has_image(self) -> bool:
        return self.image is not None


class Scheduler:
    """Decides what is on ``screen`` and writes it there.

    ``state_dir`` holds each plugin's storage folder (``<state_dir>/plugins/<name>/``).
    ``reload`` returns a freshly loaded config when :meth:`reload` is called. ``clock``,
    ``executor``, ``update`` and ``stop_updates`` are for tests; by default updates run in
    plugin processes with :func:`paperpi.runner.run_update`, at most
    :data:`~paperpi.limits.PARALLEL_UPDATES` at once, and stopping ends the running ones
    with :func:`paperpi.runner.stop_all`. ``writer`` runs the screen writes (default: one
    thread of their own). ``health`` (e.g. :meth:`paperpi.health.Health.report`)
    is called by the loop every :data:`~paperpi.limits.HEALTH_REPORT` seconds.
    """

    def __init__(
        self,
        config: Config,
        screen: Screen,
        *,
        state_dir: Path,
        reload: Callable[[], Config] | None = None,
        clock: Clock | None = None,
        executor: Executor | None = None,
        writer: Executor | None = None,
        update: Update | None = None,
        stop_updates: Callable[[], None] | None = None,
        health: Report | None = None,
        low_disk: LowDisk | None = None,
    ):
        self.screen = screen
        self.state_dir = Path(state_dir)
        self.display = config.display
        self._reload = reload
        self.clock = clock or Clock()
        self.executor = executor or ThreadPoolExecutor(
            max_workers=limits.PARALLEL_UPDATES, thread_name_prefix="paperpi-update"
        )
        self.writer = writer or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="paperpi-screen"
        )
        self._update = update or _run_update
        if stop_updates is None:
            stop_updates = stop_all if update is None else lambda: None
        self._stop_updates = stop_updates
        self._health = health
        self._low_disk = low_disk or LowDisk(self.state_dir)
        self._cleaned: dict[Path, float] = {}
        """When each storage folder was last cleaned (monotonic clock)."""
        self._stopping = False
        self._next_report = -math.inf
        self._last_written: float | None = None
        """When the screen was last written without an error."""
        self._events: queue.SimpleQueue = queue.SimpleQueue()
        self._slots: list[_Slot] = []
        self._default = _Slot(_default_config(config))
        self._fallback = _Slot(_fallback_config()) if config.display.fallback_clock else None
        """The fallback clock, shown when no plugin has anything to show."""
        self._current: _Slot | None = None
        """The plugin on screen."""
        self._turn_start = 0.0
        self._last_rotation: str | None = None
        """The name of the rotation plugin shown last; the rotation goes on after it."""
        self._attempted: Image.Image | None = None
        """The image last sent to the screen (also when the write failed)."""
        self.write_seconds = 0.0
        """How long the last screen write took."""
        self._write_failures = 0
        """Failed screen writes in a row."""
        self._writing = False
        """A screen write is running."""
        self._retry_at: float | None = None
        """While the screen watchdog pauses writes: when to try again."""
        self._shown_by: str | None = None
        """The plugin whose image is on screen (``None``: unknown, so the next write is full)."""
        self._last_clean = -math.inf
        """When the screen was last cleared (monotonic clock): never, so the first write cleans."""
        self._checked = False
        self._apply(config)

    # Called from other threads or signal handlers: they only put an event in the queue.
    # SimpleQueue.put is safe to call from a signal handler.

    def stop(self) -> None:
        """Ask :meth:`run` to end."""
        self._events.put(_STOP)

    def reload(self) -> None:
        """Ask :meth:`run` to load the config again and apply the changes."""
        self._events.put(_RELOAD)

    def dismiss(self, name: str) -> None:
        """Dismiss the alert of the plugin called ``name`` (from the web interface, M5)."""
        self._events.put(_Dismiss(name))

    @property
    def on_screen(self) -> str | None:
        """The name of the plugin on screen."""
        return None if self._current is None else self._current.name

    def run(self) -> None:
        """Show plugins until :meth:`stop` is called."""
        self._stopping = False
        if not self._checked:
            self._checked = True
            self._writing = True
            self.writer.submit(self._check_job, self.clock.monotonic())
        try:
            while True:
                now = self.clock.monotonic()
                self._report(now)
                self._start_due(now)
                self._show(now)
                event = self.clock.wait(self._events, self._wait_time(self.clock.monotonic()))
                # Handle every event that is already waiting, then decide once, so updates
                # that finish together don't each cause a screen write.
                while event is not None:
                    if event == _STOP:
                        return
                    self._handle(event)
                    event = None if self._events.empty() else self._events.get_nowait()
        finally:
            # Drop the updates that have not started, and stop the running ones, so stopping
            # never waits for a hanging plugin's time limit.
            self._stopping = True
            self.executor.shutdown(wait=False, cancel_futures=True)
            self._stop_updates()
            self.executor.shutdown(wait=True)
            # A running write is ended by closing the screen (paperpi.screen.Screen.close).
            self.writer.shutdown(wait=False)

    # Everything below runs in the loop's thread only.

    def _handle(self, event) -> None:
        now = self.clock.monotonic()
        if isinstance(event, _Finished):
            self._finished(event, now)
        elif isinstance(event, _Written):
            self._written(event, now)
        elif isinstance(event, _Dismiss):
            for slot in self._slots:
                if slot.name == event.name and slot.level == "alert":
                    slot.dismissed_at = now
                    log.info("alert %r dismissed", slot.name)
        elif event == _RELOAD and self._reload is not None:
            try:
                new = self._reload()
            except Exception as error:  # noqa: BLE001 - a broken file keeps the old settings
                log.error("config not applied, the old settings keep running: %s", error)
                return
            if new.from_last_good:
                log.error("config file can't be used; the old settings keep running")
                return
            self._apply(new)

    def _report(self, now: float) -> None:
        # Only this loop reports, so the reports stop when the loop is stuck, for example
        # in a screen write that never ends.
        if self._health is None or now < self._next_report:
            return
        since = None if self._last_written is None else now - self._last_written
        self._health(since, self._screen_state)
        self._next_report = now + limits.HEALTH_REPORT

    def _apply(self, config: Config) -> None:
        """Use a new config. Plugins whose settings did not change keep their place and image."""
        if config.display != self.display:
            log.warning("screen settings take effect at the next start of PaperPi")
        now = self.clock.monotonic()
        old = {slot.name: slot for slot in self._slots}
        slots = []
        for found in config.plugins:
            if not found.entry.enabled or found.plugin.type == "default":
                continue
            slot = old.get(found.entry.name)
            if slot is None or not _same_plugin(slot.config, found):
                changed = _Slot(found, due=now)
                if slot is not None:
                    # Keep the old image on screen until the new one is ready, and keep
                    # what is known about its alert (e.g. that it was dismissed).
                    changed.state, changed.image = slot.state, slot.image
                    changed.alert_since, changed.dismissed_at = slot.alert_since, slot.dismissed_at
                    changed.expired, changed.reported = slot.expired, slot.reported
                    if slot.running:
                        changed.due, changed.waits_for = math.inf, slot
                    if slot is self._current:
                        self._current = changed
                slot = changed
            slots.append(slot)
        names = [slot.name for slot in slots]
        if self._last_rotation is not None and self._last_rotation not in names:
            # The plugin shown last was removed: go on after the one before it.
            old_names = [slot.name for slot in self._slots]
            index = old_names.index(self._last_rotation)
            before = old_names[:index][::-1] + old_names[index + 1 :][::-1]
            self._last_rotation = next((n for n in before if n in names), None)
        self._slots = slots
        default = _default_config(config)
        if not _same_plugin(self._default.config, default):
            self._default = _Slot(default)

    def _start_due(self, now: float) -> None:
        for slot in self._slots:
            if not slot.running and slot.due <= now:
                self._start(slot, None)

    def _start(self, slot: _Slot, status: PluginsStatus | None) -> None:
        slot.running = True
        slot.status = status
        found = slot.config
        width, height = self.display.layout_size
        storage = self.state_dir / "plugins" / found.folder_name
        context = Context(
            found.settings, width, height, self.display.screen_mode, storage, found.layout, status
        )
        self.executor.submit(self._job, slot, context)

    def _job(self, slot: _Slot, context: Context) -> None:
        """Runs in a worker thread: one update, then hand the result to the loop."""
        try:
            # Only PaperPi may read the plugins' files: they may hold e.g. downloaded tokens.
            context.storage.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            context.storage.mkdir(mode=0o700, exist_ok=True)
            context = dataclasses.replace(context, low_disk=self._low_disk.check())
            result = self._update(slot.config.plugin.type, context, slot.config.entry.time_limit)
            event = _Finished(slot, result, None)
        except Exception as error:  # noqa: BLE001 - every failure is handled the same way
            event = _Finished(slot, None, error)
        self._clean(slot, context.storage)
        self._events.put(event)

    def _clean(self, slot: _Slot, folder: Path) -> None:
        """Runs in a worker thread, after an update: apply the plugin's storage limits."""
        now = self.clock.monotonic()
        last = self._cleaned.get(folder)
        if self._stopping or (last is not None and now - last < limits.STORAGE_CLEAN_EVERY):
            return  # when stopping: cleaned at the next start anyway
        self._cleaned[folder] = now
        try:
            # Here, not in the plugin process: also after a failed or stopped update.
            clean(folder, slot.config.storage_mb, slot.config.storage_days)
        except Exception as error:  # noqa: BLE001 - a clean-up problem never stops updates
            log.warning("cleaning the folder of %r failed: %s", slot.name, error)

    def _finished(self, event: _Finished, now: float) -> None:
        slot = event.slot
        slot.running = False
        if slot is self._default:
            if event.error is not None:
                log.error("the default plugin failed: %s", event.error)
            else:
                slot.state, slot.image = event.result.state, event.result.image
            return
        if slot is self._fallback:
            if event.error is not None:
                log.error("the fallback clock failed: %s", event.error)
                slot.due = now + slot.config.refresh
            else:
                slot.state, slot.image = event.result.state, event.result.image
                slot.due = self._next_update(slot, now)
            return
        if slot not in self._slots:
            # Removed or changed while it was updating. A changed one can start now.
            for waiting in self._slots:
                if waiting.waits_for is slot:
                    waiting.waits_for, waiting.due = None, now
            return
        slot.reported = True
        if event.error is not None:
            slot.failures += 1
            slot.state, slot.image = State.NOTHING, None
            if slot.failures >= limits.FAILURES_BEFORE_LEFT_OUT:
                slot.due = now + limits.LEFT_OUT
                log.warning(
                    "plugin %r failed %d times in a row; left out for %g minutes: %s",
                    slot.name,
                    slot.failures,
                    limits.LEFT_OUT / 60,
                    event.error,
                )
            else:
                slot.due = self._next_update(slot, now)
                log.warning("plugin %r failed: %s", slot.name, event.error)
            return
        slot.failures = 0
        if slot is self._current and self._write_failures:
            self._attempted = None  # the last screen write failed: try again with this update
        slot.state = event.result.state
        slot.image = None if slot.state is State.NOTHING else event.result.image
        slot.due = self._next_update(slot, now)
        if slot.level == "alert":
            if not slot.has_image:
                slot.alert_since = slot.dismissed_at = None
                slot.expired = False
            elif slot.alert_since is None:
                slot.alert_since = now  # a new alert

    def _next_update(self, slot: _Slot, now: float) -> float:
        refresh = slot.config.refresh
        if not slot.config.plugin.refresh_on_minute:
            return now + refresh
        # Line up with the clock: just after the next multiple of `refresh` since midnight,
        # so a 60 s clock updates at second 1 of every minute.
        wall = self.clock.now()
        midnight = wall.replace(hour=0, minute=0, second=0, microsecond=0)
        since = (wall - midnight).total_seconds() - limits.ON_THE_MINUTE_DELAY
        return now + refresh - since % refresh

    def _alert_active(self, slot: _Slot, now: float) -> bool:
        if slot.alert_since is None or slot.expired or not slot.has_image:
            return False
        if now - slot.alert_since >= slot.config.entry.alert_max_time:
            slot.expired = True
            log.warning(
                "alert %r was active for %g hours and was dismissed",
                slot.name,
                slot.config.entry.alert_max_time / 3600,
            )
            return False
        if slot.dismissed_at is not None:
            return now - slot.dismissed_at >= slot.config.entry.alert_reminder
        return True

    def _show(self, now: float) -> None:
        """Choose what is on screen, and write it when it changed."""
        if self._writing:
            return  # decided again when the write has finished
        if self._retry_at is not None and now >= self._retry_at:
            self._retry_at = None
            self._attempted = None  # the screen watchdog allows a new try
        chosen, new_turn = self._choose(now)
        if chosen is None:
            return
        if not new_turn and self._near_end_of_turn(now):
            # The next plugin takes over before this image would be finished drawing.
            return
        if chosen.level == "rotation" and chosen in self._slots:
            self._last_rotation = chosen.name
        self._current = chosen
        paused = self._retry_at is not None
        if not paused and (
            self._attempted is None or not _same_image(chosen.image, self._attempted)
        ):
            self._write(chosen, new_turn, now)
        elif new_turn:
            self._turn_start = now

    def _choose(self, now: float) -> tuple[_Slot | None, bool]:
        """The plugin to show, and whether a new turn starts."""
        alerts = [s for s in self._slots if s.level == "alert" and self._alert_active(s, now)]
        if alerts:
            return self._take_turns(alerts, now)
        interrupts = [s for s in self._slots if s.level == "interrupt" and s.has_image]
        if interrupts:
            return self._take_turns(interrupts, now)
        rotation = [s for s in self._slots if s.level == "rotation" and s.has_image]
        if rotation:
            if self._current not in rotation:
                # Back from an interrupt, or the plugin on screen has nothing now: go on
                # with the next plugin after the one shown last.
                return self._next(rotation, self._last_rotation), True
            return self._take_turns(rotation, now)
        return self._choose_idle(now), True

    def _take_turns(self, group: list[_Slot], now: float) -> tuple[_Slot, bool]:
        """Keep the plugin on screen until its turn is over, then the next one in ``group``."""
        current = self._current
        if current not in group:
            return group[0], True
        if now - self._turn_start < current.config.entry.display_time:
            return current, False
        return self._next(group, current.name), True

    def _next(self, group: list[_Slot], after: str | None) -> _Slot:
        """The first plugin in ``group`` after the one called ``after``, in config order."""
        names = [s.name for s in self._slots]
        start = names.index(after) + 1 if after in names else 0
        order = self._slots[start:] + self._slots[:start]
        return next(s for s in order if s in group)

    def _choose_idle(self, now: float) -> _Slot | None:
        """No plugin has anything to show.

        When plugins fail, or none are switched on: the ``default`` plugin, which says so.
        Otherwise (e.g. only a music plugin, and no music) the fallback clock, so the screen
        still changes every minute and can be told apart from a broken one.
        """
        failing = sum(1 for s in self._slots if s.failures)
        if failing or not self._slots:
            status = PluginsStatus(failing, len(self._slots))
            default = self._default
            if not default.running and default.status != status:
                self._start(default, status)
            return default if default.has_image else None
        clock = self._fallback
        if clock is None or not all(s.reported for s in self._slots):
            return None  # switched off, or still starting: keep the screen as it is
        if clock.due <= now:
            # Its picture is out of date (it is only updated while it is needed): never
            # show a wrong time, wait for the new one.
            if not clock.running:
                self._start(clock, None)
            return None
        return clock if clock.has_image else None

    def _near_end_of_turn(self, now: float) -> bool:
        current = self._current
        if current is None or current.level != "rotation" or current not in self._slots:
            return False
        others = [s for s in self._slots if s.level == "rotation" and s.has_image]
        if others == [current]:
            return False  # it gets another turn, so there is no next plugin to wait for
        left = self._turn_start + current.config.entry.display_time - now
        return left <= self.write_seconds

    @property
    def _screen_state(self) -> str | None:
        if self._retry_at is not None:
            return "paused"
        if self._write_failures:
            return "failing"
        return None if self._last_written is None else "ok"

    def _write(self, chosen: _Slot, new_turn: bool, now: float) -> None:
        image = chosen.image
        self._attempted = image
        self._writing = True
        rotation = self.display.rotation
        # Rotation turns the picture clockwise.
        image = image.rotate(-rotation, expand=True) if rotation else image
        every = self.display.clean_every
        clean = bool(every) and now - self._last_clean >= every
        fast = not clean and self._shown_by == chosen.name
        job = (self.clock.monotonic(), new_turn, chosen.name, fast, clean)
        self.writer.submit(self._write_job, image, *job)

    def _write_job(
        self,
        image: Image.Image,
        start: float,
        new_turn: bool,
        name: str,
        fast: bool,
        clean: bool,
    ) -> None:
        """Runs in the writer thread: one screen write, then hand the result to the loop."""
        cleared = False
        try:
            if clean:
                self.screen.clear()
                cleared = True
            self.screen.write(image, fast=fast)
            error = None
        except Exception as failed:  # noqa: BLE001 - handled in the loop
            error = failed
        seconds = self.clock.monotonic() - start
        self._events.put(_Written(seconds, error, new_turn, name, cleared))

    def _check_job(self, start: float) -> None:
        """Runs in the writer thread at start: start the screen, to check that it answers."""
        try:
            self.screen.check()
            error = None
        except Exception as failed:  # noqa: BLE001 - handled in the loop
            error = failed
        self._events.put(_Written(self.clock.monotonic() - start, error, False, check=True))

    def _written(self, event: _Written, now: float) -> None:
        self._writing = False
        if isinstance(event.error, ScreenStuck):
            raise event.error  # only a restart of PaperPi can help
        if event.check:
            if event.error is None:
                log.info("the screen answers")
                return
            log.error("the screen does not answer at start: %s; PaperPi keeps running", event.error)
            self._write_failures += 1
            if isinstance(event.error, ScreenResting):
                self._retry_at = now + event.error.wait
            return
        if event.new_turn:
            # The turn starts once it is on screen, or once the try has failed: otherwise a
            # failing screen would hand the turn on again and again without waiting.
            self._turn_start = now
        if event.cleared:
            self._last_clean = now
        if event.error is not None:
            self._write_failures += 1
            self._shown_by = None  # what is on screen is not known now
            if event.cleared:
                self._attempted = None  # the screen is blank now: try again soon
            if isinstance(event.error, ScreenResting):
                self._retry_at = now + event.error.wait
            # Logged once; the same failure again and again would fill the log.
            level = logging.ERROR if self._write_failures == 1 else logging.DEBUG
            log.log(level, "screen write failed: %s", event.error)
            return
        if self._write_failures:
            log.warning("screen writes work again, after %d failed", self._write_failures)
            self._write_failures = 0
        self._retry_at = None
        self._last_written = now
        self.write_seconds = event.seconds
        self._shown_by = event.name

    def _wait_time(self, now: float) -> float | None:
        """Seconds until something is due; ``None`` when only an event can change anything."""
        times = [s.due for s in self._slots if not s.running]
        if self._health is not None:
            times.append(self._next_report)
        if self._writing:
            # Nothing is chosen during a write; only updates and reports can be due.
            later = [t for t in times if now < t < math.inf]
            return min(later) - now if later else None
        if self._retry_at is not None:
            times.append(self._retry_at)
        if any(t <= now for t in times):
            return 0  # something came due while the screen was being written
        if self._current is not None:
            times.append(self._turn_start + self._current.config.entry.display_time)
            if self._current is self._fallback and not self._fallback.running:
                times.append(self._fallback.due)
        for slot in self._slots:
            if slot.alert_since is not None and not slot.expired:
                times.append(slot.alert_since + slot.config.entry.alert_max_time)
                if slot.dismissed_at is not None:
                    times.append(slot.dismissed_at + slot.config.entry.alert_reminder)
        later = [t for t in times if now < t < math.inf]
        if not later:
            return None
        return min(later) - now


def _run_update(plugin_type: str, context: Context, time_limit: float) -> UpdateResult:
    return run_update(plugin_type, context, time_limit=time_limit)


def _default_config(config: Config) -> PluginConfig:
    """The ``default`` block from the config, or one with the default settings."""
    for found in config.plugins:
        if found.plugin.type == "default":
            return found
    plugin = plugins.load("default")
    # Its own storage folder, also when a user names another plugin "default".
    entry = PluginEntry(name="built-in default", type="default")
    return PluginConfig(entry, plugin.settings(), plugin)


def _fallback_config() -> PluginConfig:
    """The fallback clock: basic_clock with one small line of time and date."""
    plugin = plugins.load("basic_clock")
    entry = PluginEntry(name="built-in clock", type="basic_clock", layout="small")
    return PluginConfig(entry, plugin.settings(), plugin)


def _same_plugin(a: PluginConfig, b: PluginConfig) -> bool:
    return a.entry == b.entry and a.settings == b.settings and a.plugin.type == b.plugin.type


def _same_image(a: Image.Image, b: Image.Image) -> bool:
    if a is b:
        return True
    if a.size != b.size or a.mode != b.mode:
        return False
    return ImageChops.difference(a, b).getbbox() is None
