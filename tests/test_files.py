"""Writing files safely (paperpi.files)."""

import os

import pytest

from paperpi.files import write_atomic


def test_write_atomic(tmp_path):
    path = tmp_path / "f.toml"
    write_atomic(path, b"one")
    write_atomic(path, b"two")
    assert path.read_bytes() == b"two"
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_failed_write_leaves_the_old_file_and_no_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "f.toml"
    write_atomic(path, b"old")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        write_atomic(path, b"new")
    assert path.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [path]
