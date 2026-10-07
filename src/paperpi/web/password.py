"""The web password: scrambling and checking it, and saving it in the config file.

- The password is stored in the config file as a scrypt hash: a scrambled form that can be
  checked but not turned back into the password. scrypt is built into Python.
- :func:`save_password_hash` writes the hash into ``[web]`` of the config file (``None``
  removes it, for ``paperpi reset-password``), keeping the rest of the file as it is.

See ``docs/decisions/web-interface.md``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import stat
import tomllib
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

from .. import config
from ..files import write_atomic

#: Shortest and longest password the web interface accepts.
PASSWORD_LENGTH = (8, 1000)

# scrypt's cost numbers: with these, one check takes about 16 MB of memory and 0.1 s on a Pi.
_N, _R, _P = 2**14, 8, 1
# Limits for the numbers in a hash, so a hand-edited hash can't make one log-in use all
# memory (scrypt needs 128 * N * r bytes) or take minutes.
_MOST_MEMORY = 64 * 1024 * 1024
_MOST_WORK = 2**20  # N * r * p; the default is 2**17


class PasswordError(ValueError):
    """The password or the config file can't be used; the message says why."""


def hash_password(password: str) -> str:
    """The text stored in ``password_hash``: ``scrypt:N:r:p:salt:hash``."""
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _N, _R, _P)
    return f"scrypt:{_N}:{_R}:{_P}:{_b64(salt)}:{_b64(digest)}"


def check_password(password: str, stored: str) -> bool:
    """True when ``password`` is the one scrambled in ``stored``. A broken ``stored`` is
    never a match."""
    try:
        kind, n, r, p, salt, digest = stored.split(":")
        n, r, p = int(n), int(r), int(p)
        if kind != "scrypt" or not _cost_ok(n, r, p):
            return False
        salt_bytes, digest_bytes = _unb64(salt), _unb64(digest)
        if not salt_bytes or not 16 <= len(digest_bytes) <= 64:
            return False
        found = _scrypt(password, salt_bytes, n, r, p, len(digest_bytes))
    except (ValueError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(found, digest_bytes)


def looks_like_hash(stored: str) -> bool:
    """True when ``stored`` has the form :func:`hash_password` writes, with usable costs."""
    parts = stored.split(":")
    if len(parts) != 6 or parts[0] != "scrypt" or not all(x.isdigit() for x in parts[1:4]):
        return False
    try:
        salt, digest = _unb64(parts[4]), _unb64(parts[5])
    except ValueError:
        return False
    return _cost_ok(*(int(x) for x in parts[1:4])) and bool(salt) and 16 <= len(digest) <= 64


def password_problem(password: str, again: str) -> str | None:
    """Why a new password can't be used, or ``None`` when it can."""
    shortest, longest = PASSWORD_LENGTH
    if password != again:
        return "The two passwords are not the same."
    if len(password) < shortest:
        return f"The password needs at least {shortest} characters."
    if len(password) > longest:
        return f"The password can have at most {longest} characters."
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return "The password has a character that can't be saved."
    return None


def save_password_hash(path: Path, stored: str | None) -> bool:
    """Set ``password_hash`` in ``[web]`` of the config file, or remove it (``None``).

    Comments and everything else in the file stay as they are, and the file keeps its
    permissions. Returns False when there was nothing to change. Raises
    :class:`PasswordError` when the file can't be read, changed or written.
    """
    # A config file that is a link to another file: change the file it points to.
    path = Path(os.path.realpath(path))
    try:
        text = config.read_text(path)
    except config.ConfigError as error:
        raise PasswordError(str(error)) from None
    try:
        document = tomlkit.parse(text)
    except TOMLKitError as error:
        raise PasswordError(f"{path} is not valid TOML: {error}") from None
    web = document.get("web")
    if web is not None and not isinstance(web, dict):
        raise PasswordError(f"{path}: web must be a [web] part")
    if stored is None:
        if web is None or "password_hash" not in web:
            return False
        del web["password_hash"]
    else:
        if web is None:
            web = tomlkit.table()
            document["web"] = web
        web["password_hash"] = stored
    new_text = tomlkit.dumps(document)
    try:
        old, new = tomllib.loads(text), tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as error:
        raise PasswordError(f"{path} can't be written back: {error}") from None
    if new.get("web", {}).get("password_hash") != stored or _without_hash(old) != _without_hash(
        new
    ):
        raise PasswordError(f"{path} can't be written back with the new password")
    try:
        # The new file keeps the old one's permissions and, when run with sudo, its owner,
        # so the PaperPi service can still read it.
        info = os.stat(path)
        owner = (info.st_uid, info.st_gid) if os.geteuid() == 0 else None
        write_atomic(path, new_text.encode("utf-8"), mode=stat.S_IMODE(info.st_mode), owner=owner)
    except OSError as error:
        raise PasswordError(f"can't save {path}: {error}") from None
    return True


def _cost_ok(n: int, r: int, p: int) -> bool:
    return (
        n >= 2
        and n & (n - 1) == 0  # a power of 2
        and 1 <= r
        and 1 <= p
        and n < 2 ** (16 * r)  # scrypt's own rule
        and 128 * n * r <= _MOST_MEMORY
        and n * r * p <= _MOST_WORK
    )


def _without_hash(data: dict) -> dict:
    web = data.get("web")
    if not isinstance(web, dict):
        return data
    web = {k: v for k, v in web.items() if k != "password_hash"}
    rest = {k: v for k, v in data.items() if k != "web"}
    return rest | {"web": web} if web else rest


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int = 32) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MOST_MEMORY * 2, dklen=length
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as error:
        raise ValueError(str(error)) from None
