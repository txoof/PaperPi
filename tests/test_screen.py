"""The screen helper process and the screen watchdog (paperpi.screen).

The first tests start real helper processes with the pretend drivers of ``fake_screens``.
The watchdog rules are checked with a fake helper and a fake clock, so no test waits for
minutes.
"""

import time
from functools import partial

import pytest
from epdlib import ScreenMode
from epdlib.drivers.virtual import VirtualDriver
from PIL import Image

from paperpi import limits
from paperpi.screen import Helper, Screen, ScreenError, ScreenResting, ScreenStuck, ScreenTimeout

from .fake_screens import Pretend, notes

WHITE, BLACK, GRAY, ERROR = 255, 0, 128, 1  # what the pretend driver does with each shade


def image(shade):
    return Image.new("L", (4, 3), shade)


@pytest.fixture
def short_limit(monkeypatch):
    """The first write may take 5 s instead of 2 minutes (starting a helper takes under 1 s,
    also on a busy Pi)."""
    monkeypatch.setattr(limits, "SCREEN_FIRST", 5.0)


# The helper process


def test_write_reaches_the_driver_in_the_helper_process(tmp_path):
    out = tmp_path / "screen"
    with Screen(partial(VirtualDriver, 4, 3, ScreenMode.gray(16), out)) as screen:
        screen.write(image(WHITE))
        screen.write(image(0x44))
    assert Image.open(out / "latest.png").getpixel((0, 0)) == 0x44
    assert len(list(out.glob("[0-9]*.png"))) == 2
    assert screen.redraw is not None and screen.time_limit == limits.SCREEN_SHORTEST


def test_hanging_write_is_stopped_and_the_next_one_gets_a_new_helper(tmp_path, short_limit):
    with Screen(partial(Pretend, tmp_path)) as screen:
        start = time.monotonic()
        with pytest.raises(ScreenTimeout, match="write took longer than 5 s"):
            screen.write(image(BLACK))
        assert time.monotonic() - start < 10
        screen.write(image(WHITE))
    inits = [pid for pid, what in notes(tmp_path) if what == "init"]
    assert len(set(inits)) == 2  # a new helper process, whose init resets the screen
    assert notes(tmp_path)[-3:] == [
        (inits[1], "write 255"),
        (inits[1], "sleep"),  # after every write; the next one wakes it
        (inits[1], "close"),
    ]


def test_crashed_helper_is_noticed_at_once(tmp_path, short_limit):
    with Screen(partial(Pretend, tmp_path)) as screen:
        with pytest.raises(ScreenError, match="ended during write"):
            screen.write(image(GRAY))
        screen.write(image(WHITE))
    assert [what for _, what in notes(tmp_path)][:4] == ["init", "write 128", "init", "write 255"]


def test_screen_sleeps_after_every_write_and_clear_without_a_new_init(tmp_path):
    with Screen(partial(Pretend, tmp_path)) as screen:
        screen.write(image(WHITE))
        screen.write(image(0x44), fast=True)
        screen.clear()
    assert [what for _, what in notes(tmp_path)] == [
        "init",
        "write 255",
        "sleep",
        "write 68",
        "sleep",
        "clear",
        "sleep",
        "close",
    ]


def test_driver_error_keeps_the_helper(tmp_path):
    with Screen(partial(Pretend, tmp_path)) as screen:
        with pytest.raises(ScreenError, match="write failed: DisplayError: pretend failure"):
            screen.write(image(ERROR))
        screen.clear()
    assert len({pid for pid, _ in notes(tmp_path)}) == 1
    assert [what for _, what in notes(tmp_path)][:3] == ["init", "write 1", "clear"]


def test_failed_init_is_an_error_and_the_next_write_tries_init_again(tmp_path):
    (tmp_path / "no-screen").touch()
    with Screen(partial(Pretend, tmp_path)) as screen:
        with pytest.raises(ScreenError, match="init failed: DisplayError: no screen here"):
            screen.write(image(WHITE))
        assert screen.failures == 1
        (tmp_path / "no-screen").unlink()
        screen.write(image(WHITE))
        assert screen.failures == 0
    inits = [pid for pid, what in notes(tmp_path) if what == "init"]
    assert len(set(inits)) == 2


def test_hanging_init_is_stopped(tmp_path, short_limit):
    screen = Screen(partial(Pretend, tmp_path, hang_init=True))
    with pytest.raises(ScreenTimeout, match="init took longer than 5 s"):
        screen.write(image(WHITE))
    assert not screen._helper.running
    screen.close()


def test_helper_ignores_ctrl_c_and_the_stop_signal(tmp_path):
    import os
    import signal

    with Screen(partial(Pretend, tmp_path)) as screen:
        screen.write(image(WHITE))
        pid = int(notes(tmp_path)[0][0])
        os.kill(pid, signal.SIGINT)
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.2)
        screen.write(image(WHITE))
    assert {p for p, what in notes(tmp_path) if what.startswith("write")} == {str(pid)}


def test_closing_a_screen_that_never_wrote_does_nothing(tmp_path):
    Screen(partial(Pretend, tmp_path)).close()
    assert notes(tmp_path) == []


