"""Running the web interface inside ``paperpi run``, in its own thread.

The screen loop is more important than the web interface: when the web interface can't
start (for example because another program uses the port), PaperPi logs why and keeps
showing the plugins.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn

from .. import config
from .app import create_app
from .auth import Auth
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
    ):
        self.auth = auth
        self.editor = editor
        self.previewer = Previewer()
        self.settings = settings
        """The settings it was started with; a change of address or port needs a restart."""
        self._socket = sock
        self.port: int = sock.getsockname()[1]
        """The port it listens on (useful with ``port = 0`` in tests)."""
        self._server = uvicorn.Server(
            uvicorn.Config(
                create_app(auth, self.editor, self.previewer),
                log_config=None,  # PaperPi's own logging stays as it is
                log_level="warning",
                access_log=False,
                lifespan="off",
                # Connections still open at a stop (e.g. a slow phone) are closed after this.
                timeout_graceful_shutdown=STOP_SECONDS - 1,
            )
        )
        self._thread = threading.Thread(target=self._serve, name="paperpi-web", daemon=True)

    def _serve(self) -> None:
        try:
            self._server.run(sockets=[self._socket])
        except BaseException:  # noqa: BLE001 - also SystemExit, which uvicorn uses for errors
            log.exception("the web interface stopped because of an error")

    def use(self, loaded: config.Config) -> None:
        """Apply a reloaded config: ``[web]`` log-in changes apply at once, the rest of
        ``[web]`` at the next start."""
        settings = loaded.web
        self.auth.use(settings)
        self.editor.loaded(loaded.text)
        changed = [
            k for k in config.WEB_NEXT_START if getattr(settings, k) != getattr(self.settings, k)
        ]
        if changed:
            log.warning("[web] %s: changes apply at the next start of PaperPi", ", ".join(changed))

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def stop_previews(self) -> None:
        """Start no more previews: PaperPi is stopping (see :meth:`Previewer.stop`)."""
        self.previewer.stop()

    def stop(self) -> None:
        self.stop_previews()
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
) -> WebServer | None:
    """Start the web interface, or log why it can't start and return ``None``.

    ``reload`` makes PaperPi load the config file again (after a change in the web
    interface); ``text`` is the config file text PaperPi uses now.
    """
    try:
        sock = _listen(settings.address, settings.port)
    except OSError as error:
        log.error(
            "the web interface can't start on %s port %s: %s",
            settings.address,
            settings.port,
            error,
        )
        return None
    editor = PluginEditor(config_file, reload)
    if text is not None:
        editor.loaded(text)
    server = WebServer(Auth(config_file, settings), settings, sock, editor)
    server._thread.start()
    return server


def _listen(address: str, port: int) -> socket.socket:
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
