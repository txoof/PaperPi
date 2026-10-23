"""What the home page's plugin list and the Plugin Library show, and the changes they make.

- :class:`PluginEditor` reads the plugin list from the config file and makes one change at a
  time (:mod:`paperpi.web.config_file`). After each change it asks PaperPi to load the file
  again, so the change applies at once.
- A change is made to the file as it is on disk now, so hand edits that were not applied
  yet stay in it and apply together with the change (agreed with txoof, M5 part 2b). The
  page then says so.
- A change is refused while the file has a problem that stops PaperPi from using it (such
  as a wrong ``[display]``): PaperPi would keep running on the last good copy, so the change
  would not apply.
- A preview (:meth:`PluginEditor.preview_job`) makes the same change to a copy of the file
  text, so it draws the settings as Save would write them, and saves nothing.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .. import config, example, plugins
from ..plugin import ID_LENGTH, Plugin, PluginEntry, helper_of, label
from . import config_file, forms, helpers, preview

#: Plugin types the Plugin Library doesn't offer: ``default`` is PaperPi's own message when
#: nothing else can be shown, and ``debugging`` is for testing PaperPi.
HIDDEN = ("default", "debugging")


class FormErrors(config_file.EditError):
    """A settings form with values that can't be used; nothing was saved."""

    MESSAGE = "Nothing was saved: some settings can't be used; see the messages next to them."

    def __init__(self, found: forms.Read):
        super().__init__(self.MESSAGE)
        self.found = found