def test_closing_during_a_hanging_write_does_not_wait_for_it(tmp_path):
    import threading

    screen = Screen(partial(Pretend, tmp_path))
    result = []

    def write():
        try:
            screen.write(image(BLACK))
        except ScreenError as error:
            result.append(error)

    thread = threading.Thread(target=write)
    thread.start()
    deadline = time.monotonic() + 10
    while "write 0" not in [what for _, what in notes(tmp_path)]:
        assert time.monotonic() < deadline, "the write did not start"
        time.sleep(0.05)
    start = time.monotonic()
    screen.close()
    thread.join(10)
    assert not thread.is_alive()
    assert time.monotonic() - start < 10
    assert len(result) == 1  # the write ended with an error


def test_helper_that_cannot_be_stopped_is_stuck():
    class Unkillable:
        pid, exitcode = 1234, None

        def join(self, timeout):
            pass

        def kill(self):
            pass

    class Pipe:
        def close(self):
            pass

    helper = Helper(None)
    helper._process, helper._pipe = Unkillable(), Pipe()
    with pytest.raises(ScreenStuck, match="1234 can't be stopped"):
        helper.stop()
    assert not helper.running

    # Stuck while being stopped after a write that ran over its time limit.
    class Silent(Pipe):
        def send(self, message):
            pass

        def poll(self, timeout):
            return False

    other = Helper(None)
    other._process, other._pipe = Unkillable(), Silent()
    with pytest.raises(ScreenStuck):
        other.call("write", limit=0.1)
    assert not helper.running
    # A new one is not started while the stuck one still runs (it may hold the pins).
    with pytest.raises(ScreenError, match="stuck screen helper process 1234 still runs"):
        helper.start(1)


# The screen watchdog, with a fake helper and a fake clock


class FakeHelper:
    """Fails while ``fail`` is set (with ``fail`` itself when it is an error); raises
    ScreenStuck from stop() while ``stuck`` is set."""

    def __init__(self):
        self.running = False
        self.fail = False
        self.stuck = False
        self.seconds = 2.0
        self.starts = 0
        self.stops = 0
        self.make_driver = None

    def start(self, limit):
        self.running = True
        self.starts += 1

    def call(self, command, *args, limit):
        self.limit = limit
        if isinstance(self.fail, Exception):
            raise self.fail
        if self.fail:
            raise ScreenError("pretend failure")
        return self.seconds

    def stop(self, close=False):
        self.running = False
        self.stops += 1
        if self.stuck:
            raise ScreenStuck("stuck")

    def kill(self):
        pass


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_screen(tmp_path=None, **options):
    helper, clock = FakeHelper(), Clock()
    stuck_file = None if tmp_path is None else tmp_path / "screen-stuck"
    screen = Screen(
        None,
        helper=helper,
        clock=clock,
        wall=lambda: 1e9 + clock.t,
        stuck_file=stuck_file,
        **options,
    )
    return screen, helper, clock


def fail(screen, times=1):
    for _ in range(times):
        with pytest.raises(ScreenError):
            screen.write(image(WHITE))


def test_time_limit_is_three_times_the_redraw_within_bounds():
    screen, helper, _ = make_screen()
    assert screen.time_limit == 120
    assert make_screen(color=True)[0].time_limit == 300
    for seconds, limit in [(2, 30), (20, 60), (200, 300)]:
        helper.seconds = seconds
        screen.write(image(WHITE))
        assert screen.time_limit == limit
    assert helper.limit == 60  # each write has the limit from the write before it


def test_every_third_failure_resets_the_screen(tmp_path, caplog):
    screen, helper, _ = make_screen(tmp_path)
    helper.fail = True
    fail(screen, 2)
    assert helper.starts == 1
    fail(screen)
    assert "screen failed 3 times in a row; resetting it (reset 1 of 3)" in caplog.text
    assert not helper.running  # the next write starts a new helper, which resets the screen
    fail(screen, 6)
    assert (helper.starts, screen.resets) == (3, 3)


def test_writes_pause_when_three_resets_did_not_help_and_the_wait_doubles(caplog):
    screen, helper, clock = make_screen()
    helper.fail = True
    fail(screen, 9)
    with pytest.raises(ScreenResting) as paused:
        screen.write(image(WHITE))  # the write that starts the pause says so
    assert paused.value.wait == 600
    assert "does not answer after 3 resets: pretend failure; next try in 10 minutes" in caplog.text
    assert not helper.running  # the pins are free during the pause
    starts = helper.starts
    clock.t = 599
    with pytest.raises(ScreenResting) as paused:
        screen.write(image(WHITE))
    assert paused.value.wait == pytest.approx(1)
    assert helper.starts == starts  # not tried
    # Each failed try doubles the wait: 20, 40, 80, 160 minutes, then at most 6 hours.
    waits = []
    for _ in range(7):
        clock.t = screen.retry_at
        fail(screen)  # one try, which fails: pause again
        waits.append(screen.retry_at - clock.t)
    assert waits == [1200, 2400, 4800, 9600, 19200, 21600, 21600]
    assert "screen still not answering (since " in caplog.text
    assert "next try in 6 hours" in caplog.text
    assert caplog.text.count("pretend failure") == 1  # the full message once
    clock.t, helper.fail = screen.retry_at, False
    screen.write(image(WHITE))
    assert (screen.failures, screen.resets, screen.retry_at, screen.rests) == (0, 0, None, 0)
    assert "the screen answers again, after 17 failures" in caplog.text


