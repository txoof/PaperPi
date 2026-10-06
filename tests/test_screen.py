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
    """The first write may take 2 s instead of 2 minutes."""
    monkeypatch.setattr(limits, "SCREEN_FIRST", 2.0)


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
        with pytest.raises(ScreenTimeout, match="longer than 2 s"):
            screen.write(image(BLACK))
        assert time.monotonic() - start < 10
        screen.write(image(WHITE))
    inits = [pid for pid, what in notes(tmp_path) if what == "init"]
    assert len(set(inits)) == 2  # a new helper process, whose init resets the screen
    assert notes(tmp_path)[-2:] == [(inits[1], "write 255"), (inits[1], "close")]


def test_crashed_helper_is_noticed_at_once(tmp_path, short_limit):
    with Screen(partial(Pretend, tmp_path)) as screen:
        with pytest.raises(ScreenError, match="ended during write"):
            screen.write(image(GRAY))
        screen.write(image(WHITE))
    assert [what for _, what in notes(tmp_path)][:4] == ["init", "write 128", "init", "write 255"]


def test_driver_error_keeps_the_helper(tmp_path):
    with Screen(partial(Pretend, tmp_path)) as screen:
        with pytest.raises(ScreenError, match="write failed: DisplayError: pretend failure"):
            screen.write(image(ERROR))
        screen.clear()
    assert len({pid for pid, _ in notes(tmp_path)}) == 1
    assert [what for _, what in notes(tmp_path)][:3] == ["init", "write 1", "clear"]


def test_failed_init_is_an_error(tmp_path):
    with Screen(partial(Pretend, tmp_path, fail_init=True)) as screen:
        with pytest.raises(ScreenError, match="init failed: DisplayError: no screen here"):
            screen.write(image(WHITE))
    assert screen.failures == 1


def test_closing_during_a_hanging_write_does_not_wait_for_it(tmp_path):
    import threading

    screen = Screen(partial(Pretend, tmp_path))
    thread = threading.Thread(target=lambda: pytest.raises(ScreenError, screen.write, image(BLACK)))
    thread.start()
    while "write 0" not in [what for _, what in notes(tmp_path)]:
        time.sleep(0.05)
    start = time.monotonic()
    screen.close()
    thread.join(10)
    assert not thread.is_alive()
    assert time.monotonic() - start < 10


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
    assert not helper.running  # forgotten, so a new one can be started


# The screen watchdog, with a fake helper and a fake clock


class FakeHelper:
    """Fails while ``fail`` is set; raises ``stuck`` from stop() when set."""

    def __init__(self):
        self.running = False
        self.fail = False
        self.stuck = False
        self.seconds = 2.0
        self.starts = 0
        self.stops = 0

    def start(self, limit):
        self.running = True
        self.starts += 1

    def call(self, command, *args, limit):
        self.limit = limit
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


def test_writes_pause_when_three_resets_did_not_help_and_are_tried_every_10_minutes(caplog):
    screen, helper, clock = make_screen()
    helper.fail = True
    fail(screen, 10)
    assert "does not answer after 3 resets; trying again every 10 minutes" in caplog.text
    assert not helper.running  # the pins are free during the pause
    starts = helper.starts
    clock.t = 599
    with pytest.raises(ScreenResting) as paused:
        screen.write(image(WHITE))
    assert paused.value.wait == pytest.approx(1)
    assert helper.starts == starts  # not tried
    clock.t = 600
    fail(screen)  # one try, which fails: pause again
    assert screen.retry_at == 1200
    clock.t, helper.fail = 1200, False
    screen.write(image(WHITE))
    assert (screen.failures, screen.resets, screen.retry_at) == (0, 0, None)
    assert "the screen answers again, after 11 failures" in caplog.text


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
