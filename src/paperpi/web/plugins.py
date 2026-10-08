"""What the Active Plugins and Plugin Library pages show, and the changes they make.

- :class:`PluginEditor` reads the plugin list from the config file and makes one change at a
  time (:mod:`paperpi.web.config_file`). After each change it asks PaperPi to load the file
  again, so the change applies at once.
- A change is made to the file as it is on disk now, so hand edits that were not applied
  yet stay in it and apply together with the change (agreed with txoof, M5 part 2b). The
  page then says so.
- A change is refused while the file has a problem that stops PaperPi from using it (such
  as a wrong ``[display]``): PaperPi would keep running on the last good copy, so the change
  would not apply.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .. import config, example, plugins
from ..plugin import ID_LENGTH, Plugin, PluginEntry, label
from . import config_file

#: Plugin types the Plugin Library doesn't offer: ``default`` is PaperPi's own message when
#: nothing else can be shown, and ``debugging`` is for testing PaperPi.
HIDDEN = ("default", "debugging")


@dataclass(frozen=True)
class Row:
    """One ``[[plugin]]`` block, as the Active Plugins page shows it."""

    index: int
    """Its place in the file, counted from 0."""
    id: str
    """``""`` when the block has no proper ID."""
    name: str
    """The name it is shown with: its ``name``, or its ID without one."""
    type: str
    enabled: bool
    missing: tuple[str, ...] = ()
    """Required settings that are not set yet; the plugin can't be switched on until they are."""
    errors: tuple[str, ...] = ()
    """What is wrong with the block; PaperPi leaves it out until it is fixed."""
    known: bool = True
    """False when the file can't be checked, so whether PaperPi uses the block is not known."""

    @property
    def status(self) -> str:
        if not self.known:
            return "Unknown"
        if self.errors:
            return "Not used: has errors"
        if self.missing:
            return "Needs settings: " + ", ".join(self.missing)
        return "On" if self.enabled else "Off"


@dataclass(frozen=True)
class PluginList:
    rows: list[Row]
    problems: list[str] = field(default_factory=list)
    """Problems with the whole file (no change can be made until they are fixed)."""


@dataclass(frozen=True)
class LibraryItem:
    """One plugin type in the Plugin Library."""

    type: str
    description: str
    plugin: Plugin | None = None
    """``None`` when the plugin itself is broken (``description`` says why)."""

    @property
    def required(self) -> list[tuple[str, str]]:
        """The settings the user has to fill in, with their help text."""
        if self.plugin is None:
            return []
        fields = self.plugin.settings.model_fields
        return [(key, fields[key].description or "") for key in self.plugin.required]


class PluginEditor:
    """Reads and changes the plugin blocks of one config file."""

    def __init__(self, path: Path, reload: Callable[[], None] | None = None):
        self.path = Path(path)
        self._reload = reload
        self._applied: str | None = None
        """The file text PaperPi uses now (``None``: not known)."""

    def loaded(self, text: str) -> None:
        """PaperPi loaded the config file ``text`` (at the start or a reload)."""
        self._applied = text

    def plugin_list(self) -> PluginList:
        """The plugin blocks in the file now. Raises :class:`config_file.EditError` when the
        file can't be read at all."""
        path, text = config_file.read(self.path)
        return _plugin_list(text, path.name)

    def change(self, edit: Callable[[str], str]) -> bool:
        """Change the file with ``edit`` (old text -> new text), save it and apply it.

        Returns True when the file had hand edits that were not applied yet; they apply
        too. Raises :class:`config_file.EditError` when the change can't be made.
        """
        with config_file.LOCK:
            path, text = config_file.read(self.path)
            hand_edits = (
                self._applied is not None
                and text != self._applied
                and not config_file.saved_here(path, text)
            )
            new = edit(text)
            try:
                config.parse(new, path.name)
            except config.ConfigError as error:
                found = "; ".join(str(p) for p in error.problems if p.level == "error")
                raise config_file.EditError(
                    "The config file has a problem that must be fixed first, in the file "
                    f"itself: {found}"
                ) from None
            config_file.write(path, new)
        if self._reload is not None:
            self._reload()
        return hand_edits

    def move(self, index: int, plugin_id: str, step: int) -> bool:
        return self.change(lambda text: config_file.move(text, index, plugin_id, step))

    def set_enabled(self, index: int, plugin_id: str, enabled: bool) -> bool:
        def switch(text: str) -> str:
            row = _row(_plugin_list(text), index, plugin_id)
            if enabled and row.missing:
                raise config_file.EditError(
                    f"{row.name} can't be switched on yet. Fill in these settings first: "
                    f"{', '.join(row.missing)}."
                )
            return config_file.set_enabled(text, index, plugin_id, enabled)

        return self.change(switch)

    def remove(self, index: int, plugin_id: str) -> bool:
        return self.change(lambda text: config_file.remove(text, index, plugin_id))

    def row(self, index: int, plugin_id: str) -> Row:
        """The block at ``index``, if it still has the ID ``plugin_id``."""
        return _row(self.plugin_list(), index, plugin_id)

    def add(self, item: LibraryItem, name: str) -> tuple[bool, str]:
        """Add a block for ``item``, shown as ``name``, at the end of the plugin list. It
        gets a new ID: the type and 8 random letters and digits, e.g. ``met_no-3f9a1c2e``.
        A plugin with required settings is added switched off.

        Returns whether hand edits applied too (see :meth:`change`) and the new ID. Raises
        :class:`config_file.EditError` for a name that can't be used."""
        if item.plugin is None:
            raise config_file.EditError(f"{item.type} can't be added. {item.description}")
        plugin = item.plugin
        name = name.strip()
        problem = name_problem(name)
        if problem:
            raise config_file.EditError(problem)
        values = ({"name": name} if name else {}) | ({"enabled": False} if plugin.required else {})
        made = ""

        def add(text: str) -> str:
            nonlocal made
            used = _used_ids(text)
            made = new_id(item.type)
            while config.folder_name(made) in used:
                made = new_id(item.type)
            return config_file.add(text, example.plugin_block(plugin, made, values))

        return self.change(add), made

    def suggested_name(self, item: LibraryItem) -> str:
        """A name for a new block of ``item`` that no other plugin is shown with yet:
        "Basic clock", "Basic clock 2", ..."""
        try:
            used = _used_names(config_file.read(self.path)[1])
        except config_file.EditError:
            used = set()
        base = item.type.replace("_", " ").capitalize()
        name, number = base, 1
        while name.casefold() in used:
            number += 1
            name = f"{base} {number}"
        return name


