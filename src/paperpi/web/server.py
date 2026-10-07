"""Running the web interface inside ``paperpi run``, in its own thread.

The screen loop is more important than the web interface: when the web interface can't
start (for example because another program uses the port), PaperPi logs why and keeps
showing the plugins.
"""

from __future__ import annotations

import logging
import socket
import threading
from pathlib import Path

import uvicorn

from .. import config
from .app import create_app
from .auth import Auth

log = logging.getLogger(__name__)

#: Seconds to wait for the web interface to stop.
STOP_SECONDS = 5


class WebServer:
    """The web interface of one ``paperpi run``. Start it with :func:`start`."""

    def __init__(self, auth: Auth, settings: config.WebSettings, sock: socket.socket):
        self.auth = auth
        self.settings = settings
        """The settings it was started with; a change of address or port needs a restart."""
        self._socket = sock
        self._server = uvicorn.Server(
            uvicorn.Config(
                create_app(auth),
                log_config=None,  # PaperPi's own logging stays as it is
                log_level="warning",
                access_log=False,
                lifespan="off",
            )
        )
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [sock]}, name="paperpi-web", daemon=True
        )

    @property
    def port(self) -> int:
        """The port it listens on (useful with ``port = 0`` in tests)."""
        return self._socket.getsockname()[1]

    def use(self, settings: config.WebSettings) -> None:
        """Apply reloaded ``[web]`` settings: log-in changes apply at once, the rest at the
        next start."""
        self.auth.use(settings)
        changed = [
            k for k in config.WEB_NEXT_START if getattr(settings, k) != getattr(self.settings, k)
        ]
        if changed:
            log.warning("[web] %s: changes apply at the next start of PaperPi", ", ".join(changed))

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(STOP_SECONDS)
        self._socket.close()


def start(config_file: Path, settings: config.WebSettings) -> WebServer | None:
    """Start the web interface, or log why it can't start and return ``None``."""
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
    server = WebServer(Auth(config_file, settings), settings, sock)
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
