"""``paperpi reload`` (paperpi.reload): find the running PaperPi, send the reload signal and
report the result."""

import json
import os
import signal

import pytest

from paperpi import cli, config, health, limits, reload
from paperpi.health import Health

CONFIG = """\
config_version = 1
[display]
type = "virtual"

[[plugin]]
id = "basic_clock-5c1e0a7b"
name = "Clock"
type = "basic_clock"
display_time = 300

[[plugin]]
id = "music"
type = "lms_client"
player_name = "Kitchen"
password = "one"
"""
PID = 4321


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class FakePaperPi:
    """Answers the reload signal like ``paperpi run``: a new health report with the result."""

    def __init__(self, path, tmp_path):
        self.health = Health(path, disk=tmp_path, notify=lambda name: None)
        self.signals = []
        self.answer = ()  # the errors of the next reload; None: no answer
        self.refuse = None

    def report(self, pid=PID):
        self.health.report(None)
        values = health.read(self.health.path)
        values["pid"] = pid
        self.health.path.write_text(json.dumps(values))

    def kill(self, pid, number):
        if self.refuse is not None:
            raise self.refuse
        self.signals.append((pid, number))
        if self.answer is not None:
            self.health.reloaded(self.answer)
            self.report()


@pytest.fixture
def setup(tmp_path):
    """The config file, the last good copy and a running fake PaperPi."""
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    (tmp_path / config.LAST_GOOD_NAME).write_text(CONFIG)
    paperpi = FakePaperPi(tmp_path / "health", tmp_path)
    paperpi.report()
    clock = FakeClock()

    def run(check_only=False, is_paperpi=lambda pid: True):
        return reload.run(
            path,
            tmp_path,
            tmp_path / "health",
            check_only=check_only,
            kill=paperpi.kill,
            is_paperpi=is_paperpi,
            clock=clock,
            sleep=clock.sleep,
        )

    run.path, run.paperpi, run.clock = path, paperpi, clock
    return run


def edit(path, old, new):
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def test_reload_sends_the_signal_and_lists_the_changes(setup):
    edit(setup.path, "display_time = 300", "display_time = 600")
    edit(setup.path, 'password = "one"', 'password = "two"')
    status, lines = setup()
    assert status == reload.OK
    assert setup.paperpi.signals == [(PID, signal.SIGHUP)]
    assert lines == [
        "Applied.",
        "Changes:",
        "  Clock (basic_clock-5c1e0a7b)",
        "    display_time: 300 -> 600",
        "  music",
        "    password: (hidden) -> (hidden)",
    ]


def test_new_and_removed_plugins_and_defaults_are_listed(setup):
    edit(setup.path, "display_time = 300\n", "")
    setup.path.write_text(
        setup.path.read_text() + '\n[[plugin]]\nid = "new"\ntype = "basic_clock"\n'
    )
    status, lines = setup()
    assert status == reload.OK
    assert lines[2:] == [
        "  Clock (basic_clock-5c1e0a7b)",
        "    display_time: 300 -> (default: 120)",
        "  new: new plugin",
        "    Joins the order at place 3 (where it is in the file). Its ID is new, so it starts "
        "with an empty storage folder.",
    ]


def test_no_changes(setup):
    assert setup() == (reload.OK, ["Applied.", "No changes in the settings."])


def test_a_file_with_a_mistake_is_not_sent(setup):
    setup.path.write_text(CONFIG + "\n[display\n")
    status, lines = setup()
    assert status == reload.FAILED
    assert lines[0] == "The config file has a mistake, so it can't be applied:"
    assert "line" in lines[1]
    assert lines[-1] == "Nothing was sent; PaperPi keeps running with the old settings."
    assert setup.paperpi.signals == []


def test_a_plugin_with_a_mistake_is_named_but_the_rest_applies(setup):
    edit(setup.path, "display_time = 300", 'display_time = "soon"')
    status, lines = setup()
    assert status == reload.OK
    at = lines.index("These plugins have a mistake; PaperPi leaves them out until it is fixed:")
    assert "display_time" in lines[at + 1]


def test_paperpi_refuses_the_file(setup):
    setup.paperpi.answer = ("paperpi.toml: can't read: Permission denied",)
    status, lines = setup()
    assert status == reload.FAILED
    assert lines == [
        "PaperPi could not use the config file; the old settings keep running:",
        "  paperpi.toml: can't read: Permission denied",
    ]


def test_an_earlier_reload_is_not_taken_for_this_one(setup):
    setup.paperpi.health.reloaded(())  # a reload from the web interface, before
    setup.paperpi.report()
    setup.paperpi.answer = None  # PaperPi does not answer this time
    status, lines = setup()
    assert status == reload.FAILED
    assert "did not answer within 30 seconds" in lines[0]
    assert setup.clock.t >= limits.RELOAD_WAIT


def test_paperpi_stops_or_starts_again_while_waiting(setup):
    setup.paperpi.answer = None
    setup.paperpi.kill = lambda pid, number: setup.paperpi.report(pid=PID + 1)
    assert setup()[1] == ["PaperPi started again before it loaded the config file."]
    setup.paperpi.kill = lambda pid, number: setup.paperpi.health.path.unlink()
    setup.paperpi.report()
    assert setup()[1] == ["PaperPi stopped before it loaded the config file."]


