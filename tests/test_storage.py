"""Size and age limits of the plugins' storage folders, and the low-disk check
(paperpi.storage)."""

import logging
import os

import pytest

from paperpi import config, limits, storage
from paperpi.plugin import PluginDefinitionError, PluginEntry

DAY = 24 * 60 * 60
NOW = 1_800_000_000.0
BLOCK = 4096  # the space a small file uses on the disk


@pytest.fixture(autouse=True)
def modification_time_only(monkeypatch, request):
    """Tests set file ages with os.utime, which can't set the status-change time back."""
    if "real_times" not in request.node.name:
        monkeypatch.setattr(storage, "_changed", lambda info: info.st_mtime)


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
    assert (cleaned.removed, cleaned.kept_bytes, cleaned.finished) == (2, BLOCK, True)


def test_age_0_keeps_every_file(tmp_path):
    make(tmp_path, "ancient.jpg", 10, 10_000)
    storage.clean(tmp_path, 500, 0, now=NOW)
    assert names(tmp_path) == ["ancient.jpg"]


def test_over_the_size_limit_the_files_changed_longest_ago_go_first(tmp_path):
    for name, days in [("a", 3), ("b", 1), ("c", 2), ("d", 0)]:
        make(tmp_path, f"photos/{name}.jpg", 100 * BLOCK, days)  # 0.4 MB each
    cleaned = storage.clean(tmp_path, 1, 0, now=NOW)  # 1 MB
    assert names(tmp_path) == ["photos/b.jpg", "photos/d.jpg"]
    assert cleaned.kept_bytes == 200 * BLOCK


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
    assert "could not be cleaned fully within -1 s" in caplog.text


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
    free[0] = (limits.FREE_DISK_MB + 50) * 1_000_000
    assert low.check() is True  # not fine again until 100 MB more is free
    free[0] = (limits.FREE_DISK_MB + limits.FREE_DISK_GAP_MB) * 1_000_000
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


def test_real_times_copied_file_with_an_old_modification_time_is_not_removed(tmp_path):
    import shutil

    old = make(tmp_path / "elsewhere", "old.jpg", 10, 90)
    folder = tmp_path / "plugin"
    folder.mkdir()
    shutil.copy2(old, folder / "copied.jpg")  # keeps the 90-day-old modification time
    storage.clean(folder, 500, 30)
    assert (folder / "copied.jpg").exists()


def test_folder_that_is_a_link_is_not_cleaned(tmp_path, caplog):
    outside = tmp_path / "usb"
    photo = make(outside, "photo.jpg", 10, 400)
    (tmp_path / "photos").symlink_to(outside)
    assert storage.clean(tmp_path / "photos", 500, 30, now=NOW).removed == 0
    assert photo.exists()
    assert "is a link; it is not cleaned" in caplog.text


def test_empty_subfolders_are_removed(tmp_path):
    make(tmp_path, "2026/01/old.jpg", 10, 400)
    (tmp_path / "2026" / "02").mkdir()
    storage.clean(tmp_path, 500, 30, now=NOW)
    assert tmp_path.exists() and list(tmp_path.iterdir()) == []


def test_size_limit_waits_when_the_folder_was_not_read_fully(tmp_path, monkeypatch):
    for name in "abc":
        make(tmp_path, f"{name}.jpg", 100 * BLOCK, 1)
    make(tmp_path, "old.jpg", 10, 400)
    monkeypatch.setattr(limits, "STORAGE_MAX_FILES", 2)
    cleaned = storage.clean(tmp_path, 0.1, 30, now=NOW)
    assert not cleaned.finished
    # Old files that were read are removed; nothing for the size limit, as the unread
    # part may hold older files.
    assert cleaned.kept_bytes <= 300 * BLOCK and len(names(tmp_path)) >= 2


def test_folder_swapped_for_a_link_before_removing_leads_nowhere(tmp_path, monkeypatch):
    folder = tmp_path / "plugin"
    make(folder, "sub/a.jpg", 100 * BLOCK, 2)
    make(folder, "b.jpg", 100 * BLOCK, 1)
    outside = tmp_path / "outside"
    precious = make(outside, "a.jpg", 100 * BLOCK, 2)  # same name as the file in sub/
    real = storage._scan

    def scan_then_swap(*args):
        result = real(*args)
        (folder / "sub" / "a.jpg").unlink()
        (folder / "sub").rmdir()
        (folder / "sub").symlink_to(outside)  # swapped after reading, before removing
        return result

    monkeypatch.setattr(storage, "_scan", scan_then_swap)
    storage.clean(folder, 0.5, 0, now=NOW)
    assert precious.exists()


def test_problems_are_one_log_line_per_clean_up(tmp_path, caplog):
    for n in range(20):
        locked = tmp_path / f"locked-{n}"
        make(locked, "file", 10, 1)
        locked.chmod(0)
    try:
        storage.clean(tmp_path, 500, 30, now=NOW)
    finally:
        for n in range(20):
            (tmp_path / f"locked-{n}").chmod(0o700)
    lines = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(lines) == 1
    assert lines[0].startswith(f"cleaning {tmp_path}: 20 problems, the first: 'locked-")


def test_folders_no_block_uses_are_named_but_not_cleaned(tmp_path, caplog):
    old = make(tmp_path / "plugins" / "renamed-photos", "old.jpg", 10, 400)
    storage.clean_all([], tmp_path)
    assert old.exists()
    assert "no [[plugin]] block uses" in caplog.text and "renamed-photos" in caplog.text


