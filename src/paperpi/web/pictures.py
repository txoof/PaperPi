"""Example pictures for the Plugin Library: each plugin drawn with its sample data.

See ``docs/decisions/web-interface.md``. The pictures are drawn ahead, in the background,
at the screen's size (in 256 shades of gray, or in color for a color screen), and saved in
``library-pictures/`` in the state folder, so the Library page opens at once (agreed with
txoof, M5 part 3b-2).

A picture's file name holds a fingerprint: a short code made from the plugin's files (the
name, size and time of last change of each file in its folder, so a change to any of them
counts), the screen's width, height and type, and the PaperPi and epdlib versions. When
one of these changes, the old picture no longer matches and a new one is drawn; pictures
that match no plugin any more are deleted. The files' contents are not read: moon_phase
alone has 19 MB of images, too much to read at every opening of the page on a Pi 3. Only
files in the plugin's own folder count: a change to PaperPi's shared code (or to epdlib
without a new version number, as while developing) counts only through the version.

Drawing starts :data:`~paperpi.limits.LIBRARY_PICTURES_WAIT` seconds after PaperPi starts
(so the first screen update goes first), or at once when the Library page is opened or
the config file is loaded again. One picture is drawn at a time, each in its own plugin
process, as a preview is (:func:`paperpi.runner.run_update`), with the plugin's default
settings and first layout, within :data:`~paperpi.limits.PREVIEW_SAMPLE` seconds. A plugin
that takes longer is tried again, at most :data:`TRIES` times in all (the Pi may just have
been busy). Any other picture that can't be drawn says why and is not tried again until its
file name changes or PaperPi starts again, so an open Library page can't keep the Pi busy.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import tempfile
import threading
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from epdlib import ScreenMode

from .. import __version__, config, limits, plugins
from ..plugin import Context, State
from ..runner import PluginFailed, PluginTimeout, run_update
from .plugins import HIDDEN
from .preview import Update

log = logging.getLogger(__name__)

#: The folder in the state folder that holds the pictures.
FOLDER = "library-pictures"

#: How often a picture is tried when the plugin takes too long.
TRIES = 3


@dataclass(frozen=True)
class Screen:
    """What the pictures are drawn for."""

    width: int
    height: int
    mode: ScreenMode

    @classmethod
    def of(cls, display: config.DisplaySettings) -> Screen:
        """What the pictures are drawn for with ``display``: its size (turned when it is
        rotated), in the best gray (256 shades) so the examples are easy to see on a phone,
        also for a black-and-white screen (agreed with txoof, 2026-10-10). A color screen
        keeps its colors."""
        mode = display.screen_mode
        return cls(*display.layout_size, mode if mode.has_color else ScreenMode.gray(256))


@dataclass(frozen=True)
class Shown:
    """What the Library page shows for one plugin."""

    file: str = ""
    """The picture's file name, once it is drawn."""
    problem: str = ""
    """Why there is no picture (it could not be drawn)."""
    screen: Screen | None = None

    @property
    def waiting(self) -> bool:
        """Not drawn yet: the page asks again in a moment."""
        return not self.file and not self.problem


