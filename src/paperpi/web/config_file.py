"""Changing the config file from the web interface, keeping everything else in it as it is.

- :func:`read` and :func:`write` read the file and save a changed copy that keeps the old
  file's permissions (and owner, when run as root). Hold :data:`LOCK` from reading to
  saving, so two changes at the same moment (a plugin and the password) can't undo each
  other. :func:`saved_here` tells whether a text is the one the web interface saved last.
- The plugin changes (:func:`move`, :func:`remove`, :func:`set_enabled`, :func:`set_settings`,
  :func:`add`) work on the file's text, one ``[[plugin]]`` block at a time. The comment lines
  just above a ``[[plugin]]`` line (with a blank line above them) belong to that block: they
  move with it and are removed with it. A comment at the end of a setting's line (such as
  ``enabled =``) is lost when that setting is changed.
- Every change is checked before it is saved: PaperPi must read the new text back as exactly
  the old settings plus the change. A file written in a way these functions don't
  understand (for example a ``[[plugin]]`` line written differently, or a value line
  that looks like a ``[part]`` line) is never saved wrongly: :class:`UnknownForm` says to
  change it by hand instead.
- Each change names its block by place and ID, so a block that was moved or removed by
  hand a moment ago is not changed by mistake (:class:`ChangedMeanwhile`).
"""

from __future__ import annotations

import os
import re
import stat
import threading
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit

from .. import config, example, limits
from ..files import write_atomic

#: Held from reading the config file to saving the changed copy.
LOCK = threading.Lock()
_saved: dict[Path, str] = {}


class EditError(ValueError):
    """The config file can't be read, changed or saved; the message says why."""


class ChangedMeanwhile(EditError):
    """The block to change is not where the page showed it: the file changed meanwhile."""

    def __init__(self) -> None:
        super().__init__(
            "The config file changed after this page was opened. Check the list and try again."
        )


class UnknownForm(EditError):
    """The file is written in a way these functions can't change safely."""

    def __init__(self) -> None:
        super().__init__(
            "The plugin list in the config file is written in a way the web interface can't "
            "change safely. Make this change in the config file itself."
        )


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
    data = text.encode("utf-8")
    if len(data) > limits.CONFIG_FILE_BYTES:
        raise EditError(
            f"The config file would be larger than {limits.CONFIG_FILE_BYTES} bytes, which "
            "PaperPi can't read. Remove a plugin first."
        )
    try:
        # The new file keeps the old one's permissions and, when run with sudo, its owner,
        # so the PaperPi service can still read it.
        info = os.stat(path)
        owner = (info.st_uid, info.st_gid) if os.geteuid() == 0 else None
        write_atomic(path, data, mode=stat.S_IMODE(info.st_mode), owner=owner)
    except OSError as error:
        raise EditError(f"can't save {path}: {error}") from None
    _saved[path] = text


def saved_here(path: Path, text: str) -> bool:
    """True when ``text`` is what the web interface saved last as the config file ``path``."""
    return _saved.get(Path(os.path.realpath(path))) == text


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


@dataclass(frozen=True)
class _Scan:
    lines: list[str]
    """The lines, each with its line break (TOML only breaks lines at ``\\n``)."""
    in_string: frozenset[int]
    """Lines that start inside a multi-line string."""
    blocks: list[Block]


def _scan(text: str) -> _Scan:
    lines = re.split(r"(?<=\n)", text)
    if lines and lines[-1] == "":
        lines.pop()
    plain = [line.rstrip("\r\n") for line in lines]
    starts: list[tuple[int, str]] = []  # (line, "plugin" / "part of plugin" / "other")
    in_string = set()
    quote = None  # inside a multi-line string: the quotes it started with
    for number, line in enumerate(plain):
        if quote is not None:
            in_string.add(number)
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
        end = _comments_above(plain, after, header + 1) if after < len(lines) else after
        lowest = max((n + 1 for n, _ in starts[:index]), default=0)
        found.append(Block(_comments_above(plain, header, lowest), header, own_end, end))
    return _Scan(lines, frozenset(in_string), found)


def blocks(text: str) -> list[Block]:
    """The ``[[plugin]]`` blocks in ``text``, in file order."""
    return _scan(text).blocks


def _comments_above(lines: list[str], line: int, lowest: int) -> int:
    """The first of the comment lines just above ``line``, when a blank line (or the start
    of the file) is above them; else ``line`` itself: then they belong to what is above."""
    start = line
    while start > lowest and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    if start == line or start == 0 or not lines[start - 1].strip():
        return start
    return line


def plugin_blocks(data: dict[str, Any]) -> list[Any]:
    """The ``[[plugin]]`` blocks of the loaded settings (as written, also broken ones)."""
    found = data.get("plugin", [])
    return found if isinstance(found, list) else []