def test_a_config_change_tries_again_at_once_with_the_shortest_wait():
    screen, helper, clock = make_screen()
    helper.fail = True
    fail(screen, 10)
    clock.t = screen.retry_at
    fail(screen)
    assert screen.retry_at - clock.t == 1200
    screen.change()  # e.g. vcom was fixed in the config
    assert screen.retry_at is None
    fail(screen)  # tried at once, without the pause; 3 failures start the counting again
    assert screen.retry_at is None and screen.failures == 1


def test_change_with_a_new_driver_stops_the_helper_with_the_old_one():
    screen, helper, _ = make_screen()
    screen.write(image(WHITE))
    new = object()
    screen.change(new)
    assert not helper.running and helper.make_driver is new
    screen.write(image(WHITE))
    assert helper.starts == 2


def test_check_starts_the_screen_only_once():
    screen, helper, _ = make_screen()
    screen.check()
    screen.check()
    screen.write(image(WHITE))
    assert helper.starts == 1


def test_one_good_write_resets_the_counts():
    screen, helper, _ = make_screen()
    helper.fail = True
    fail(screen, 5)
    helper.fail = False
    screen.write(image(WHITE))
    helper.fail = True
    fail(screen, 2)
    assert (screen.failures, screen.resets) == (2, 0)


def test_stuck_helper_exits_paperpi_at_most_once_per_hour(tmp_path):
    screen, helper, clock = make_screen(tmp_path)
    helper.fail, helper.stuck = True, True
    fail(screen, 2)
    with pytest.raises(ScreenStuck):
        screen.write(image(WHITE))  # the reset at the 3rd failure can't stop the helper
    written = (tmp_path / "screen-stuck").read_text()

    # PaperPi was started again and its helper gets stuck again, within the hour.
    screen, helper, clock = make_screen(tmp_path)
    clock.t = 3000
    helper.fail, helper.stuck = True, True
    fail(screen, 2)
    with pytest.raises(ScreenResting):
        screen.write(image(WHITE))  # no exit: writes pause instead
    assert (tmp_path / "screen-stuck").read_text() == written

    clock.t = 3600 + 600
    with pytest.raises(ScreenStuck):
        screen.write(image(WHITE))  # an hour later it may exit again
    assert (tmp_path / "screen-stuck").read_text() != written


def test_without_a_stuck_file_a_stuck_helper_pauses_writes():
    screen, helper, _ = make_screen()
    helper.fail, helper.stuck = True, True
    fail(screen, 2)
    with pytest.raises(ScreenResting):
        screen.write(image(WHITE))


@pytest.mark.parametrize("content", ["nan", "inf", "1e300", "junk", ""])
def test_odd_stuck_file_does_not_stop_the_exit(tmp_path, content):
    (tmp_path / "screen-stuck").write_text(content)
    screen, helper, _ = make_screen(tmp_path)
    helper.fail, helper.stuck = True, True
    fail(screen, 2)
    with pytest.raises(ScreenStuck):
        screen.write(image(WHITE))


def test_stuck_file_that_is_a_link_is_not_followed(tmp_path):
    (tmp_path / "screen-stuck").symlink_to("/dev/zero")
    screen, helper, _ = make_screen(tmp_path)
    helper.fail, helper.stuck = True, True
    fail(screen, 2)
    with pytest.raises(ScreenStuck):
        screen.write(image(WHITE))


def test_stuck_file_that_cannot_be_written_pauses_instead_of_exiting(tmp_path):
    screen, helper, _ = make_screen(tmp_path / "missing-folder")
    helper.fail, helper.stuck = True, True
    fail(screen, 2)
    with pytest.raises(ScreenResting):
        screen.write(image(WHITE))


def test_closed_screen_starts_no_new_helper():
    screen, helper, _ = make_screen()
    screen.close()
    with pytest.raises(ScreenError, match="closed"):
        screen.write(image(WHITE))
    assert helper.starts == 0


def test_only_writes_change_the_measured_redraw():
    screen, helper, _ = make_screen()
    helper.seconds = 20
    screen.write(image(WHITE))
    helper.seconds = 200
    screen.clear()
    assert screen.time_limit == 60


def test_write_that_hangs_and_cannot_be_stopped_exits_at_most_once_per_hour(tmp_path):
    screen, helper, clock = make_screen(tmp_path)
    helper.fail = ScreenStuck("can't be stopped")
    with pytest.raises(ScreenStuck):
        screen.write(image(WHITE))
    assert (tmp_path / "screen-stuck").exists()
    screen, helper, clock = make_screen(tmp_path)
    helper.fail = ScreenStuck("can't be stopped")
    with pytest.raises(ScreenResting):
        screen.write(image(WHITE))
