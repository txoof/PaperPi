"""``paperpi reload``: tell the running ``paperpi run`` to load the config file again, and
say what happened (issue #272, agreed with txoof on 2026-10-24).

1. It reads the edited config file and compares it with the last good copy in the state
   folder, the file PaperPi loaded last (the same comparison as the web interface's Review
   changes page, :func:`paperpi.web.changes.review`). A file with a mistake is not sent:
   PaperPi would refuse it anyway, and the old settings keep running.
2. It finds the running PaperPi by the process id in the health report
   (:mod:`paperpi.health`), which PaperPi writes every 30 seconds and removes when it stops.
3. It sends that process the reload signal (SIGHUP, the same as ``kill -HUP``) and waits up
   to :data:`~paperpi.limits.RELOAD_WAIT` seconds until a new health report holds the
   result of a newer reload. PaperPi sends that report right after loading the file.

With ``--check`` it stops after step 1: it names the mistakes and the changes, and sends
nothing, so it also works when PaperPi is not running.

The last good copy is saved only from a file without any mistake. After a file with a
mistake in one plugin block was applied, the list may also show changes PaperPi already
uses.
"""

from __future__ import annotations

import os
import signal
import time
from collections.abc import Callable
from pathlib import Path

from . import config, health, limits
from .config import ConfigError
from .web.changes import Change, Review, review

#: Exit status: applied (or, with ``--check``, the file can be used).
OK = 0
#: Exit status: not applied, or the file has a mistake.
FAILED = 1


def run(
    config_path: Path,
    state_dir: Path,
    health_file: Path,
    *,
    check_only: bool = False,
    kill: Callable[[int, int], None] = os.kill,
    is_paperpi: Callable[[int], bool] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, list[str]]:
    """Do ``paperpi reload``; the exit status and the lines to print.

    ``kill``, ``is_paperpi`` (whether a process is ``paperpi run``), ``clock`` and ``sleep``
    are for tests.
    """
    try:
        edited = config.read_text(config_path)
    except ConfigError as error:
        return FAILED, [f"Can't read the config file: {error}"]
    found = review(_applied(state_dir) or "", edited, str(config_path))
    if found.mistakes:
        return FAILED, [
            "The config file has a mistake, so it can't be applied:",
            *(f"  {line}" for line in found.mistakes),
            "Nothing was sent; PaperPi keeps running with the old settings.",
        ]
    listed = _listed(found, state_dir)
    if check_only:
        return OK, ["The config file can be used.", *listed]

    pid, problem = _find(health_file, is_paperpi or _is_paperpi)
    if pid is None:
        return FAILED, [problem]
    before = _reload_number(health.read(health_file))
    try:
        kill(pid, signal.SIGHUP)
    except PermissionError:
        return FAILED, [
            f"No permission to send PaperPi (process id {pid}) the reload signal. "
            "Run this command as the same user as PaperPi, or with sudo: sudo paperpi reload"
        ]
    except ProcessLookupError:
        return FAILED, ["PaperPi is not running (it stopped just now)."]

    end = clock() + limits.RELOAD_WAIT
    while clock() < end:
        sleep(0.2)
        try:
            values = health.read(health_file)
        except FileNotFoundError:
            return FAILED, ["PaperPi stopped before it loaded the config file."]
        except (OSError, ValueError):
            continue  # read again
        if values.get("pid") != pid:
            return FAILED, ["PaperPi started again before it loaded the config file."]
        result = values.get("reload")
        if _reload_number(values) > before and isinstance(result, dict):
            errors = result.get("errors") or []
            if errors:
                return FAILED, [
                    "PaperPi could not use the config file; the old settings keep running:",
                    *(f"  {line}" for line in errors),
                ]
            return OK, ["Applied.", *listed]
    return FAILED, [
        f"Sent the reload signal, but PaperPi did not answer within "
        f"{limits.RELOAD_WAIT:.0f} seconds. It may still be busy; its log says more."
    ]


def describe(found: Review) -> list[str]:
    """The changes as lines for a terminal, like the Review changes page shows them."""
    lines = []
    for group in found.groups:
        head = group.title
        if group.plugin_id and group.plugin_id != group.title:
            head += f" ({group.plugin_id})"
        if group.status == "added":
            head += ": new plugin"
        elif group.status == "removed":
            head += ": removed"
        lines.append(head)
        if group.note:
            lines.append(f"  {group.note}")
        for change in group.changes:
            if group.status == "added":
                line = f"  {change.key} = {_value(change.new, change)}"
            else:
                line = f"  {change.key}: {_value(change.old, change)} -> "
                line += _value(change.new, change)
            lines.append(f"{line}  ({change.note})" if change.note else line)
    return lines


def _listed(found: Review, state_dir: Path) -> list[str]:
    """The lines about the changes and the plugin blocks that will be left out."""
    if _applied(state_dir) is None:
        listed = [f"(The changes can't be listed: no last good copy of the config in {state_dir}.)"]
    elif found.groups:
        listed = ["Changes:", *(f"  {line}" for line in describe(found))]
    else:
        listed = ["No changes in the settings."]
    if found.problems:
        listed += [
            "These plugins have a mistake; PaperPi leaves them out until it is fixed:",
            *(f"  {line}" for line in found.problems),
        ]
    return listed


def _value(shown: str | None, change: Change) -> str:
    if shown is not None:
        return shown
    return "(not set)" if change.default is None else f"(default: {change.default})"


def _applied(state_dir: Path) -> str | None:
    """The config text PaperPi loaded last; ``None``: not known."""
    try:
        return config.read_text(Path(state_dir) / config.LAST_GOOD_NAME)
    except ConfigError:
        return None


def _find(health_file: Path, is_paperpi: Callable[[int], bool]) -> tuple[int | None, str]:
    """The process id of the running PaperPi, or ``None`` and why it can't be used."""
    healthy, message = health.check(health_file)
    if not healthy:
        if not health_file.exists():
            return None, (
                f"PaperPi is not running: there is no health report in {health_file}. "
                "A PaperPi started by hand writes it only where it may: give paperpi run and "
                "paperpi reload the same --health-file (or use kill -HUP <process id>)."
            )
        return None, f"PaperPi can't be reached: {message}"
    try:
        pid = health.read(health_file)["pid"]
    except (OSError, ValueError, KeyError) as error:
        return None, f"The health report in {health_file} can't be used: {error}"
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        return None, f"The health report in {health_file} has no process id."
    if not is_paperpi(pid):
        return None, f"Process {pid} from the health report is not PaperPi."
    return pid, ""


def _reload_number(values: dict) -> int:
    result = values.get("reload")
    number = result.get("number") if isinstance(result, dict) else None
    return number if isinstance(number, int) else 0


def _is_paperpi(pid: int) -> bool:
    """Whether process ``pid`` runs ``paperpi run``: after a crash, the health report stays
    for a while, and its process id may then belong to another program."""
    try:
        parts = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    # ".../bin/paperpi run ..." or "python -m paperpi run ...".
    names = [os.path.basename(part) for part in parts[:3]]
    return b"paperpi" in names and b"run" in parts