@dataclass(frozen=True)
class Row:
    """One ``[[plugin]]`` block, as the home page shows it."""

    index: int
    """Its place in the file, counted from 0."""
    id: str
    """``""`` when the block has no proper ID."""
    name: str
    """The name it is shown with: its ``name``, or its ID without one."""
    type: str
    enabled: bool
    title: str = ""
    """The plain name of its plugin type, e.g. ``Weather`` (see :func:`title_of`)."""
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
    def title(self) -> str:
        """The plain name shown in the Library, e.g. ``Weather``."""
        return self.plugin.shown_title if self.plugin else self.type

    @property
    def labels(self) -> list[str]:
        """The small labels on its Library card."""
        if self.plugin is None:
            return []
        found = ["Requires setup"] if self.plugin.required or self.plugin.setup else []
        if self.plugin.network == "internet":
            found.append("Requires internet")
        elif self.plugin.network == "home":
            found.append("Uses home network")
        return found

    @property
    def layouts(self) -> list[str]:
        """The titles of its layouts, the default first."""
        if self.plugin is None:
            return []
        return [self.plugin.layout_title(name) for name in self.plugin.layouts]

    @property
    def layout_choices(self) -> list[tuple[str, str]]:
        """The names and titles of its layouts, the default first."""
        if self.plugin is None:
            return []
        return [(name, self.plugin.layout_title(name)) for name in self.plugin.layouts]

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
        self.display: config.DisplaySettings | None = None
        """The ``[display]`` settings the screen uses now (``None``: not known, then
        previews use the file's)."""

    def loaded(self, text: str) -> None:
        """PaperPi loaded the config file ``text`` (at the start or a reload)."""
        self._applied = text

    @property
    def applied(self) -> str | None:
        """The file text PaperPi uses now (``None``: not known)."""
        return self._applied

    def plugin_list(self) -> PluginList:
        """The plugin blocks in the file now. Raises :class:`config_file.EditError` when the
        file can't be read at all."""
        path, text = config_file.read(self.path)
        return _plugin_list(text, path.name)

    def change(self, edit: Callable[[str], str]) -> bool:
        """Change the file with ``edit`` (old text -> new text), save it and apply it.

        Returns True when the file had hand edits that were not applied yet; they apply
        too. When ``edit`` changes nothing, nothing is saved or applied (False). Raises
        :class:`config_file.EditError` when the change can't be made.
        """
        with config_file.LOCK:
            path, text = config_file.read(self.path)
            hand_edits = (
                self._applied is not None
                and text != self._applied
                and not config_file.saved_here(path, text)
            )
            new = edit(text)
            if new == text:  # nothing to save or apply
                return False
            _parse(new, path.name)
            config_file.write(path, new)
        if self._reload is not None:
            self._reload()
        return hand_edits

    def undo(self, seen: str) -> Path:
        """Undo the hand edits: put the text PaperPi uses now back in the config file.

        ``seen`` is the :func:`config_file.fingerprint` of the edited text the page showed.
        The edited file is kept as ``<name>.undone`` next to it; returns that path. Nothing
        needs to load again, as PaperPi already uses this text. Raises
        :class:`config_file.EditError` when there are no hand edits, the file changed after
        the page showed it, or a file can't be saved.
        """
        with config_file.LOCK:
            path, text = config_file.read(self.path)
            applied = self._applied
            if applied is None or text == applied or config_file.saved_here(path, text):
                raise config_file.EditError("There are no hand edits to undo.")
            if config_file.fingerprint(text) != seen:
                raise config_file.EditError(
                    "The config file changed after this page was opened. Check the changes "
                    "and try again."
                )
            kept = config_file.keep(path, text)  # first, so the edits are never lost
            config_file.write(path, applied)
        return kept

    def move(self, index: int, plugin_id: str, step: int) -> bool:
        return self.change(lambda text: config_file.move(text, index, plugin_id, step))

    def move_to(self, index: int, plugin_id: str, place: int) -> bool:
        return self.change(lambda text: config_file.move_to(text, index, plugin_id, place))

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

    def settings(self, index: int, plugin_id: str) -> tuple[Plugin, dict[str, Any]]:
        """The plugin of block ``index`` (if it still has the ID ``plugin_id``) and the
        settings in its block, for the settings form."""
        return _plugin_block(config_file.read(self.path)[1], index, plugin_id)

    def save_settings(self, index: int, plugin_id: str, form: Mapping[str, Sequence[str]]) -> bool:
        """Save a sent settings form (see :func:`forms.read`) into block ``index``. Raises
        :class:`FormErrors` when a value can't be used, so nothing is saved."""

        return self.change(lambda text: _with_settings(text, index, plugin_id, form))

    def preview_job(
        self, index: int, plugin_id: str, form: Mapping[str, Sequence[str]]
    ) -> preview.Job:
        """What a preview of block ``index`` draws with the settings of a sent form: the
        block as Save would write it, and the screen. Nothing is saved. Raises
        :class:`FormErrors` when a value can't be used."""
        found, checked = self._as_saved(index, plugin_id, form, "drawn")
        # The screen as it runs now: a new size, mode or type waits for the next start.
        display = self.display or checked.display
        width, height = display.layout_size
        return preview.Job(found, width, height, display.screen_mode)

    def search_job(
        self,
        index: int,
        plugin_id: str,
        form: Mapping[str, Sequence[str]],
        key: str,
        text: str,
        language: str = "en",
    ) -> helpers.Job:
        """A search with the helper of setting ``key`` of block ``index``, for the typed
        ``text`` and the settings of a sent form as Save would write them. Nothing is
        saved. Raises :class:`FormErrors` when a value can't be used."""
        found, _ = self._as_saved(index, plugin_id, form, "searched for")
        info = found.plugin.settings.model_fields.get(key)
        name = helper_of(info) if info is not None else None
        if name is None:
            raise config_file.EditError(f"The setting {key!r} has no search.")
        helper = found.plugin.helpers[name]
        # A helper without a search box gets no text, also from a form sent by hand.
        text = text.strip() if helper.typed else ""
        return helpers.Job(found, key, name, helper, text, language)

    def filled(
        self,
        index: int,
        plugin_id: str,
        form: Mapping[str, Sequence[str]],
        key: str,
        fill: Mapping[str, Sequence[str]],
    ) -> list[forms.FormField]:
        """The fields of the settings form of block ``index`` after Use, in the choices of
        the helper of setting ``key``, put a choice's
        ``fill`` (setting and texts) into the sent form, each with its error if the value
        can't be used. Only the plugin's own settings that the form can change are filled;
        ``fill`` was checked by :func:`paperpi.helper.clean` when the choice was made, and is
        checked again here like typed values, as a browser can send anything."""
        plugin, block = self.settings(index, plugin_id)
        if plugin.helper(key) is None:
            raise config_file.EditError(f"The setting {key!r} has no search.")
        sent = {k: list(v) for k, v in form.items()} | {k: list(v) for k, v in fill.items()}
        found = forms.read(plugin, block, sent)
        shown = forms.fields(plugin, block, sent, found.errors)
        return [
            f
            for f in shown
            if f.key in fill and f.group == "own" and f.kind not in ("secret", "file")
        ]

    def _as_saved(
        self, index: int, plugin_id: str, form: Mapping[str, Sequence[str]], what: str
    ) -> tuple[config.PluginConfig, config.Config]:
        """Block ``index`` checked with the settings of a sent form, as Save would write
        them, and the whole checked file. Nothing is saved."""
        path, text = config_file.read(self.path)
        new = _with_settings(text, index, plugin_id, form)
        checked = _parse(new, path.name)
        # By the line of its [[plugin]] line: another block may have the same ID.
        place = config_file.blocks(new)[index]
        found = next((p for p in checked.plugins if p.line == place.header + 1), None)
        if found is None:
            problems = "; ".join(
                _without_place(p)
                for p in checked.errors
                if p.line and place.start < p.line <= place.end
            )
            raise config_file.EditError(
                f"This plugin can't be {what}. Its settings in the config file have a problem: "
                f"{problems or 'unknown'}"
            )
        return found, checked

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
        base = item.plugin.title if item.plugin and item.plugin.title else ""
        base = base or item.type.replace("_", " ").capitalize()
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
    titles: dict[str, str] = {}
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
        plugin_type = plugin_type if isinstance(plugin_type, str) else ""
        if plugin_type not in titles:
            titles[plugin_type] = title_of(plugin_type)
        rows.append(
            Row(
                index=index,
                id=plugin_id,
                name=label(name if isinstance(name, str) else "", plugin_id),
                type=plugin_type,
                enabled=enabled if isinstance(enabled, bool) else True,
                title=titles[plugin_type],
                missing=good.missing if good is not None else (),
                errors=() if good is not None or not known else (errors or ("can't be used",)),
                known=known,
            )
        )
    return PluginList(rows, file_problems)


