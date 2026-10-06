"""The health report (paperpi.health): messages to systemd, the health file and its check."""

import json
import logging
import time

import pytest

from paperpi import health, limits
from paperpi.health import Health, check


class FakeSystemd:
    def __init__(self):
        self.messages = []
        self.fail = False

    def __call__(self, name):
        self.messages.append(name)
        if self.fail:
            raise OSError("socket gone")


@pytest.fixture
def systemd():
    return FakeSystemd()


def test_first_report_says_ready_then_every_report_says_watchdog(tmp_path, systemd):
    reports = Health(tmp_path / "health", disk=tmp_path, notify=systemd)
    reports.report(None)
    reports.report(None)
    reports.stopping()
    assert systemd.messages == ["READY", "WATCHDOG", "WATCHDOG", "STOPPING"]


def test_nothing_is_sent_without_systemd(tmp_path, monkeypatch):
    def fail(name):
        raise AssertionError("sent without systemd")

    monkeypatch.setattr(health, "_systemd_notify", fail)
    reports = Health(tmp_path / "health", disk=tmp_path, environ={})
    reports.report(None)
    reports.stopping()


def test_report_holds_the_health_data(tmp_path, systemd):
    path = tmp_path / "run" / "health"  # the folder is made when needed
    Health(path, disk=tmp_path, notify=systemd).report(12.34)
    values = json.loads(path.read_text())
    assert abs(values["monotonic"] - time.monotonic()) < 5
    assert values["since_screen"] == 12.3
    assert values["memory_mb"] > 1
    assert values["open_files"] >= 3  # at least standard input, output and error
    assert values["free_disk_mb"] > 0
    assert values["time"]
    assert path.stat().st_mode & 0o777 == 0o644


def test_report_is_replaced_and_never_grows(tmp_path, systemd):
    path = tmp_path / "health"
    reports = Health(path, disk=tmp_path, notify=systemd)
    for _ in range(200):
        reports.report(None)
    assert len(path.read_text().splitlines()) == 1
    assert path.stat().st_size < 200
    assert [p.name for p in tmp_path.iterdir()] == ["health"]  # no temporary files left


def test_stopping_removes_the_file(tmp_path, systemd):
    path = tmp_path / "health"
    reports = Health(path, disk=tmp_path, notify=systemd)
    reports.report(None)
    reports.stopping()
    assert not path.exists()


def test_failures_are_logged_once_and_never_raise(tmp_path, systemd, caplog):
    blocked = tmp_path / "file"
    blocked.write_text("")
    systemd.fail = True
    reports = Health(blocked / "health", disk=tmp_path, notify=systemd)
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            reports.report(None)
    assert len(systemd.messages) == 6  # READY and 5 WATCHDOG: it keeps trying
    assert [r.getMessage().split(":")[0] for r in caplog.records] == [
        "can't send READY to systemd",
        f"can't write the health report to {blocked / 'health'}",
    ]


def test_check_a_fresh_report(tmp_path, systemd):
    path = tmp_path / "health"
    Health(path, disk=tmp_path, notify=systemd).report(5)
    healthy, message = check(path)
    assert healthy
    assert message.startswith("healthy: last report 0 s ago (since_screen 5")


@pytest.mark.parametrize(
    ("age", "healthy"),
    [
        (limits.HEALTH_STALE, True),
        (limits.HEALTH_STALE + 1, False),
        (-limits.HEALTH_REPORT - 1, False),  # from the future: not a report of this start
    ],
)
def test_check_the_age(tmp_path, systemd, age, healthy):
    path = tmp_path / "health"
    Health(path, disk=tmp_path, notify=systemd).report(None)
    written = json.loads(path.read_text())["monotonic"]
    result, message = check(path, now=written + age)
    assert result is healthy
    if not healthy:
        assert message.startswith("not responding")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "PaperPi is not running"),
        ("not json", "can't be read"),
        ('{"time": "no monotonic"}', "can't be read"),
        ('{"monotonic": "soon"}', "can't be read"),
        ("[" * 2000, "can't be read: too large"),
    ],
)
def test_check_a_missing_or_broken_file(tmp_path, content, message):
    path = tmp_path / "health"
    if content is not None:
        path.write_text(content)
    healthy, text = check(path)
    assert not healthy
    assert message in text
