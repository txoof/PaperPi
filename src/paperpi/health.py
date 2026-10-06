"""The health report: PaperPi says "still running" to systemd and to a small file.

The reasons are in ``docs/decisions/errors-and-time-limits.md``. In short:

- The scheduler loop calls :meth:`Health.report` every :data:`~paperpi.limits.HEALTH_REPORT`
  seconds. When the loop gets stuck, the reports stop, and after
  :data:`~paperpi.limits.HEALTH_STALE` seconds the watchdog restarts PaperPi.
- Under systemd, each report is a ``WATCHDOG=1`` message (the first one also says
  ``READY=1``), sent with the ``cysystemd`` package. The service needs ``Type=notify``
  (systemd counts PaperPi as started only after ``READY=1``), ``WatchdogSec=120`` (systemd
  restarts PaperPi when no ``WATCHDOG=1`` arrives for 120 seconds) and the default
  ``NotifyAccess=main`` (only messages from the main process count, not from plugin
  processes). Without systemd nothing is sent.
- Each report also replaces the health file (default :data:`HEALTH_FILE`). Docker's health
  check runs ``paperpi health``, which reads it with :func:`check`. The file holds one line
  of JSON: the time of the report, the time since the last screen write, memory use and
  open files of the main process, and free disk. It is replaced, never added to, so it
  can't grow. The file is written first and systemd told after it, so "ready" means the
  file is there.
- Healthy means only "the loop still reports". A broken screen does not make PaperPi
  restart again and again; screen failures are handled by the scheduler itself.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from . import limits
from .files import write_atomic

log = logging.getLogger(__name__)

#: Where ``paperpi run`` writes the health report. On Raspberry Pi OS, ``/run`` is kept in
#: memory and emptied at every start of the Pi, so the report costs no SD card writes and an
#: old report can never look new. Only root can make the folder: the service gets it from
#: systemd (``RuntimeDirectory=paperpi``), and Docker must keep it in memory too (M6).
HEALTH_FILE = Path("/run/paperpi/health")


@dataclass(frozen=True)
class Report:
    """One health report.

    ``monotonic`` is the time of the report on the monotonic clock. On Linux that clock is
    the same for every program on the computer (it counts from the start of the Pi), so
    ``paperpi health`` can compare it with its own. ``time`` is the same moment for people.
    """

    monotonic: float
    time: str
    since_screen: float | None
    """Seconds since the last successful screen write; ``None``: none yet."""
    memory_mb: float | None
    """Memory used by the main PaperPi process."""
    open_files: int | None
    """Files the main PaperPi process has open."""
    free_disk_mb: float | None
    """Free space on the disk that holds PaperPi's files."""


def measure(since_screen: float | None, disk: Path) -> Report:
    """A report about this process, now. A value that can't be measured is ``None``."""
    return Report(
        monotonic=time.monotonic(),  # not rounded: rounded up, it would lie in the future
        time=datetime.now().astimezone().isoformat(timespec="seconds"),
        since_screen=None if since_screen is None else round(since_screen, 1),
        memory_mb=_memory_mb(),
        open_files=_open_files(),
        free_disk_mb=_free_disk_mb(disk),
    )


#: Sends one message to systemd, e.g. ``"WATCHDOG"``.
Notify = Callable[[str], None]