def _plugin_block(text: str, index: int, plugin_id: str) -> tuple[Plugin, dict[str, Any]]:
    raw = config_file.plugin_blocks(config_file.load(text))
    if not 0 <= index < len(raw) or config_file.id_of(raw[index]) != plugin_id:
        raise config_file.ChangedMeanwhile()
    plugin_type = raw[index].get("type")
    try:
        if plugin_type not in plugins.available():
            raise KeyError(plugin_type)
        return plugins.load(plugin_type), raw[index]
    except Exception:  # noqa: BLE001 - a missing or broken plugin can't be set up here
        raise config_file.EditError(
            f"The settings of {plugin_id} can't be changed here: its plugin type "
            f"{plugin_type!r} can't be used. Fix the block in the config file."
        ) from None


def _with_settings(text: str, index: int, plugin_id: str, form: Mapping[str, Sequence[str]]) -> str:
    """``text`` with the settings of a sent form in block ``index``. Raises
    :class:`FormErrors` when a value can't be used."""
    plugin, block = _plugin_block(text, index, plugin_id)
    found = forms.read(plugin, block, form)
    if found.errors:
        raise FormErrors(found)
    changes, shown = found.changes, forms.defaults(plugin)
    return config_file.set_settings(text, index, plugin_id, changes, shown)


def _parse(text: str, source: str) -> config.Config:
    """Check changed config file text, as PaperPi would load it."""
    try:
        return config.parse(text, source)
    except config.ConfigError as error:
        found = "; ".join(str(p) for p in error.problems if p.level == "error")
        raise config_file.EditError(
            f"The config file has a problem that must be fixed first, in the file itself: {found}"
        ) from None


def _row(found: PluginList, index: int, plugin_id: str) -> Row:
    if not 0 <= index < len(found.rows) or found.rows[index].id != plugin_id:
        raise config_file.ChangedMeanwhile()
    return found.rows[index]


def library() -> list[LibraryItem]:
    """The plugin types the Plugin Library offers, sorted by title."""
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
    return sorted(items, key=lambda item: (item.title.casefold(), item.type))


def added_names(rows: Sequence[Row]) -> dict[str, list[str]]:
    """The names of the plugins in the config file, per type, in their order."""
    found: dict[str, list[str]] = {}
    for row in rows:
        found.setdefault(row.type, []).append(row.name or "(no id)")
    return found


def title_of(plugin_type: str) -> str:
    """The plain name of ``plugin_type``, e.g. ``Weather``; the type itself for a plugin
    without a title, or one that is unknown or broken."""
    try:
        return plugins.load(plugin_type).shown_title
    except Exception:  # noqa: BLE001 - the type is shown; its block says what is wrong
        return plugin_type


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
