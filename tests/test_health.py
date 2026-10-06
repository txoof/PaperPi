"""The health report (paperpi.health): messages to systemd, the health file and its check."""

import json
import logging
import os
import socket
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

    monkeypatch.setattr(health, "send_to_systemd", fail)
    reports = Health(tmp_path / "health", disk=tmp_path, notify_socket=None)
    reports.report(None)
    reports.stopping()


@pytest.mark.parametrize("abstract", [False, True])
def test_messages_reach_a_real_socket(tmp_path, abstract):
    # Stands in for systemd. An address starting with @ is an "abstract" socket (no file).
    address = f"@paperpi-test-{os.getpid()}" if abstract else str(tmp_path / "notify")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as systemd:
        systemd.bind("\0" + address[1:] if abstract else address)
        systemd.settimeout(5)
        reports = Health(tmp_path / "health", disk=tmp_path, notify_socket=address)
        reports.report(None)
        reports.report(None)
        reports.stopping()
        received = [systemd.recv(100) for _ in range(4)]
    assert received == [b"READY=1", b"WATCHDOG=1", b"WATCHDOG=1", b"STOPPING=1"]


@pytest.mark.parametrize("address", ["/no/such/socket", "vsock:2:1234"])
def test_message_to_a_missing_or_unknown_socket_is_only_logged(tmp_path, caplog, address):
    reports = Health(tmp_path / "health", disk=tmp_path, notify_socket=address)
    with caplog.at_level(logging.WARNING):
        reports.report(None)
        reports.stopping()
    assert "can't send READY to systemd" in caplog.text


def test_ready_is_sent_again_until_it_works(tmp_path, systemd):
    reports = Health(tmp_path / "health", disk=tmp_path, notify=systemd)
    systemd.fail = True
    reports.report(None)
    systemd.fail = False
    reports.report(None)
    reports.report(None)
    assert systemd.messages == ["READY", "WATCHDOG", "READY", "WATCHDOG", "WATCHDOG"]


def test_report_holds_the_health_data(tmp_path, systemd):
    path = tmp_path / "run" / "health"  # the folder is made when needed
    Health(path, disk=tmp_path, notify=systemd).report(12.34)
    values = json.loads(path.read_text())
    assert abs(values["monotonic"] - time.monotonic()) < 5
    assert values["since_screen"] == 12.3
    assert values["memory_mb"] > 1
    assert abs(values["open_files"] - (len(os.listdir("/proc/self/fd")) - 1)) <= 1
    assert values["free_disk_mb"] > 0
    assert values["time"]
    assert path.stat().st_mode & 0o777 == 0o644


def test_health_values_go_to_the_log_at_the_start_and_then_every_hour(tmp_path, systemd, caplog):
    now = [1000.0]
    reports = Health(tmp_path / "health", disk=tmp_path, notify=systemd, clock=lambda: now[0])
    with caplog.at_level(logging.INFO, logger="paperpi.health"):
        for _ in range(250):  # 2 hours and 5 minutes, a report every 30 s
            reports.report(7)
            now[0] += limits.HEALTH_REPORT
    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 3  # at the start, after 1 hour, after 2 hours
    assert lines[0].startswith("health: since_screen 7, memory_mb ")
    assert "open_files" in lines[0] and "free_disk_mb" in lines[0]


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
    # It keeps trying: READY (not sent yet) and WATCHDOG, at every report.
    assert systemd.messages == ["READY", "WATCHDOG"] * 5
    assert [r.getMessage().split(":")[0] for r in caplog.records] == [
        f"can't write the health report to {blocked / 'health'}",
        "can't send READY to systemd",
    ]


def test_failure_that_comes_back_after_working_is_logged_again(tmp_path, systemd, caplog):
    blocked = tmp_path / "folder"
    reports = Health(blocked / "health", disk=tmp_path, notify=systemd)
    with caplog.at_level(logging.WARNING):
        for fails in (True, False, True):
            systemd.fail = fails
            if fails:
                blocked.write_text("")  # a file where the folder should be
            else:
                blocked.unlink()
            reports.report(None)
            if not fails:
                (blocked / "health").unlink()
                blocked.rmdir()
    messages = [r.getMessage().split(" ")[1] for r in caplog.records]
    assert messages == ["write", "send", "write", "send"]


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
