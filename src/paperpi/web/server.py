"""Running the web interface inside ``paperpi run``, in its own thread.

The screen loop is more important than the web interface: when the web interface can't
start (for example because another program uses the port), PaperPi logs why and keeps
showing the plugins. New web settings are on trial after a restart (see :mod:`.keep`):
when nobody keeps them, the web interface moves back to its old address without stopping
PaperPi.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn

from .. import config
from ..logbook import Logbook
from . import keep, system
from .app import create_app
from .auth import Auth
from .config_file import EditError
from .helpers import Searcher
from .home import Controls
from .pictures import FOLDER, Pictures, Screen
from .plugins import PluginEditor
from .preview import Previewer

log = logging.getLogger(__name__)

#: Seconds to wait for the web interface to stop.
STOP_SECONDS = 5


class WebServer:
    """The web interface of one ``paperpi run``. Start it with :func:`start`."""

    def __init__(
        self,
        auth: Auth,
        settings: config.WebSettings,
        sock: socket.socket,
        editor: PluginEditor,
        pictures: Pictures | None = None,
        controls: Controls | None = None,
        logbook: Logbook | None = None,
        state_dir: Path | None = None,
        keeper: keep.Keeper | None = None,
    ):
        self.auth = auth
        self.editor = editor
        self.previewer = Previewer()
        self.searcher = Searcher()
        self.pictures = pictures or Pictures(None)
        self.display: config.DisplaySettings | None = None
        """The ``[display]`` settings the screen uses now (see :meth:`use_display`)."""
        self.settings = settings
        """The settings of the address it listens on; a change of address or port needs a
        restart (or going back to the old ones, see :mod:`.keep`)."""
        self.keeper = keeper or keep.Keeper(settings, state_dir)
        self.keeper.go_back = self._go_back
        self._state_dir = state_dir
        self._socket = sock
        self.port: int = sock.getsockname()[1]
        """The port it listens on (useful with ``port = 0`` in tests)."""
        self._app = create_app(
            auth,
            self.editor,
            self.previewer,
            self.pictures,
            self.searcher,
            controls,
            logbook,
            state_dir,
            settings,
            self.keeper,
        )
        self._moving = threading.Lock()
        self._stopped = False
        self._server = self._new_server()
        self._thread = self._new_thread()

    def _new_server(self) -> uvicorn.Server:
        return uvicorn.Server(
            uvicorn.Config(
                self._app,
                log_config=None,  # PaperPi's own logging stays as it is
                log_level="warning",
                access_log=False,
                lifespan="off",
                # Connections still open at a stop (e.g. a slow phone) are closed after this.
                timeout_graceful_shutdown=STOP_SECONDS - 1,
            )
        )

    def _new_thread(self) -> threading.Thread:
        server, sock = self._server, self._socket
        return threading.Thread(
            target=self._serve, args=(server, sock), name="paperpi-web", daemon=True
        )

    def _serve(self, server: uvicorn.Server, sock: socket.socket) -> None:
        try:
            server.run(sockets=[sock])
        except BaseException:  # noqa: BLE001 - also SystemExit, which uvicorn uses for errors
            log.exception("the web interface stopped because of an error")

    def _go_back(self, why: str) -> None:
        """Nobody kept the new web settings (``why``: "time" or "asked"): write the old
        address and port back into the config file and move the web interface there."""
        old = self.keeper.end_trial()
        if old is None:
            return
        # Before the change: the reload it starts compares the file with these.
        self.settings = self.keeper.used = old
        try:
            self.editor.change(lambda text: system.set_web_address(text, old))
        except EditError as error:
            # The kept file stays, so the next start puts the new settings on trial again.
            log.error("can't write the old web address back into the config file: %s", error)
        else:
            keep.forget(self._state_dir)
        self.keeper.note = keep.reason(why, old)
        log.warning("%s", self.keeper.note)
        self._move(old)

    def _move(self, settings: config.WebSettings) -> None:
        """Listen at the address and port of ``settings`` instead."""
        with self._moving:
            if self._stopped:
                return
            # Stopped first: the old address may use the same port.
            self._server.should_exit = True
            self._thread.join(STOP_SECONDS)
            self._socket.close()
            try:
                sock = listen(settings.address, settings.port)
            except OSError as error:
                log.error(
                    "the web interface can't start on %s port %s: %s",
                    settings.address,
                    settings.port,
                    error,
                )
                return
            self._socket = sock
            self.port = sock.getsockname()[1]
            self.settings = self.keeper.used = settings
            self._server = self._new_server()
            self._thread = self._new_thread()
            self._thread.start()

    def use(self, loaded: config.Config) -> None:
        """Apply a reloaded config: ``[web]`` log-in changes apply at once, the rest of
        ``[web]`` at the next start."""
        settings = loaded.web
        self.auth.use(settings)
        self.editor.loaded(loaded.text)
        self.use_display(loaded.display)
        changed = [
            k for k in config.WEB_NEXT_START if getattr(settings, k) != getattr(self.settings, k)
        ]
        if changed:
            log.warning("[web] %s: changes apply at the next start of PaperPi", ", ".join(changed))

    def use_display(self, display: config.DisplaySettings) -> None:
        """Draw previews and the Library pictures for ``display``. As in the scheduler, a
        change of the screen's type, model, size or mode applies only at the next start, so
        they keep the values the screen started with."""
        if self.display is not None:
            started = {key: getattr(self.display, key) for key in config.NEXT_START}
            display = display.model_copy(update=started)
        self.display = self.editor.display = display
        self.pictures.use(Screen.of(display))

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def stop_previews(self) -> None:
        """Start no more previews, library pictures or helper searches: PaperPi is stopping
        (see :meth:`Previewer.stop`)."""
        self.previewer.stop()
        self.searcher.stop()
        self.pictures.stop()

    def stop(self) -> None:
        self.stop_previews()
        self.keeper.stop()
        with self._moving:
            self._stopped = True
            self._server.should_exit = True
            self._thread.join(STOP_SECONDS)
            if self._thread.is_alive():
                log.warning("the web interface did not stop within %s s", STOP_SECONDS)
            self._socket.close()


def start(
    config_file: Path,
    settings: config.WebSettings,
    *,
    reload: Callable[[], None] | None = None,
    text: str | None = None,
    state_dir: Path | None = None,
    display: config.DisplaySettings | None = None,
    controls: Controls | None = None,
    logbook: Logbook | None = None,
) -> WebServer | None:
    """Start the web interface, or log why it can't start and return ``None``.

    ``reload`` makes PaperPi load the config file again (after a change in the web
    interface); ``text`` is the config file text PaperPi uses now. The Plugin Library's
    example pictures are kept in ``state_dir`` (without it there are none) and drawn for
    ``display``, the screen's settings at the start. ``controls`` (the scheduler) tells
    the home page what is on screen, and does what its buttons ask for. ``logbook`` holds
    the log lines for the Full log page.

    When the web settings kept in ``state_dir`` (:mod:`.keep`) name another address,
    ``settings`` are new ones: they are put on trial, or, when their port can't be opened,
    the old ones are written back and used at once.
    """
    editor = PluginEditor(config_file, reload)
    if text is not None:
        editor.loaded(text)
    keeper = keep.Keeper(settings, state_dir)
    old = keep.previous(state_dir, settings)
    if old is not None and keep.same_address(old, settings):
        keep.forget(state_dir)  # back on it, by hand
        old = None
    try:
        sock = listen(settings.address, settings.port)
    except OSError as error:
        _cant_start(settings, error)
        if old is None:
            return None
        try:
            editor.change(lambda text: system.set_web_address(text, old))
        except EditError as problem:
            log.error("can't write the old web address back into the config file: %s", problem)
        else:
            keep.forget(state_dir)
        keeper.note = keep.reason("port", old, error.strerror or str(error))
        log.warning("%s", keeper.note)
        settings = keeper.used = old
        old = None
        try:
            sock = listen(settings.address, settings.port)
        except OSError as again:
            _cant_start(settings, again)
            return None
    pictures = Pictures(state_dir / FOLDER if state_dir is not None else None)
    auth = Auth(config_file, settings)
    server = WebServer(auth, settings, sock, editor, pictures, controls, logbook, state_dir, keeper)
    if old is not None:
        keeper.start_trial(old)
        log.info(
            "new web settings on trial: %s (old: %s)", keep.describe(settings), keep.describe(old)
        )
    server._thread.start()
    if display is not None:
        server.use_display(display)
    return server


def _cant_start(settings: config.WebSettings, error: OSError) -> None:
    log.error(
        "the web interface can't start on %s port %s: %s", settings.address, settings.port, error
    )


def listen(address: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((address, port))
        sock.listen(64)
    except OSError:
        sock.close()
        raise
    return sock
