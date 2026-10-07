"""Changing the config file from the web interface, keeping everything else in it as it is.

- :func:`read` and :func:`write` read the file and save a changed copy that keeps the old
  file's permissions (and owner, when run as root).
- The plugin changes (:func:`move`, :func:`remove`, :func:`set_enabled`, :func:`add`) work on
  the file's text, one ``[[plugin]]`` block at a time. The comment lines just above a
  ``[[plugin]]`` line belong to that block and move with it.
- Every change is checked before it is saved: PaperPi must read the new text back as exactly
  the old settings plus the change. A file written in a way these functions don't
  understand is never saved wrongly; :class:`EditError` says so instead.
- Each change names its block by place and name, so a block that was moved or removed by
  hand a moment ago is not changed by mistake (:class:`ChangedMeanwhile`).
"""

from __future__ import annotations

import os
import re
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import config
from ..files import write_atomic


class EditError(ValueError):
    """The config file can't be read, changed or saved; the message says why."""


class ChangedMeanwhile(EditError):
    """The block to change is not where the page showed it: the file changed meanwhile."""


def read(path: Path) -> tuple[Path, str]:
    """The real path of the config file (links followed) and its text."""
    # A config file that is a link to another file: change the file it points to.
    path = Path(os.path.realpath(path))
    try:
        return path, config.read_text(path)
    except config.ConfigError as error:
        raise EditError(str(error)) from None


def write(path: Path, text: str) -> None:
    """Save ``text`` as the config file at ``path`` (a real path, from :func:`read`)."""
    try:
        # The new file keeps the old one's permissions and, when run with sudo, its owner,
        # so the PaperPi service can still read it.
        info = os.stat(path)
        owner = (info.st_uid, info.st_gid) if os.geteuid() == 0 else None
        write_atomic(path, text.encode("utf-8"), mode=stat.S_IMODE(info.st_mode), owner=owner)
    except OSError as error:
        raise EditError(f"can't save {path}: {error}") from None


def load(text: str) -> dict[str, Any]:
    """The settings in ``text``, as PaperPi reads them."""
    try:
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, RecursionError, ValueError) as error:
        raise EditError(f"the config file is not valid TOML: {error}") from None


@dataclass(frozen=True)
class Block:
    """Where one ``[[plugin]]`` block is in the file (line numbers count from 0)."""

    start: int
    """The first line: the comments just above the ``[[plugin]]`` line, or that line."""
    header: int
    """The ``[[plugin]]`` line."""
    own_end: int
    """The line after its own settings (where a ``[plugin.x]`` part or the next part starts)."""
    end: int
    """The line after the block, including blank lines and ``[plugin.x]`` parts."""


_HEADER = re.compile(r"\s*(\[\[?)\s*([A-Za-z0-9_.-]+)\s*\]\]?\s*(#.*)?")
_ENABLED = re.compile(r"\s*enabled\s*=")


def blocks(text: str) -> list[Block]:
    """The ``[[plugin]]`` blocks in ``text``, in file order."""
    lines = text.splitlines()
    starts: list[tuple[int, str]] = []  # (line, "plugin" / "part of plugin" / "other")
    quote = None  # inside a multi-line string: the quotes it started with
    for number, line in enumerate(lines):
        inside = quote is not None
        for found in re.finditer(r'"""|\'\'\'', line):
            if quote is None:
                quote = found.group()
            elif found.group() == quote:
                quote = None
        header = None if inside else _HEADER.fullmatch(line)
        if header:
            brackets, name = header.group(1), header.group(2)
            if brackets == "[[" and name == "plugin":
                starts.append((number, "plugin"))
            elif name.startswith("plugin."):
                starts.append((number, "part of plugin"))
            else:
                starts.append((number, "other"))
    found: list[Block] = []
    for index, (header, kind) in enumerate(starts):
        if kind != "plugin":
            continue
        later = starts[index + 1 :]
        own_end = later[0][0] if later else len(lines)
        after = next((n for n, k in later if k != "part of plugin"), len(lines))
        end = _comments_above(lines, after, header + 1) if after < len(lines) else after
        lowest = max((n + 1 for n, _ in starts[:index]), default=0)
        found.append(Block(_comments_above(lines, header, lowest), header, own_end, end))
    return found


def _comments_above(lines: list[str], line: int, lowest: int) -> int:
    """The first of the comment lines just above ``line`` (or ``line`` itself)."""
    while line > lowest and lines[line - 1].lstrip().startswith("#"):
        line -= 1
    return line


def plugin_blocks(data: dict[str, Any]) -> list[Any]:
    """The ``[[plugin]]`` blocks of the loaded settings (as written, also broken ones)."""
    found = data.get("plugin", [])
    return found if isinstance(found, list) else []


def name_of(block: Any) -> str:
    """The name of a loaded plugin block, or ``""`` when it has none (a broken block)."""
    name = block.get("name") if isinstance(block, dict) else None
    return name if isinstance(name, str) else ""