class Pictures:
    """Draws and keeps the example pictures in ``folder``; ``None``: no pictures at all
    (e.g. tests that don't need them)."""

    def __init__(
        self,
        folder: Path | None,
        update: Update = run_update,
        *,
        package: str = plugins.__name__,
        wait: float = limits.LIBRARY_PICTURES_WAIT,
    ):
        self.folder = folder
        self._update = update
        self._package = package
        self._wait = wait
        self._screen: Screen | None = None
        self._failed: dict[str, str] = {}  # file name -> why it could not be drawn
        self._timeouts: dict[str, int] = {}  # file name -> how often it took too long
        self._problem = ""  # why no picture can be saved at all (the folder)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def use(self, screen: Screen) -> None:
        """Draw the pictures for ``screen`` (at the start, and after each config reload):
        those that are missing are drawn in the background."""
        if self.folder is None:
            return
        with self._lock:
            self._screen = screen
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._work, name="paperpi-library-pictures", daemon=True
                )
                self._thread.start()
                return  # the first round starts after the wait
        self._wake.set()

    def stop(self) -> None:
        """PaperPi stops: draw no more pictures."""
        self._stopped.set()
        self._wake.set()

    def shown(self, plugin_type: str) -> Shown | None:
        """What to show for ``plugin_type``; ``None`` when there are no pictures."""
        with self._lock:
            screen = self._screen
        if self.folder is None or screen is None:
            return None
        if self._problem:
            return Shown(problem=self._problem, screen=screen)
        try:
            name = self.file_name(plugin_type, screen)
        except OSError as error:
            return Shown(problem=f"Its files can't be read: {error.strerror}.", screen=screen)
        if (self.folder / name).is_file():
            return Shown(file=name, screen=screen)
        if name in self._failed:
            return Shown(problem=self._failed[name], screen=screen)
        self._wake.set()  # a plugin changed, or the page was opened during the wait
        return Shown(screen=screen)

    def path(self, name: str) -> Path | None:
        """The saved picture called ``name``, or ``None`` (also for any other file name)."""
        if self.folder is None or not _good_name(name):
            return None
        found = self.folder / name
        # Not a link to another file: only pictures PaperPi saved itself are given out.
        return found if found.is_file() and not found.is_symlink() else None

    def file_name(self, plugin_type: str, screen: Screen) -> str:
        """The file name of ``plugin_type``'s picture for ``screen``: ``<type>-<16 hex
        digits>.png``, the digits being the fingerprint (see the top)."""
        spec = importlib.util.find_spec(f"{self._package}.{plugin_type}")
        folder = Path(spec.submodule_search_locations[0])
        code = hashlib.sha256()
        for part in (__version__, version("epdlib"), plugin_type, screen.width, screen.height):
            code.update(f"{part}\n".encode())
        code.update(f"{screen.mode!r}\n".encode())
        for file in sorted(folder.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                info = file.stat()
                code.update(
                    f"{file.relative_to(folder)} {info.st_size} {info.st_mtime_ns}\n".encode()
                )
        return f"{plugin_type}-{code.hexdigest()[:16]}.png"

    def _work(self) -> None:
        self._wake.wait(self._wait)
        while not self._stopped.is_set():
            self._wake.clear()
            try:
                self._draw_all()
            except OSError as error:  # the folder can't be made or read
                log.error("library pictures can't be saved in %s: %s", self.folder, error)
                self._problem = f"Pictures can't be saved: {error.strerror or error}."
            self._wake.wait()

    def _draw_all(self) -> None:
        with self._lock:
            screen = self._screen
        self.folder.mkdir(parents=True, exist_ok=True)
        self._problem = ""  # e.g. fixed before a config reload
        keep = set()
        for plugin_type in plugins.available(self._package):
            if plugin_type in HIDDEN:
                continue
            if self._stopped.is_set():
                return
            try:
                name = self.file_name(plugin_type, screen)
            except OSError:  # keep what it has; the page says its files can't be read
                keep.update(p.name for p in self.folder.glob(f"{plugin_type}-*.png"))
                continue
            keep.add(name)
            if not (self.folder / name).is_file() and name not in self._failed:
                try:
                    self._draw(plugin_type, name, screen)
                except Exception as error:  # noqa: BLE001 - say why; go on with the others
                    log.exception("library picture of %s", plugin_type)
                    self._failed[name] = f"It could not be drawn: {error}"
        for old in [*self.folder.glob("*.png"), *self.folder.glob(".*.part")]:
            if old.name not in keep:
                old.unlink(missing_ok=True)

    def _draw(self, plugin_type: str, name: str, screen: Screen) -> None:
        try:
            plugin = plugins.load(plugin_type, self._package)
            settings = plugin.settings.model_validate({})
        except Exception as error:  # noqa: BLE001 - the Library page says it is broken
            self._failed[name] = f"The plugin is broken: {error}"
            return
        with tempfile.TemporaryDirectory(prefix="paperpi-picture-") as storage:
            context = Context(
                settings,
                screen.width,
                screen.height,
                screen.mode,
                Path(storage),
                plugin.default_layout,
            )
            try:
                result = self._update(
                    plugin_type, context, sample=True, time_limit=limits.PREVIEW_SAMPLE
                )
            except PluginFailed as error:
                log.info("library picture of %s: %s", plugin_type, error)
                tries = self._timeouts[name] = self._timeouts.get(name, 0) + 1
                if isinstance(error, PluginTimeout) and tries < TRIES:
                    return  # tried again at the next round (the page asks again)
                self._failed[name] = f"Its sample data could not be drawn: {error.reason}"
                return
        if result.state is State.NOTHING or result.image is None:
            self._failed[name] = "Its sample data gives no picture."
            return
        part = self.folder / f".{name}.part"
        try:
            result.image.save(part, format="PNG")
            part.replace(self.folder / name)  # the page never sees half a file
        except OSError as error:
            part.unlink(missing_ok=True)
            self._failed[name] = f"It could not be saved: {error.strerror or error}."
            log.error("library picture of %s can't be saved: %s", plugin_type, error)
            return
        log.debug("library picture of %s drawn in %.1f s", plugin_type, result.seconds)


def _good_name(name: str) -> bool:
    base, _, rest = name.rpartition("-")
    digits = rest.removesuffix(".png")
    return (
        bool(base)
        and all(c.isascii() and (c.isalnum() or c == "_") for c in base)
        and rest.endswith(".png")
        and len(digits) == 16
        and all(c in "0123456789abcdef" for c in digits)
    )
