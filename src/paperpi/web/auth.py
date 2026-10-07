"""The log-in: the cookie that keeps a browser logged in, and the password the web pages use.

After logging in, the browser keeps a cookie for one year. The cookie is signed with the
password hash, so a new password logs out every browser.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
import tomllib
from pathlib import Path

from .. import config
from .password import PasswordError, check_password, hash_password, save_password_hash

#: How long a log-in lasts.
COOKIE_SECONDS = 365 * 24 * 60 * 60


def new_cookie(stored: str, now: float | None = None) -> str:
    """The log-in cookie's value: the time of logging in, signed with the password hash."""
    issued = int(time.time() if now is None else now)
    return f"{issued}.{_sign(stored, issued)}"


def cookie_ok(cookie: str | None, stored: str | None, now: float | None = None) -> bool:
    """True when ``cookie`` was made for this password hash less than a year ago."""
    if not cookie or not stored:
        return False
    issued, _, signature = cookie.partition(".")
    if not (issued.isascii() and issued.isdigit() and len(issued) <= 12):
        return False
    if not (signature.isascii() and len(signature) == 64):
        return False
    now = time.time() if now is None else now
    if not now - COOKIE_SECONDS < int(issued) <= now + 60:
        return False
    return hmac.compare_digest(signature, _sign(stored, int(issued)))


class Auth:
    """The log-in settings the web interface uses now.

    ``use`` takes new ``[web]`` settings after a config reload. Password checks run one at
    a time: each one takes about 16 MB of memory for a moment.
    """

    def __init__(self, config_file: Path, settings: config.WebSettings):
        self.config_file = Path(config_file)
        self._settings = settings
        self._lock = threading.Lock()
        self._checking = threading.Lock()
        self._saved: str | None = None
        """The hash this web interface saved last."""

    @property
    def login(self) -> bool:
        """False when log-in is switched off (``login = false``)."""
        return self._settings.login

    @property
    def password_hash(self) -> str | None:
        return self._settings.password_hash

    def use(self, settings: config.WebSettings) -> None:
        """Use reloaded settings. A reload that read the file just before the web interface
        saved a new password must not forget that password."""
        with self._lock:
            if settings.password_hash is None and self._saved is not None:
                if _saved_hash(self.config_file) == self._saved:
                    settings = settings.model_copy(update={"password_hash": self._saved})
            self._settings = settings

    def check(self, password: str, stored: str | None = None) -> bool:
        """True when ``password`` is right: for the hash ``stored`` (as read by the caller),
        or else the hash used now."""
        stored = stored or self.password_hash
        if stored is None:
            return False
        with self._checking:
            return check_password(password, stored)

    def set_first_password(self, password: str) -> str:
        """Save the first password and return its hash. Raises :class:`PasswordError` when
        a password is set already (e.g. by someone else a moment ago)."""
        with self._lock:
            if self._settings.password_hash is not None:
                raise PasswordError("A password is set already. Log in with it.")
            with self._checking:
                stored = hash_password(password)
            save_password_hash(self.config_file, stored)
            self._saved = stored
            self._settings = self._settings.model_copy(update={"password_hash": stored})
        return stored

    def cookie_ok(self, cookie: str | None) -> bool:
        return cookie_ok(cookie, self.password_hash)


def _saved_hash(path: Path) -> str | None:
    try:
        web = tomllib.loads(config.read_text(path)).get("web", {})
    except (config.ConfigError, tomllib.TOMLDecodeError):
        return None
    return web.get("password_hash") if isinstance(web, dict) else None


def _sign(stored: str, issued: int) -> str:
    key = b"paperpi web log-in\0" + stored.encode("utf-8")
    return hmac.new(key, str(issued).encode("ascii"), hashlib.sha256).hexdigest()
