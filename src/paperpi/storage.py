"""Size and age limits for the plugins' storage folders, and the low-disk check.

See "Saved files" in ``docs/decisions/errors-and-time-limits.md``. Each plugin has its own
folder (``<state-dir>/plugins/<name>/``) with two limits, set per plugin (``storage_mb``,
``storage_days``) or suggested by the plugin:

- Files not changed for more than ``storage_days`` days are removed (0: they are kept).
- When the folder holds more than ``storage_mb`` megabytes, the files changed longest ago
  are removed until it fits.

"Changed" is the file's modification time, so a file a plugin writes again at every update
(such as a saved forecast) never counts as old. Links are not followed and not counted, so
cleaning never removes anything outside the plugin's folder.

There is no limit for all plugins together. Instead, when less than
:data:`~paperpi.limits.FREE_DISK_MB` is free on the disk, plugins are told (``low_disk`` in
their :class:`~paperpi.plugin.Context`) so they don't save more. Nothing else is removed:
the space may be used by something outside PaperPi.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import limits

log = logging.getLogger(__name__)

_DAY = 24 * 60 * 60


@dataclass(frozen=True)
class Cleaned:
    """What one clean-up did."""

    removed: int
    """Files removed."""
    kept_bytes: int
    """Size of the files that are left."""
    finished: bool
    """False when the time limit ran out before the whole folder was checked."""


def clean(
    folder: Path,
    max_mb: int,
    max_days: int,
    *,
    now: float | None = None,
    time_limit: float = limits.STORAGE_CLEAN,
) -> Cleaned:
    """Apply the size and age limits to ``folder``. A missing folder is fine.

    ``now`` is the time to compare file ages with (default: the current time). The time
    limit is checked between files: it stops a folder with very many files from taking too
    long, but can't stop one file operation that hangs inside the operating system.
    """
    now = time.time() if now is None else now
    deadline = time.monotonic() + time_limit
    files, finished = _files(folder, deadline)
    removed = 0
    if max_days:
        too_old = now - max_days * _DAY
        kept = []
        for found in files:
            if found[2] < too_old and _remove(found[0]):
                removed += 1
            else:
                kept.append(found)
        files = kept
    total = sum(size for _, size, _ in files)
    if total > max_mb * 1_000_000:
        for path, size, _ in sorted(files, key=lambda f: f[2]):  # changed longest ago first
            if total <= max_mb * 1_000_000 or time.monotonic() > deadline:
                break
            if _remove(path):
                removed += 1
                total -= size
    if removed:
        log.info("removed %d old file%s from %s", removed, "" if removed == 1 else "s", folder)
    if not finished:
        log.warning("cleaning %s took longer than %g s; the rest waits", folder, time_limit)
    return Cleaned(removed, total, finished)


def _files(folder: Path, deadline: float) -> tuple[list[tuple[Path, int, float]], bool]:
    """Every plain file below ``folder``: (path, size, modification time), and whether the
    whole folder was read before the deadline. Links are not followed."""
    found = []
    folders = [folder]
    while folders:
        if time.monotonic() > deadline:
            return found, False
        try:
            entries = list(os.scandir(folders.pop()))
        except FileNotFoundError:
            continue
        except OSError as error:
            log.warning("can't read %s: %s", folder, error)
            continue
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(info.st_mode):
                folders.append(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                found.append((Path(entry.path), info.st_size, info.st_mtime))
    return found, True


def _remove(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError as error:
        log.warning("can't remove %s: %s", path, error)
        return False
    return True


def clean_all(plugins, state_dir: Path) -> None:
    """Clean the storage folder of every plugin block (``Config.plugins``), also the ones
    switched off. Runs when PaperPi starts."""
    for found in plugins:
        folder = Path(state_dir) / "plugins" / found.folder_name
        clean(folder, found.storage_mb, found.storage_days)


class LowDisk:
    """Says whether the disk that holds ``folder`` is low, and warns about it.

    The warning is logged when the disk becomes low, repeated every
    :data:`~paperpi.limits.LOW_DISK_REPEAT` seconds while it stays low, and a line follows
    when there is enough space again. ``clock`` (monotonic) and ``free`` (free bytes) are
    for tests.
    """

    def __init__(
        self,
        folder: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        free: Callable[[Path], int] | None = None,
    ):
        self.folder = Path(folder)
        self.clock = clock
        self._free = free or (lambda path: shutil.disk_usage(path).free)
        self._warned_at: float | None = None

    def check(self) -> bool:
        """True when less than :data:`~paperpi.limits.FREE_DISK_MB` is free."""
        try:
            free = self._free(self.folder)
        except OSError:
            return False  # can't tell; the health report shows it too
        low = free < limits.FREE_DISK_MB * 1_000_000
        now = self.clock()
        if low and (self._warned_at is None or now - self._warned_at >= limits.LOW_DISK_REPEAT):
            log.warning(
                "only %d MB free on the disk of %s; plugins are asked not to save more "
                "(PaperPi keeps %d MB free)",
                free // 1_000_000,
                self.folder,
                limits.FREE_DISK_MB,
            )
            self._warned_at = now
        elif not low and self._warned_at is not None:
            log.warning("the disk of %s has enough free space again", self.folder)
            self._warned_at = None
        return low