def move(text: str, index: int, name: str, step: int) -> str:
    """``text`` with plugin block ``index`` moved one place up (``step=-1``) or down (``1``)."""
    data, found = _check(text, index, name)
    other = index + step
    if step not in (-1, 1) or not 0 <= other < len(found):
        raise EditError("this plugin can't move further")
    first, second = sorted((index, other))
    a, b = found[first], found[second]
    lines = _lines(text)
    new = [
        *lines[: a.start],
        *_spaced(lines[b.start : b.end]),
        *lines[a.end : b.start],
        *lines[a.start : a.end],
        *lines[b.end :],
    ]
    expected = plugin_blocks(data)
    expected[first], expected[second] = expected[second], expected[first]
    return _checked("".join(new), data | {"plugin": expected})


def remove(text: str, index: int, name: str) -> str:
    """``text`` without plugin block ``index``."""
    data, found = _check(text, index, name)
    block = found[index]
    lines = _lines(text)
    new = "".join([*lines[: block.start], *lines[block.end :]])
    expected = plugin_blocks(data)
    del expected[index]
    data = {k: v for k, v in data.items() if k != "plugin"}
    return _checked(new, data | {"plugin": expected} if expected else data)


def set_enabled(text: str, index: int, name: str, enabled: bool) -> str:
    """``text`` with plugin block ``index`` switched on or off.

    Off writes ``enabled = false``; on removes that line, because the file only holds
    settings that differ from the default.
    """
    data, found = _check(text, index, name)
    block = found[index]
    lines = _lines(text)
    own = range(block.header + 1, block.own_end)
    at = [n for n in own if _ENABLED.match(lines[n]) and not _in_string(text, n)]
    if enabled:
        new = [line for n, line in enumerate(lines) if n not in at]
    else:
        new = list(lines)
        if at:
            new[at[0]] = "enabled = false\n"
        else:
            after = _setting_line(lines, own, "type") or _setting_line(lines, own, "name")
            new.insert((after or block.header) + 1, "enabled = false\n")
    expected = plugin_blocks(data)
    changed = {k: v for k, v in expected[index].items() if k != "enabled"}
    expected[index] = changed if enabled else changed | {"enabled": False}
    return _checked("".join(new), data | {"plugin": expected})


def add(text: str, block_text: str) -> str:
    """``text`` with ``block_text`` (one ``[[plugin]]`` block, as written by
    :func:`paperpi.example.plugin_block`) added after the last plugin block."""
    data = load(text)
    found = blocks(text)
    if len(found) != len(plugin_blocks(data)):
        raise EditError(_UNKNOWN_FORM)
    new_block = plugin_blocks(load(block_text))
    lines = _lines(text)
    at = found[-1].end if found else len(lines)
    before = "".join(lines[:at])
    after = "".join(lines[at:])
    gap = "" if not before or before.endswith("\n\n") else "\n"
    new = before + gap + block_text + ("\n" + after if after else "")
    return _checked(new, data | {"plugin": [*plugin_blocks(data), *new_block]})


_UNKNOWN_FORM = (
    "the plugin blocks in the config file are written in a way the web interface can't "
    "change safely; change it by hand"
)


def _check(text: str, index: int, name: str) -> tuple[dict[str, Any], list[Block]]:
    data = load(text)
    found = blocks(text)
    raw = plugin_blocks(data)
    if len(found) != len(raw):
        raise EditError(_UNKNOWN_FORM)
    if not 0 <= index < len(raw):
        raise ChangedMeanwhile(_MEANWHILE)
    if name_of(raw[index]) != name:
        raise ChangedMeanwhile(_MEANWHILE)
    return data, found


_MEANWHILE = "the config file was changed meanwhile; look at the list again and retry"


def _checked(new: str, expected: dict[str, Any]) -> str:
    """``new``, after checking that PaperPi reads it back as ``expected``."""
    try:
        read_back = tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        read_back = None
    if read_back != expected:
        raise EditError(_UNKNOWN_FORM)
    return new


def _lines(text: str) -> list[str]:
    """The lines of ``text``, each ending with a line break."""
    return [line if line.endswith("\n") else line + "\n" for line in text.splitlines(True)]


def _spaced(chunk: list[str]) -> list[str]:
    """``chunk`` ending with a blank line, so it stays apart from the block after it."""
    return chunk if chunk and not chunk[-1].strip() else [*chunk, "\n"]


def _setting_line(lines: list[str], within: range, key: str) -> int | None:
    pattern = re.compile(rf"\s*{key}\s*=")
    return next((n for n in within if pattern.match(lines[n])), None)


def _in_string(text: str, line: int) -> bool:
    """True when line ``line`` starts inside a multi-line string."""
    before = "\n".join(text.splitlines()[:line])
    quote = None
    for found in re.finditer(r'"""|\'\'\'', before):
        if quote is None:
            quote = found.group()
        elif found.group() == quote:
            quote = None
    return quote is not None