def _plugin_list(text: str, source: str = "config") -> PluginList:
    data = config_file.load(text)
    found = config_file.blocks(text)
    raw = config_file.plugin_blocks(data)
    file_problems: list[str] = []
    problems: list[config.Problem] = []
    checked: dict[int, config.PluginConfig] = {}
    try:
        loaded = config.parse(text, source)
    except config.ConfigError as error:
        file_problems = [str(p) for p in error.problems if p.level == "error"]
    else:
        problems = loaded.problems
        # By the line of its [[plugin]] line: two blocks may have the same ID (then
        # PaperPi uses only the first).
        checked = {p.line: p for p in loaded.plugins if p.line is not None}
    known = len(found) == len(raw) and not file_problems
    if len(found) != len(raw):
        file_problems.append(str(config_file.UnknownForm()))
    rows = []
    for index, block in enumerate(raw):
        block = block if isinstance(block, dict) else {}
        plugin_type, enabled = block.get("type"), block.get("enabled", True)
        good = errors = None
        if known:
            place = found[index]
            good = checked.get(place.header + 1)
            errors = tuple(
                _without_place(p)
                for p in problems
                if p.level == "error" and p.line and place.start < p.line <= place.end
            )
        plugin_id, name = config_file.id_of(block), block.get("name")
        rows.append(
            Row(
                index=index,
                id=plugin_id,
                name=label(name if isinstance(name, str) else "", plugin_id),
                type=plugin_type if isinstance(plugin_type, str) else "",
                enabled=enabled if isinstance(enabled, bool) else True,
                missing=good.missing if good is not None else (),
                errors=() if good is not None or not known else (errors or ("can't be used",)),
                known=known,
            )
        )
    return PluginList(rows, file_problems)


def _row(found: PluginList, index: int, plugin_id: str) -> Row:
    if not 0 <= index < len(found.rows) or found.rows[index].id != plugin_id:
        raise config_file.ChangedMeanwhile()
    return found.rows[index]


def library() -> list[LibraryItem]:
    """The plugin types the Plugin Library offers, sorted by type."""
    items = []
    for plugin_type in plugins.available():
        if plugin_type in HIDDEN:
            continue
        try:
            plugin = plugins.load(plugin_type)
        except Exception as error:  # noqa: BLE001 - a broken plugin is shown as broken
            items.append(LibraryItem(plugin_type, f"This plugin is broken: {error}"))
        else:
            items.append(LibraryItem(plugin_type, plugin.description, plugin))
    return items


def library_item(plugin_type: str) -> LibraryItem | None:
    return next((item for item in library() if item.type == plugin_type), None)


def new_id(plugin_type: str) -> str:
    """A new plugin ID: ``plugin_type``, ``-`` and 8 random letters and digits."""
    return f"{plugin_type[: ID_LENGTH - 9]}-{secrets.token_hex(4)}"


def name_problem(name: str) -> str | None:
    """Why ``name`` can't be the name a plugin is shown with, or ``None`` when it can."""
    try:
        PluginEntry.model_validate({"id": "x", "type": "x", "name": name})
    except ValidationError as error:
        found = error.errors()[0]
        if found["type"] == "string_too_long":
            return f"The name can have at most {found['ctx']['max_length']} characters."
        return f"The name {found['msg'].removeprefix('Value error, ')}."
    return None


def _used_ids(text: str) -> set[str]:
    blocks = config_file.plugin_blocks(config_file.load(text))
    return {config.folder_name(i) for i in map(config_file.id_of, blocks) if i}


def _used_names(text: str) -> set[str]:
    """The names the plugins are shown with, without capitals."""
    return {row.name.casefold() for row in _plugin_list(text).rows}


def _without_place(problem: config.Problem) -> str:
    """The problem's message with its line number, without the file name."""
    return f"line {problem.line}: {problem.message}" if problem.line else problem.message