def id_of(block: Any) -> str:
    """The ID of a loaded plugin block, or ``""`` when it has none (a broken block)."""
    plugin_id = block.get("id") if isinstance(block, dict) else None
    return plugin_id if isinstance(plugin_id, str) else ""


def move(text: str, index: int, plugin_id: str, step: int) -> str:
    """``text`` with plugin block ``index`` moved one place up (``step=-1``) or down (``1``)."""
    data, scan = _check(text, index, plugin_id)
    other = index + step
    if step not in (-1, 1) or not 0 <= other < len(scan.blocks):
        raise EditError("This plugin can't move further.")
    first, second = sorted((index, other))
    a, b = scan.blocks[first], scan.blocks[second]
    lines = _ended(scan.lines)
    new = [
        *lines[: a.start],
        *_spaced(lines[b.start : b.end], _newline(lines)),
        *lines[a.end : b.start],
        *lines[a.start : a.end],
        *lines[b.end :],
    ]
    expected = plugin_blocks(data)
    expected[first], expected[second] = expected[second], expected[first]
    return _checked("".join(new), data | {"plugin": expected})


def remove(text: str, index: int, plugin_id: str) -> str:
    """``text`` without plugin block ``index`` (and the comments just above it)."""
    data, scan = _check(text, index, plugin_id)
    block = scan.blocks[index]
    new = "".join([*scan.lines[: block.start], *scan.lines[block.end :]])
    expected = plugin_blocks(data)
    del expected[index]
    data = {k: v for k, v in data.items() if k != "plugin"}
    return _checked(new, data | {"plugin": expected} if expected else data)


def set_enabled(text: str, index: int, plugin_id: str, enabled: bool) -> str:
    """``text`` with plugin block ``index`` switched on or off.

    Off writes ``enabled = false``; on removes that line, because the file only holds
    settings that differ from the default.
    """
    data, scan = _check(text, index, plugin_id)
    block = scan.blocks[index]
    lines = _ended(scan.lines)
    own = [n for n in range(block.header + 1, block.own_end) if n not in scan.in_string]
    at = [n for n in own if re.match(r"\s*enabled\s*=", lines[n])]
    line = "enabled = false" + _newline(lines)
    if enabled:
        new = [kept for n, kept in enumerate(lines) if n not in at]
    else:
        new = list(lines)
        if at:
            new[at[0]] = line
        else:
            after = _setting_line(lines, own, "type") or _setting_line(lines, own, "id")
            new.insert((after or block.header) + 1, line)
    expected = plugin_blocks(data)
    changed = {k: v for k, v in expected[index].items() if k != "enabled"}
    expected[index] = changed if enabled else changed | {"enabled": False}
    return _checked("".join(new), data | {"plugin": expected})


def set_settings(
    text: str,
    index: int,
    plugin_id: str,
    values: Mapping[str, Any],
    defaults: Mapping[str, Any] | None = None,
) -> str:
    """``text`` with settings of plugin block ``index`` changed: ``values`` maps a setting
    to its new value, or to ``None`` to remove it (back to its default).

    - A setting that is in the block gets its new value on the same line (a comment at the
      end of that line is lost).
    - A new one replaces a ``# key = ...`` comment line, so the help text above it stays.
      Without one, ``name`` goes below ``id`` and the others below the block's last setting.
    - A removed setting with a value in ``defaults`` becomes the comment ``# key = default``
      (``# key =`` for ``None``), as in the example config; others are taken out.
    - A setting written over several lines can't be changed: :class:`UnknownForm`.
    """
    defaults = defaults or {}
    data, scan = _check(text, index, plugin_id)
    block = scan.blocks[index]
    lines = _ended(scan.lines)
    newline = _newline(lines)
    own = [n for n in range(block.header + 1, block.own_end) if n not in scan.in_string]
    expected = plugin_blocks(data)
    changed = dict(expected[index])
    new: dict[int, str | None] = {}  # line -> its new text (None: taken out)
    added: list[tuple[str, str]] = []  # (setting, line) with no place in the block yet
    for key, value in values.items():
        at = _setting_line(lines, own, re.escape(key))
        if at is not None and not _one_line(lines[at]):
            raise UnknownForm()
        commented = _commented_setting(lines, own, key)
        if value is None:
            changed.pop(key, None)
            if at is not None:
                # Back to "# key = default", unless the block has that comment already.
                new[at] = None if commented is not None else _default_line(key, defaults, newline)
            continue
        changed[key] = example.plain(value)
        line = f"{_key(key)} = {example.toml_value(value)}{newline}"
        if at is None:
            at = commented  # a commented-out setting, so its help text above stays
        if at is None:
            added.append((key, line))
        else:
            new[at] = line

    def setting_after(number: int) -> bool:
        line = new.get(number, lines[number])
        return line is not None and bool(line.strip()) and not line.lstrip().startswith("#")

    last = max((n for n in own if setting_after(n)), default=block.header)
    below: dict[int, list[str]] = {}  # line -> new lines to put below it
    for key, line in added:
        at = _setting_line(lines, own, "id") if key == "name" else None
        at = _value_end(lines, last if at is None else at, block.own_end)
        below.setdefault(at, []).append(line)
    result = []
    for number, line in enumerate(lines):
        replaced = new.get(number, line)
        if replaced is not None:
            result.append(replaced)
        result += below.get(number, [])
    expected[index] = changed
    return _checked("".join(result), data | {"plugin": expected})


