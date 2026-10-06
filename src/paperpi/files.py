"""Small helpers for files."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, data: bytes, *, mode: int = 0o600, durable: bool = True) -> None:
    """Write ``data`` to ``path`` so a power cut can't leave a half-written file.

    The data goes to a temporary file in the same folder first, which then replaces ``path``
    in one step. ``mode`` is the file's permissions (default: only the owner can read it,
    because config files hold passwords and API keys). ``durable=False`` skips forcing the
    data onto the disk, for files that need not survive a power cut (still replaced in one
    step).
    """
    path = Path(path)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            if durable:
                os.fsync(file.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    if not durable:
        return
    folder = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(folder)  # makes the rename itself survive a power cut
    finally:
        os.close(folder)
