"""Size and age limits of the plugins' storage folders, and the low-disk check
(paperpi.storage)."""

import logging
import os

import pytest

from paperpi import config, limits, storage
from paperpi.plugin import PluginDefinitionError, PluginEntry

DAY = 24 * 60 * 60
NOW = 1_800_000_000.0


def make(folder, name, size, days_old):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    when = NOW - days_old * DAY
    os.utime(path, (when, when))
    return path


def names(folder):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def test_files_older_than_the_limit_are_removed(tmp_path):
    make(tmp_path, "new.json", 10, 29)
    make(tmp_path, "old.json", 10, 31)
    make(tmp_path, "photos/older.jpg", 10, 400)
    cleaned = storage.clean(tmp_path, 500, 30, now=NOW)
    assert names(tmp_path) == ["new.json"]
    assert (cleaned.removed, cleaned.kept_bytes, cleaned.finished) == (2, 10, True)


def test_age_0_keeps_every_file(tmp_path):
    make(tmp_path, "ancient.jpg", 10, 10_000)
    storage.clean(tmp_path, 500, 0, now=NOW)
    assert names(tmp_path) == ["ancient.jpg"]


def test_over_the_size_limit_the_files_changed_longest_ago_go_first(tmp_path):
    for name, days in [("a", 3), ("b", 1), ("c", 2), ("d", 0)]:
        make(tmp_path, f"photos/{name}.jpg", 400_000, days)  # 0.4 MB each
    cleaned = storage.clean(tmp_path, 1, 0, now=NOW)  # 1 MB
    assert names(tmp_path) == ["photos/b.jpg", "photos/d.jpg"]
    assert cleaned.kept_bytes == 800_000


def test_links_are_not_followed_or_removed(tmp_path):
    outside = tmp_path / "outside"
    big = make(outside, "precious.jpg", 2_000_000, 400)
    folder = tmp_path / "plugin"
    folder.mkdir()
    (folder / "to-file").symlink_to(big)
    (folder / "to-folder").symlink_to(outside)
    cleaned = storage.clean(folder, 1, 30, now=NOW)
    assert big.exists()
    assert (folder / "to-file").is_symlink() and (folder / "to-folder").is_symlink()
    assert (cleaned.removed, cleaned.kept_bytes) == (0, 0)


def test_missing_folder_is_fine(tmp_path):
    assert storage.clean(tmp_path / "none", 500, 30) == storage.Cleaned(0, 0, True)


def test_time_limit_stops_the_clean_up(tmp_path, caplog):
    make(tmp_path, "old.json", 10, 400)
    cleaned = storage.clean(tmp_path, 500, 30, now=NOW, time_limit=-1)
    assert not cleaned.finished
    assert (tmp_path / "old.json").exists()
    assert "took longer than" in caplog.text


def test_clean_all_also_cleans_plugins_that_are_switched_off(tmp_path):
    loaded = config.parse(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        '[[plugin]]\nname = "Off"\ntype = "basic_clock"\nenabled = false\n'
    )
    old = make(tmp_path / "plugins" / "off", "old.json", 10, 400)
    storage.clean_all(loaded.plugins, tmp_path)
    assert not old.exists()


def test_low_disk_is_warned_about_when_it_starts_every_10_minutes_and_when_it_ends(caplog):
    caplog.set_level(logging.WARNING)
    now, free = [0.0], [10**12]
    low = storage.LowDisk("/", clock=lambda: now[0], free=lambda path: free[0])
    assert low.check() is False
    free[0] = limits.FREE_DISK_MB * 1_000_000 - 1
    for t in (0, 300, 599, 600):
        now[0] = t
        assert low.check() is True
    free[0] = limits.FREE_DISK_MB * 1_000_000
    assert low.check() is False
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 3
    assert messages[0].startswith("only 1999 MB free on the disk of /")
    assert messages[2] == "the disk of / has enough free space again"


def test_low_disk_check_that_fails_is_not_low():
    def broken(path):
        raise OSError("no such disk")

    assert storage.LowDisk("/", free=broken).check() is False


@pytest.mark.parametrize(
    ("setting", "ok"),
    [("storage_mb = 0", False), ("storage_mb = 20000", True), ("storage_days = -1", False)],
)
def test_storage_settings_are_checked(setting, ok):
    loaded = config.parse(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        f'[[plugin]]\nname = "Clock"\ntype = "basic_clock"\n{setting}\n'
    )
    assert (not loaded.errors) is ok


def test_setting_wins_over_the_plugin_suggestion():
    from dataclasses import replace

    from paperpi import plugins
    from paperpi.config import PluginConfig

    plugin = replace(plugins.load("basic_clock"), storage_mb=20_000, storage_days=0)
    entry = PluginEntry(name="Photos", type="basic_clock")
    found = PluginConfig(entry, plugin.settings(), plugin)
    assert (found.storage_mb, found.storage_days) == (20_000, 0)
    entry = PluginEntry(name="Photos", type="basic_clock", storage_mb=100, storage_days=7)
    found = PluginConfig(entry, plugin.settings(), plugin)
    assert (found.storage_mb, found.storage_days) == (100, 7)


def test_plugin_suggestion_out_of_range_is_a_plugin_bug():
    from dataclasses import replace

    from paperpi import plugins

    with pytest.raises(PluginDefinitionError, match="storage_mb must be between"):
        replace(plugins.load("basic_clock"), storage_mb=0)