def _value_end(lines: list[str], line: int, end: int) -> int:
    """The last line of the setting that starts on ``line``: a list or a text written over
    several lines ends further down. ``line`` itself when it is not a setting."""
    if not _HEADER.fullmatch(lines[line].rstrip("\r\n")) and not _one_line(lines[line]):
        for last in range(line + 1, end):
            if _one_line("".join(lines[line : last + 1])):
                return last
    return line


def _commented_setting(lines: list[str], within: list[int], key: str) -> int | None:
    """The line of a commented-out ``key``: ``# key = value`` (a setting without the ``#``)
    or ``# key =`` (not set), not a help text that starts the same way."""
    for number in within:
        line = lines[number].strip()
        if not re.match(rf"#\s*{re.escape(key)}\s*=", line):
            continue
        if _one_line(line[1:]) or re.fullmatch(rf"#\s*{re.escape(key)}\s*=", line):
            return number
    return None


def _key(key: str) -> str:
    """``key`` as written in a TOML file (in quotes when it needs them)."""
    return tomlkit.key(key).as_string()


def _default_line(key: str, defaults: Mapping[str, Any], newline: str) -> str | None:
    """The comment that takes the place of a removed setting, or ``None`` for none."""
    if key not in defaults:
        return None
    default = defaults[key]
    shown = "" if default is None else f" {example.toml_value(default)}"
    return f"# {_key(key)} ={shown}{newline}"


def _one_line(line: str) -> bool:
    """True when the setting on ``line`` is complete on that line."""
    try:
        tomllib.loads(line)
    except tomllib.TOMLDecodeError:
        return False
    return True


def add(text: str, block_text: str) -> str:
    """``text`` with ``block_text`` (one ``[[plugin]]`` block, as written by
    :func:`paperpi.example.plugin_block`) added after the last plugin block."""
    data = load(text)
    scan = _scan(text)
    if len(scan.blocks) != len(plugin_blocks(data)):
        raise UnknownForm()
    new_block = plugin_blocks(load(block_text))
    lines = _ended(scan.lines)
    newline = _newline(lines)
    at = scan.blocks[-1].end if scan.blocks else len(lines)
    before, after = "".join(lines[:at]), "".join(lines[at:])
    gap = "" if not before or before.endswith(newline * 2) else newline
    block_text = block_text.replace("\n", newline)
    new = before + gap + block_text + (newline + after if after else "")
    return _checked(new, data | {"plugin": [*plugin_blocks(data), *new_block]})


def _check(text: str, index: int, plugin_id: str) -> tuple[dict[str, Any], _Scan]:
    data = load(text)
    scan = _scan(text)
    raw = plugin_blocks(data)
    if len(scan.blocks) != len(raw):
        raise UnknownForm()
    if not 0 <= index < len(raw) or id_of(raw[index]) != plugin_id:
        raise ChangedMeanwhile()
    return data, scan


def _checked(new: str, expected: dict[str, Any]) -> str:
    """``new``, after checking that PaperPi reads it back as ``expected``."""
    try:
        read_back = tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        read_back = None
    if read_back != expected:
        raise UnknownForm()
    return new


def _ended(lines: list[str]) -> list[str]:
    """``lines``, the last one with a line break too."""
    if lines and not lines[-1].endswith("\n"):
        return [*lines[:-1], lines[-1] + _newline(lines)]
    return lines


def _newline(lines: list[str]) -> str:
    """The file's line break: ``\\r\\n`` (Windows) or ``\\n``."""
    return "\r\n" if lines and lines[0].endswith("\r\n") else "\n"


def _spaced(chunk: list[str], newline: str) -> list[str]:
    """``chunk`` ending with a blank line, so it stays apart from the block after it."""
    return chunk if chunk and not chunk[-1].strip() else [*chunk, newline]


def _setting_line(lines: list[str], within: list[int], key: str) -> int | None:
    pattern = re.compile(rf"\s*{key}\s*=")
    return next((n for n in within if pattern.match(lines[n])), None)