def test_not_running(setup):
    setup.paperpi.health.path.unlink()
    status, lines = setup()
    assert status == reload.FAILED
    assert lines[0].startswith("PaperPi is not running: there is no health report in ")
    assert "--health-file" in lines[0]


def test_a_stale_report_or_another_program(setup):
    setup.paperpi.report()
    values = health.read(setup.paperpi.health.path)
    values["monotonic"] -= limits.HEALTH_STALE + 10
    setup.paperpi.health.path.write_text(json.dumps(values))
    assert setup()[1][0].startswith("PaperPi can't be reached: not responding")
    setup.paperpi.report()
    assert setup(is_paperpi=lambda pid: False)[1] == [
        f"Process {PID} from the health report is not PaperPi."
    ]
    assert setup.paperpi.signals == []


def test_no_permission_says_sudo(setup):
    setup.paperpi.refuse = PermissionError()
    status, lines = setup()
    assert status == reload.FAILED
    assert "sudo paperpi reload" in lines[0]


def test_check_only_sends_nothing_and_works_without_paperpi(setup):
    setup.paperpi.health.path.unlink()
    edit(setup.path, "display_time = 300", "display_time = 600")
    status, lines = setup(check_only=True)
    assert status == reload.OK
    assert lines[:2] == ["The config file can be used.", "Changes:"]
    setup.path.write_text("[display\n")
    assert setup(check_only=True)[0] == reload.FAILED
    assert setup.paperpi.signals == []


def test_without_a_last_good_copy_the_changes_are_not_listed(setup, tmp_path):
    (tmp_path / config.LAST_GOOD_NAME).unlink()
    status, lines = setup()
    assert status == reload.OK
    assert lines[1].startswith("(The changes can't be listed: no last good copy")


def test_odd_reasons_in_the_health_report_are_printed_safely(setup):
    setup.paperpi.answer = None

    numbers = iter(range(10, 20))

    def answer(errors):
        def kill(pid, number):
            setup.paperpi.report()
            values = health.read(setup.paperpi.health.path)
            values["reload"] = {"number": next(numbers), "errors": errors}
            setup.paperpi.health.path.write_text(json.dumps(values))

        return kill

    setup.paperpi.kill = answer("not a list")
    assert setup()[1][1:] == ["  (the reason in the health report can't be read)"]
    setup.paperpi.kill = answer(["red \x1b[31m text", "two", "three"])
    assert setup()[1][1:] == ["  red ?[31m text", "  two", "  three"]


def test_a_broken_report_while_waiting_is_read_again(setup):
    setup.paperpi.answer = None
    tries = []

    def kill(pid, number):
        setup.paperpi.health.path.write_text("{broken")
        tries.append(number)

    setup.paperpi.kill = kill
    real_sleep = setup.clock.sleep

    def sleep(seconds):
        real_sleep(seconds)
        if setup.clock.t > 1 and setup.paperpi.health.path.read_text() == "{broken":
            setup.paperpi.health.reloaded(())
            setup.paperpi.report()

    status, lines = reload.run(
        setup.path,
        setup.path.parent,
        setup.paperpi.health.path,
        kill=kill,
        is_paperpi=lambda pid: True,
        clock=setup.clock,
        sleep=sleep,
    )
    assert (status, lines[0]) == (reload.OK, "Applied.")


def test_paperpi_gone_at_the_signal(setup):
    setup.paperpi.refuse = ProcessLookupError()
    assert setup() == (reload.FAILED, ["PaperPi is not running (it stopped just now)."])


def test_an_unreadable_config_file_says_sudo(setup, monkeypatch):
    def refuse(path):
        raise config.ConfigError([config.Problem("error", "can't read: Permission denied")])

    monkeypatch.setattr(config, "read_text", refuse)
    status, lines = setup()
    assert status == reload.FAILED and lines[0].endswith("sudo paperpi reload")


@pytest.mark.parametrize(
    ("cmdline", "is_run"),
    [
        (b"/opt/paperpi/venv/bin/python3\0/opt/paperpi/venv/bin/paperpi\0run\0", True),
        (b"/usr/bin/python3\0-m\0paperpi\0run\0--config\0x.toml\0", True),
        (b"/opt/paperpi/venv/bin/python3\0/opt/paperpi/venv/bin/paperpi\0reload\0", False),
        (b"/usr/bin/python3\0foo.py\0run\0", False),
        (b"/usr/bin/vim\0paperpi\0", False),
    ],
)
def test_what_counts_as_paperpi_run(cmdline, is_run):
    assert reload.runs_paperpi(cmdline) is is_run


def test_this_process_is_not_paperpi_run():
    assert not reload._is_paperpi(os.getpid())
    assert not reload._is_paperpi(2**22 + 1)  # no such process


def test_command_line(tmp_path, capsys):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    args = ["--config", str(path), "--state-dir", str(tmp_path)]
    assert cli.main(["reload", *args, "--check"]) == 0
    assert "The config file can be used." in capsys.readouterr().out
    status = cli.main(["reload", *args, "--health-file", str(tmp_path / "health")])
    assert status == 1
    assert "PaperPi is not running" in capsys.readouterr().err
