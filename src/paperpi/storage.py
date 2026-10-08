"""Size and age limits for the plugins' storage folders, and the low-disk check.

See "Saved files" in ``docs/decisions/errors-and-time-limits.md``. Each plugin has its own
folder (``<state-dir>/plugins/<id>/``) with two limits, set per plugin (``storage_mb``,
``storage_days``) or suggested by the plugin:

- Files not changed for more than ``storage_days`` days are removed (0: they are kept).
- When the folder holds more than ``storage_mb`` megabytes, the files changed longest ago
  are removed until it fits.

"Changed" is the newer of the file's modification time and its status-change time (which
Linux sets when the file is made, renamed or copied in, and no program can set back), so a
file a plugin writes again at every update (such as a saved forecast) never counts as old,
and a copied file that kept an old modification time is not removed at once. A file that is
only read keeps getting older: a plugin writes it again (or suggests ``storage_days = 0``)
to keep it. Links are not followed and not counted, and a plugin folder that is itself a
link is not cleaned, so cleaning never removes anything outside the plugin's folder. The
size counted is the space the files use on the disk. Empty subfolders are removed.

There is no limit for all plugins together. Instead, when less than
:data:`~paperpi.limits.FREE_DISK_MB` is free on the disk, plugins are told (``low_disk`` in
their :class:`~paperpi.plugin.Context`) so they don't save more. Nothing else is removed:
the space may be used by something outside PaperPi.
"""

from __future__ import annotations

import errno
import logging
import math
import os
import shutil
import stat
import threading
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
    """False when the time limit ran out before the whole folder was read and cleaned."""


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
    long, but can't stop one file operation that hangs inside the operating system. When the
    folder could not be read in time (or holds more than
    :data:`~paperpi.limits.STORAGE_MAX_FILES` files), old files are still removed, but not
    files for the size limit: the oldest ones may be in the part that was not read.

    The folder is read and changed through open folder handles, each opened without
    following links, so a folder swapped for a link in between can't lead outside.
    Folders on another disk (a drive mounted inside the folder) are skipped.
    """
    now = time.time() if now is None else now
    deadline = time.monotonic() + time_limit
    too_old = now - max_days * _DAY if max_days else -math.inf
    try:
        root = os.open(folder, _DIR_FLAGS)
    except FileNotFoundError:
        return Cleaned(0, 0, True)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            log.warning(
                "%s is a link; it is not cleaned (nothing outside PaperPi is removed)", folder
            )
        else:
            log.warning("can't read %s: %s", folder, error)
        return Cleaned(0, 0, True)
    problems = _Problems()
    try:
        scan = _scan(root, os.fstat(root).st_dev, too_old, deadline, problems)
        files = scan.files
        total = sum(size for _, size, _ in files)
        finished = scan.finished
        removed = scan.removed
        if finished and total > max_mb * 1_000_000:
            for parts, size, _ in sorted(files, key=lambda f: f[2]):  # changed longest ago first
                if total <= max_mb * 1_000_000:
                    break
                if time.monotonic() > deadline:
                    finished = False
                    break
                if _unlink(root, parts, problems):
                    removed += 1
                    total -= size
        for parts in sorted(scan.folders, key=len, reverse=True):
            _rmdir(root, parts)  # only works when it is empty
    finally:
        os.close(root)
    if removed:
        log.info("removed %d old file%s from %s", removed, "" if removed == 1 else "s", folder)
    problems.log(folder)
    if not finished:
        log.warning(
            "%s could not be cleaned fully within %g s (or has over %d files); the size "
            "limit waits",
            folder,
            time_limit,
            limits.STORAGE_MAX_FILES,
        )
    return Cleaned(removed, total, finished)


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass
class _Scan:
    files: list[tuple[tuple[str, ...], int, float]]
    """Files kept: (path parts below the folder, space used, changed time)."""
    folders: list[tuple[str, ...]]
    removed: int
    finished: bool


class _Problems:
    """Folders that can't be read and files that can't be removed: logged as one line per
    clean-up, not one per file, so a plugin can't fill the log."""

    def __init__(self):
        self.count = 0
        self.first: str | None = None

    def add(self, what: str) -> None:
        self.count += 1
        self.first = self.first or what

    def log(self, folder: Path) -> None:
        if self.count:
            # %r: a line break in a file name can't start a new log line.
            log.warning("cleaning %s: %d problems, the first: %r", folder, self.count, self.first)


