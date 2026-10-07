"""What the Active Plugins and Plugin Library pages show, and the changes they make.

- :class:`PluginEditor` reads the plugin list from the config file and makes one change at a
  time (:mod:`paperpi.web.config_file`). After each change it asks PaperPi to load the file
  again, so the change applies at once.
- A change is made to the file as it is on disk now, so hand edits that were not applied
  yet stay in it and apply together with the change (agreed with txoof, M5 part 2b). The
  page then says so.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .. import config, example, plugins
from ..plugin import Plugin, PluginEntry
from . import config_file

#: Plugin types the Plugin Library doesn't offer: ``default`` is PaperPi's own message when
#: nothing else can be shown, and ``debugging`` is for testing PaperPi.
HIDDEN = ("default", "debugging")


@dataclass(frozen=True)
class Row:
    """One ``[[plugin]]`` block, as the Active Plugins page shows it."""

    index: int
    """Its place in the file, from 0."""
    name: str
    """``""`` when the block has no proper name."""
    type: str
    enabled: bool
    missing: tuple[str, ...] = ()
    """Required settings that are not set yet; the plugin can't be switched on until they are."""
    errors: tuple[str, ...] = ()
    """What is wrong with the block; PaperPi leaves it out until it is fixed."""

    @property
    def status(self) -> str:
        if self.errors:
            return "Not used: has errors"
        if self.missing:
            return "Needs settings: " + ", ".join(self.missing)
        return "On" if self.enabled else "Off"


@dataclass(frozen=True)
class PluginList:
    rows: list[Row]
    problems: list[str] = field(default_factory=list)
    """Problems with the whole file (no plugin can be used until they are fixed)."""


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
        self._lock = threading.Lock()
        self._applied: str | None = None
        """The file text PaperPi uses now (``None``: not known)."""
        self._written: str | None = None
        """The text the web interface saved last (it may not be applied yet)."""

    def loaded(self, text: str) -> None:
        """PaperPi loaded the config file ``text`` (at the start or a reload)."""
        self._applied = text

    def plugin_list(self) -> PluginList:
        """The plugin blocks in the file now. Raises :class:`config_file.EditError` when the
        file can't be read at all."""
        path, text = config_file.read(self.path)
        data = config_file.load(text)
        found = config_file.blocks(text)
        problems: list[config.Problem] = []
        checked: dict[str, config.PluginConfig] = {}
        file_problems = []
        try:
            loaded = config.parse(text, path.name)
        except config.ConfigError as error:
            problems = error.problems
            file_problems = [str(p) for p in error.problems if p.level == "error"]
        else:
            problems = loaded.problems
            checked = {p.entry.name: p for p in loaded.plugins}
        rows = []
        for index, block in enumerate(config_file.plugin_blocks(data)):
            block = block if isinstance(block, dict) else {}
            name = config_file.name_of(block)
            plugin_type = block.get("type")
            enabled = block.get("enabled", True)
            errors = ()
            if index < len(found) and not file_problems:
                place = found[index]
                errors = tuple(
                    _without_place(p)
                    for p in problems
                    if p.level == "error" and p.line and place.start < p.line <= place.end
                )
            good = checked.get(name)
            rows.append(
                Row(
                    index=index,
                    name=name,
                    type=plugin_type if isinstance(plugin_type, str) else "",
                    enabled=enabled if isinstance(enabled, bool) else True,
                    missing=good.missing if good is not None else (),
                    errors=errors if good is None else (),
                )
            )
        if len(found) != len(rows):
            file_problems.append(config_file._UNKNOWN_FORM)
        return PluginList(rows, file_problems)

    def change(self, edit: Callable[[str], str]) -> bool:
        """Change the file with ``edit`` (old text -> new text), save it and apply it.

        Returns True when the file had hand edits that were not applied yet; they apply
        too. Raises :class:`config_file.EditError` when the change can't be made.
        """
        with self._lock:
            path, text = config_file.read(self.path)
            hand_edits = self._applied is not None and text not in (self._applied, self._written)
            new = edit(text)
            config_file.write(path, new)
            self._written = new
        if self._reload is not None:
            self._reload()
        return hand_edits

    def move(self, index: int, name: str, step: int) -> bool:
        return self.change(lambda text: config_file.move(text, index, name, step))

    def set_enabled(self, index: int, name: str, enabled: bool) -> bool:
        if enabled:
            row = self.row(index, name)
            if row.missing:
                missing = ", ".join(row.missing)
                raise config_file.EditError(
                    f"{name} can't be switched on yet: fill in these settings first: {missing}"
                )
        return self.change(lambda text: config_file.set_enabled(text, index, name, enabled))

    def remove(self, index: int, name: str) -> bool:
        return self.change(lambda text: config_file.remove(text, index, name))

    def row(self, index: int, name: str) -> Row:
        """The block at ``index``, if it is still called ``name``."""
        rows = self.plugin_list().rows
        if not 0 <= index < len(rows) or rows[index].name != name:
            raise config_file.ChangedMeanwhile(config_file._MEANWHILE)
        return rows[index]

    def add(self, item: LibraryItem, name: str) -> bool:
        """Add a block for ``item`` called ``name`` at the end of the plugin list. A plugin
        with required settings is added switched off. Raises
        :class:`config_file.EditError` for a name that can't be used."""
        if item.plugin is None:
            raise config_file.EditError(f"{item.type} can't be added: {item.description}")
        name = name.strip()
        problem = name_problem(name)
        if problem:
            raise config_file.EditError(problem)
        values = {"enabled": False} if item.plugin.required else {}
        block = example.plugin_block(item.plugin, name, values)

        def add(text: str) -> str:
            used = _used_names(text)
            if config.folder_name(name) in used:
                raise config_file.EditError(
                    f"the name {name!r} is already used by another plugin (also ignoring "
                    "capitals and punctuation); choose another one"
                )
            return config_file.add(text, block)

        return self.change(add)

    def suggested_name(self, item: LibraryItem) -> str:
        """A name for a new block of ``item`` that is not used yet: "Basic clock",
        "Basic clock 2", ..."""
        try:
            used = _used_names(config_file.read(self.path)[1])
        except config_file.EditError:
            used = set()
        base = item.type.replace("_", " ").capitalize()
        name, number = base, 1
        while config.folder_name(name) in used:
            number += 1
            name = f"{base} {number}"
        return name


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


def name_problem(name: str) -> str | None:
    """Why ``name`` can't be a plugin's name, or ``None`` when it can."""
    try:
        PluginEntry.model_validate({"name": name, "type": "x"})
    except ValidationError as error:
        found = error.errors()[0]
        if found["type"] == "string_too_short":
            return "Give the plugin a name."
        if found["type"] == "string_too_long":
            return f"The name can have at most {found['ctx']['max_length']} characters."
        return f"The name {found['msg'].removeprefix('Value error, ')}."
    return None


def _used_names(text: str) -> set[str]:
    blocks = config_file.plugin_blocks(config_file.load(text))
    return {config.folder_name(n) for n in map(config_file.name_of, blocks) if n}


def _without_place(problem: config.Problem) -> str:
    """The problem's message with its line number, without the file name."""
    return f"line {problem.line}: {problem.message}" if problem.line else problem.message