class Health:
    """Sends the health reports of one ``paperpi run``.

    ``path`` is the health file (``None``: no file). ``disk`` is the folder whose free space
    is reported. ``notify`` sends a message to systemd; by default it uses ``cysystemd``,
    and only when systemd asked for messages (``NOTIFY_SOCKET`` in ``environ``).
    """

    def __init__(
        self,
        path: Path | None = HEALTH_FILE,
        *,
        disk: Path,
        notify: Notify | None = None,
        environ: Mapping[str, str] = os.environ,
    ):
        self.path = path
        self.disk = disk
        if notify is None:
            notify = _systemd_notify if environ.get("NOTIFY_SOCKET") else lambda name: None
        self._notify = notify
        self._ready = False
        self._failed: set[str] = set()
        """What failed already; each failure is logged once, not every 30 seconds."""

    def report(self, since_screen: float | None) -> None:
        """Say "still running". Never raises: a failure is logged once (and again only
        when it comes back after working)."""
        if self.path is not None:
            self._write(since_screen)
        if not self._ready:
            # Tried again with every report until it works: systemd waits for it.
            self._ready = self._send("READY")
        self._send("WATCHDOG")

    def _write(self, since_screen: float | None) -> None:
        line = json.dumps(asdict(measure(since_screen, self.disk))) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Anyone may read it: the health check may run as another user. Not forced onto
            # the disk: after a power cut it is out of date anyway.
            write_atomic(self.path, line.encode(), mode=0o644, durable=False)
        except OSError as error:
            self._log_once("file", "can't write the health report to %s: %s", self.path, error)
        else:
            self._failed.discard("file")

    def stopping(self) -> None:
        """Say that PaperPi is stopping on purpose, and remove the health file."""
        self._send("STOPPING")
        if self.path is not None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError as error:
                log.warning("can't remove the health report %s: %s", self.path, error)

    def _send(self, name: str) -> bool:
        """Send one message to systemd; whether it worked."""
        try:
            self._notify(name)
        except Exception as error:  # noqa: BLE001 - cysystemd raises ValueError, RuntimeError...
            self._log_once("systemd", "can't send %s to systemd: %s", name, error)
            return False
        self._failed.discard("systemd")
        return True

    def _log_once(self, what: str, message: str, *args) -> None:
        if what not in self._failed:
            log.warning(message, *args)
            self._failed.add(what)


def check(path: Path = HEALTH_FILE, *, now: float | None = None) -> tuple[bool, str]:
    """Whether the report in ``path`` is recent, and a line that says why.

    ``now`` is the time on the monotonic clock (default: now). Only the time of the report
    counts; the other values are shown for people.
    """
    now = time.monotonic() if now is None else now
    try:
        with open(path, "rb") as file:
            data = file.read(limits.HEALTH_FILE_BYTES + 1)
    except FileNotFoundError:
        return False, f"no health report in {path}: PaperPi is not running, or still starting"
    except OSError as error:
        return False, f"can't read the health report: {error}"
    try:
        if len(data) > limits.HEALTH_FILE_BYTES:
            raise ValueError("too large")
        values = json.loads(data)
        age = now - float(values["monotonic"])
    except (ValueError, KeyError, TypeError) as error:
        return False, f"the health report in {path} can't be read: {error}"
    details = ", ".join(
        f"{key} {values.get(key)}"
        for key in ("since_screen", "memory_mb", "open_files", "free_disk_mb")
    )
    if not -limits.HEALTH_REPORT <= age <= limits.HEALTH_STALE:
        return False, f"not responding: the last report is {age:.0f} s old ({details})"
    # Up to one report interval in the future is accepted above; shown as 0.
    return True, f"healthy: last report {max(age, 0):.0f} s ago ({details})"


def _systemd_notify(name: str) -> None:
    # Imported here: the package is only needed when PaperPi runs under systemd.
    from cysystemd.daemon import Notification, notify

    notify(Notification[name], return_exceptions=False)


def _memory_mb() -> float | None:
    try:
        resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
    except (OSError, IndexError, ValueError):
        return None
    return round(resident_pages * os.sysconf("SC_PAGE_SIZE") / 1_000_000, 1)


def _open_files() -> int | None:
    try:
        # Listing the folder opens it, so it counts itself once.
        return len(os.listdir("/proc/self/fd")) - 1
    except OSError:
        return None


def _free_disk_mb(disk: Path) -> float | None:
    try:
        return round(shutil.disk_usage(disk).free / 1_000_000, 1)
    except OSError:
        return None