def _scan(root: int, device: int, too_old: float, deadline: float, problems: _Problems) -> _Scan:
    """Read the folder ``root`` (an open handle), removing files changed before ``too_old``."""
    scan = _Scan([], [], 0, True)
    pending: list[tuple[str, ...]] = [()]
    while pending:
        parts = pending.pop()
        try:
            fd = _open(root, parts)
        except OSError as error:
            problems.add(f"{'/'.join(parts)}: {error.strerror}")
            continue
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    if time.monotonic() > deadline or len(scan.files) >= limits.STORAGE_MAX_FILES:
                        scan.finished = False
                        return scan
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(info.st_mode) and info.st_dev == device:
                        pending.append((*parts, entry.name))
                        scan.folders.append((*parts, entry.name))
                    elif stat.S_ISREG(info.st_mode):
                        changed = _changed(info)
                        if changed < too_old:
                            # Removed from the same open folder that was read.
                            try:
                                os.unlink(entry.name, dir_fd=fd)
                                scan.removed += 1
                                continue
                            except FileNotFoundError:
                                continue
                            except OSError as error:
                                problems.add(f"{'/'.join((*parts, entry.name))}: {error.strerror}")
                        scan.files.append(((*parts, entry.name), info.st_blocks * 512, changed))
        finally:
            if fd != root:
                os.close(fd)
    return scan


def _open(root: int, parts: tuple[str, ...]) -> int:
    """An open handle of the folder ``parts`` below ``root``, each step without following
    links (``root`` itself for no parts). The caller closes it."""
    fd = root
    for name in parts:
        try:
            child = os.open(name, _DIR_FLAGS, dir_fd=fd)
        finally:
            if fd != root:
                os.close(fd)
        fd = child
    return fd


def _unlink(root: int, parts: tuple[str, ...], problems: _Problems) -> bool:
    try:
        parent = _open(root, parts[:-1])
    except OSError:
        return False  # gone or swapped for a link: not removed
    try:
        os.unlink(parts[-1], dir_fd=parent)
    except FileNotFoundError:
        return False
    except OSError as error:
        problems.add(f"{'/'.join(parts)}: {error.strerror}")
        return False
    finally:
        if parent != root:
            os.close(parent)
    return True


def _rmdir(root: int, parts: tuple[str, ...]) -> None:
    try:
        parent = _open(root, parts[:-1])
    except OSError:
        return
    try:
        os.rmdir(parts[-1], dir_fd=parent)
    except OSError:
        pass
    finally:
        if parent != root:
            os.close(parent)


def _changed(info: os.stat_result) -> float:
    """When a file was last changed: also copying it in counts (see the module docstring)."""
    return max(info.st_mtime, info.st_ctime)


def clean_all(plugins, state_dir: Path) -> None:
    """Clean the storage folder of every plugin block (``Config.plugins``), also the ones
    switched off. Runs when PaperPi starts, at most
    :data:`~paperpi.limits.STORAGE_CLEAN_START` seconds in all; the rest are cleaned after
    their next update (or at the next start). Folders no block uses (e.g. after a plugin was
    renamed) are left alone, as they may hold photos, but they are named in the log."""
    root = Path(state_dir) / "plugins"
    deadline = time.monotonic() + limits.STORAGE_CLEAN_START
    for found in plugins:
        left = deadline - time.monotonic()
        if left <= 0:
            log.warning("not every plugin folder was cleaned at start; the rest waits")
            break
        limit = min(limits.STORAGE_CLEAN, left)
        clean(root / found.folder_name, found.storage_mb, found.storage_days, time_limit=limit)
    try:
        unused = sorted({p.name for p in root.iterdir()} - {f.folder_name for f in plugins})
    except OSError:
        return
    if unused:
        log.warning(
            "plugin folders no [[plugin]] block uses (not cleaned; remove them by hand if they "
            "are not needed): %r",
            unused[:20],
        )


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
        self._lock = threading.Lock()  # updates check it from several threads

    def check(self) -> bool:
        """True when less than :data:`~paperpi.limits.FREE_DISK_MB` is free. Once low, it
        stays low until :data:`~paperpi.limits.FREE_DISK_GAP_MB` more is free, so a value
        around the limit doesn't flip it at every update."""
        with self._lock:
            return self._check()

    def _check(self) -> bool:
        try:
            free = self._free(self.folder)
        except OSError:
            return False  # can't tell; the health report shows it too
        limit = limits.FREE_DISK_MB
        if self._warned_at is not None:
            limit += limits.FREE_DISK_GAP_MB
        low = free < limit * 1_000_000
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