def test_clean_all_uses_each_blocks_own_values(tmp_path):
    loaded = config.parse(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        '[[plugin]]\nname = "Keep"\ntype = "basic_clock"\nenabled = false\nstorage_days = 0\n'
        '[[plugin]]\nname = "Small"\ntype = "basic_clock"\nstorage_mb = 1\n'
    )
    kept = make(tmp_path / "plugins" / "keep", "ancient.json", 10, 400)
    for name, days in [("a", 2), ("b", 1)]:
        make(tmp_path / "plugins" / "small", f"{name}.jpg", 150 * BLOCK, days)
    storage.clean_all(loaded.plugins, tmp_path)
    assert kept.exists()
    assert names(tmp_path / "plugins" / "small") == ["b.jpg"]


def test_a_file_exactly_at_the_age_limit_is_kept(tmp_path):
    make(tmp_path, "edge.json", 10, 30)
    storage.clean(tmp_path, 500, 30, now=NOW)
    assert names(tmp_path) == ["edge.json"]


def test_a_folder_exactly_at_the_size_limit_keeps_every_file(tmp_path):
    for name, days in [("a", 2), ("b", 1)]:
        make(tmp_path, f"{name}.jpg", 122 * BLOCK, days)  # 999,424 bytes together
    storage.clean(tmp_path, 1, 0, now=NOW)
    assert names(tmp_path) == ["a.jpg", "b.jpg"]


def test_a_megabyte_is_1000000_bytes(tmp_path):
    for name, days in [("a", 2), ("b", 1)]:
        make(tmp_path, f"{name}.jpg", 125 * BLOCK, days)  # 1,024,000 bytes: over 1 MB, under 1 MiB
    storage.clean(tmp_path, 1, 0, now=NOW)
    assert names(tmp_path) == ["b.jpg"]


def test_age_rule_then_size_rule(tmp_path):
    make(tmp_path, "old.jpg", 200 * BLOCK, 400)
    for name, days in [("a", 3), ("b", 2), ("c", 1)]:
        make(tmp_path, f"{name}.jpg", 100 * BLOCK, days)
    cleaned = storage.clean(tmp_path, 1, 30, now=NOW)  # 1 MB: two of the three fit
    assert names(tmp_path) == ["b.jpg", "c.jpg"]
    assert (cleaned.removed, cleaned.kept_bytes) == (2, 200 * BLOCK)


def test_size_rule_stops_at_the_time_limit(tmp_path, monkeypatch):
    for name, days in [("a", 3), ("b", 2), ("c", 1)]:
        make(tmp_path, f"{name}.jpg", 100 * BLOCK, days)
    ticks = iter(range(1000))
    monkeypatch.setattr(storage.time, "monotonic", lambda: next(ticks) * 0.0)
    real_unlink = storage._unlink

    def slow_unlink(*args):
        monkeypatch.setattr(storage.time, "monotonic", lambda: 1e9)  # time is up after one
        return real_unlink(*args)

    monkeypatch.setattr(storage, "_unlink", slow_unlink)
    cleaned = storage.clean(tmp_path, 0.1, 0, now=NOW)
    assert (cleaned.removed, cleaned.finished) == (1, False)
    assert names(tmp_path) == ["b.jpg", "c.jpg"]


def test_default_time_limit_is_10_seconds():
    assert limits.STORAGE_CLEAN == 10


@pytest.mark.skipif(os.geteuid() == 0, reason="root may remove any file")
def test_file_that_cannot_be_removed_is_logged_and_the_rest_goes_on(tmp_path, caplog):
    locked = tmp_path / "locked"
    make(locked, "old.json", 10, 400)
    other = make(tmp_path, "old.json", 10, 400)
    locked.chmod(0o500)
    try:
        storage.clean(tmp_path, 500, 30, now=NOW)
    finally:
        locked.chmod(0o700)
    assert not other.exists() and (locked / "old.json").exists()
    assert "1 problems, the first: 'locked/old.json: Permission denied'" in caplog.text


def test_second_low_disk_period_is_warned_about_again(caplog):
    caplog.set_level(logging.WARNING)
    free = [0]
    low = storage.LowDisk("/", clock=lambda: 0.0, free=lambda path: free[0])
    enough = (limits.FREE_DISK_MB + limits.FREE_DISK_GAP_MB) * 1_000_000
    for value in (0, enough, enough, 0):
        free[0] = value
        low.check()
    messages = [r.getMessage() for r in caplog.records]
    assert [m.split()[0] for m in messages] == ["only", "the", "only"]


@pytest.mark.parametrize(
    ("setting", "ok"),
    [
        ("storage_mb = 1000000", True),
        ("storage_mb = 1000001", False),
        ("storage_days = 0", True),
        ("storage_days = 36501", False),
    ],
)
def test_highest_storage_settings(setting, ok):
    loaded = config.parse(
        'config_version = 1\n[display]\ntype = "virtual"\n'
        f'[[plugin]]\nname = "Clock"\ntype = "basic_clock"\n{setting}\n'
    )
    assert (not loaded.errors) is ok


@pytest.mark.parametrize(
    "change", [{"storage_mb": 1_000_001}, {"storage_days": -1}, {"storage_days": 36_501}]
)
def test_plugin_suggestions_are_checked(change):
    from dataclasses import replace

    from paperpi import plugins

    with pytest.raises(PluginDefinitionError, match="must be between"):
        replace(plugins.load("basic_clock"), **change)
