"""The scheduler (paperpi.scheduler), run with a fake clock.

The fake clock is also the executor: an update takes 1 second of fake time (or what a test
sets), and the scheduler's waits jump straight to the next event. Hours of switching are
checked in a fraction of a second, and every run gives the same result.

Each fake plugin follows a plan: the outcome of each update, by the fake time it finishes.
An outcome is a label, which becomes an image in a shade of gray of its own, or "nothing" or
"fail". The fake screen turns each image it is sent back into its label.
"""

import heapq
import itertools
import math
from datetime import datetime, timedelta

import pytest
from PIL import Image

from paperpi import config, limits
from paperpi.plugin import State
from paperpi.runner import PluginFailed, UpdateResult
from paperpi.scheduler import Scheduler

SIZE = (40, 30)


class FakeTime:
    """A fake clock, which is also the executor that runs the updates."""

    def __init__(self, start=datetime(2026, 10, 5, 10, 0, 0)):
        self.t = 0.0
        self.start = start
        self.jobs = []
        self.order = itertools.count()
        self.duration = lambda context: 1.0
        """Seconds of fake time an update takes."""

    def monotonic(self):
        return self.t

    def now(self):
        return self.start + timedelta(seconds=self.t)

    def submit(self, fn, *args):
        self.at(self.t + self.duration(args[-1]), fn, *args)

    def at(self, when, fn, *args):
        heapq.heappush(self.jobs, (when, next(self.order), fn, args))

    def _run_next(self):
        when, _, fn, args = heapq.heappop(self.jobs)
        self.t = max(self.t, when)
        fn(*args)

    def shutdown(self, **options):
        pass

    def wait(self, events, timeout):
        deadline = math.inf if timeout is None else self.t + timeout
        while events.empty() and self.jobs and self.jobs[0][0] <= deadline:
            self._run_next()
        while self.jobs and self.jobs[0][0] <= self.t:
            self._run_next()  # everything that finishes at the same moment
        if not events.empty():
            return events.get_nowait()
        assert deadline != math.inf, "the scheduler would wait forever"
        self.t = deadline
        return None


class Labels:
    """Gives each label its own shade of gray, and back."""

    def __init__(self):
        self.shades = {}

    def image(self, label):
        shade = self.shades.setdefault(label, len(self.shades) + 1)
        return Image.new("L", SIZE, shade)

    def label(self, image):
        shade = image.getpixel((0, 0))
        return next(label for label, s in self.shades.items() if s == shade)


class FakeUpdates:
    """Stands in for running a plugin process. Records when each update finished."""

    def __init__(self, clock, labels):
        self.clock = clock
        self.labels = labels
        self.plans = {}
        self.calls = []
        self.default_fails = False

    def __call__(self, plugin_type, context, time_limit):
        name = context.storage.name
        self.calls.append((self.clock.t, name))
        if context.status is not None:
            if self.default_fails:
                raise PluginFailed(plugin_type, "fake failure of default")
            outcome = f"default {context.status.failing}/{context.status.total}"
        else:
            plan = self.plans.get(name, name.upper())
            outcome = plan(self.clock.t) if callable(plan) else plan
        if outcome == "fail":
            raise PluginFailed(plugin_type, "fake failure")
        if outcome == "nothing":
            return UpdateResult(State.NOTHING, None, 1.0)
        if outcome.startswith("alert:"):  # the plugin reports the state "alert"
            return UpdateResult(State.ALERT, self.labels.image(outcome), 1.0)
        return UpdateResult(State.READY, self.labels.image(outcome), 1.0)

    def times(self, name):
        return [t for t, n in self.calls if n == name]


class FakeScreen:
    def __init__(self, clock, labels):
        self.clock = clock
        self.labels = labels
        self.write_seconds = 0.0
        self.fail = False
        self.writes = []
        self.sizes = []

    def write(self, image):
        self.sizes.append(image.size)
        self.writes.append((self.clock.t, self.labels.label(image)))
        if self.fail:
            raise OSError("screen not answering")
        self.clock.t += self.write_seconds


def make_config(*blocks, display=""):
    text = f'config_version = 1\n[display]\ntype = "virtual"\nwidth = {SIZE[0]}\n'
    text += f"height = {SIZE[1]}\n{display}\n"
    for block in blocks:
        plugin_type = "" if "type =" in block else 'type = "debugging"\n'
        text += f"[[plugin]]\n{plugin_type}{block}\n"
    loaded = config.parse(text)
    assert not loaded.errors, loaded.problems
    return loaded


def rotation(name, display_time=100, refresh=30):
    return f'name = "{name}"\nlevel = "rotation"\ndisplay_time = {display_time}\n' + (
        f"refresh = {refresh}"
    )


def interrupt(name, refresh=5):
    return f'name = "{name}"\nlevel = "interrupt"\nrefresh = {refresh}\ndisplay_time = 100'


def alert(name, refresh=10, **extra):
    """An alert plugin block; ``extra`` are more settings, e.g. ``alert_reminder=300``."""
    lines = "".join(f"\n{key} = {value}" for key, value in extra.items())
    return f'name = "{name}"\nlevel = "alert"\nrefresh = {refresh}{lines}'


def between(start, end, inside, outside="nothing"):
    """A plan: ``inside`` from fake time ``start`` up to ``end``, else ``outside``."""
    return lambda t: inside if start <= t < end else outside


class Sim:
    def __init__(self, tmp_path, *blocks, display=""):
        self.clock = FakeTime()
        self.labels = Labels()
        self.updates = FakeUpdates(self.clock, self.labels)
        self.screen = FakeScreen(self.clock, self.labels)
        self.next_config = None
        self.scheduler = Scheduler(
            make_config(*blocks, display=display),
            self.screen,
            state_dir=tmp_path,
            reload=self.load,
            clock=self.clock,
            executor=self.clock,
            update=self.updates,
        )

    def load(self):
        if isinstance(self.next_config, Exception):
            raise self.next_config
        return self.next_config

    def plan(self, **plans):
        self.updates.plans.update(plans)

    def at(self, when, fn, *args):
        self.clock.at(when, fn, *args)

    def run(self, until):
        self.clock.at(until, self.scheduler.stop)
        self.scheduler.run()

    @property
    def writes(self):
        return self.screen.writes

    @property
    def shown(self):
        """The labels written, in order."""
        return [label for _, label in self.writes]


# Rotation


def test_rotation_plugins_take_turns(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.run(until=450)
    assert sim.writes == [(1, "A"), (101, "B"), (201, "C"), (301, "A"), (401, "B")]


def test_each_plugin_has_its_own_display_time(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=50), rotation("b", display_time=200))
    sim.run(until=400)
    assert sim.writes == [(1, "A"), (51, "B"), (251, "A"), (301, "B")]


def test_plugins_update_all_the_time_also_when_not_on_screen(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=1000, refresh=60), rotation("b", refresh=60))
    sim.run(until=200)
    # An update takes 1 s, the next one starts 60 s after it finished.
    assert sim.updates.times("b") == [1, 62, 123, 184]
    assert sim.shown == ["A"]


def test_unchanged_image_is_not_written_again(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=30))
    sim.run(until=1000)
    assert len(sim.updates.times("a")) > 30
    assert sim.writes == [(1, "A")]


def test_changed_image_of_the_plugin_on_screen_is_written(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=30))
    sim.plan(a=lambda t: "A1" if t < 50 else "A2")
    sim.run(until=200)
    assert sim.writes == [(1, "A1"), (63, "A2")]


def test_rotation_plugin_with_nothing_is_skipped_without_failing(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.plan(b="nothing")
    sim.run(until=400)
    assert sim.shown == ["A", "C", "A", "C"]
    assert sim.updates.times("default") == []


def test_plugin_on_screen_that_has_nothing_now_is_replaced(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=1000), rotation("b"))
    sim.plan(a=between(0, 50, "A"))
    sim.run(until=200)
    assert sim.writes == [(1, "A"), (63, "B")]


def test_one_plugin_gets_turn_after_turn(tmp_path):
    sim = Sim(tmp_path, rotation("a"))
    sim.run(until=1000)
    assert sim.writes == [(1, "A")]


def test_refresh_near_the_end_of_a_turn_is_not_written(tmp_path):
    # Screen writes take 20 s. A's turn starts once its first image is on screen (t=21)
    # and ends at 121. A's updates finish every 26 s, each with a new image.
    sim = Sim(tmp_path, rotation("a", refresh=25), rotation("b", refresh=1000))
    sim.screen.write_seconds = 20
    sim.plan(a=lambda t: f"A{t:g}")
    sim.run(until=130)
    assert sim.updates.times("a") == [1, 27, 53, 79, 105]
    # A105 is not written: only 16 s of A's turn are left, less than a screen write.
    assert sim.writes == [(1, "A1"), (27, "A27"), (53, "A53"), (79, "A79"), (121, "B")]


def test_refresh_near_the_end_is_written_when_no_other_plugin_is_waiting(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=25))
    sim.screen.write_seconds = 20
    sim.plan(a=lambda t: f"A{t:g}")
    sim.run(until=130)
    assert (105, "A105") in sim.writes


# Interrupts and alerts


def test_interrupt_takes_over_at_once_and_rotation_goes_on_with_the_next(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"), interrupt("m"))
    sim.plan(m=between(150, 250, "M"))
    sim.run(until=400)
    # M is checked every 6 s (5 s refresh + 1 s update): it finds the song at 150..156.
    assert sim.shown == ["A", "B", "M", "C", "A"]
    m_start = sim.writes[2][0]
    assert 150 <= m_start <= 157
    c_start = sim.writes[3][0]
    assert 250 <= c_start <= 257


def test_several_interrupts_take_turns(tmp_path):
    sim = Sim(tmp_path, rotation("a"), interrupt("m"), interrupt("n"))
    sim.plan(m="M", n="N")
    sim.run(until=350)
    assert sim.shown == ["M", "N", "M", "N"]


def test_alert_is_not_interrupted(tmp_path):
    sim = Sim(tmp_path, rotation("a"), interrupt("m"), alert("x"))
    sim.plan(x=between(50, 10_000, "X"), m=between(100, 10_000, "M"))
    sim.run(until=500)
    assert sim.shown == ["A", "X"]


def test_dismissed_alert_comes_back_as_a_reminder(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=10_000), alert("x", alert_reminder=300))
    sim.plan(x=between(50, 10_000, "X"))
    sim.at(100, sim.scheduler.dismiss, "x")
    sim.run(until=1000)
    # X is checked every 11 s (10 s refresh + 1 s update): it finds the alert at 56.
    assert sim.writes == [(1, "A"), (56, "X"), (100, "A"), (400, "X")]


def test_alert_held_too_long_is_dismissed_until_a_new_alert(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=10_000), alert("x", alert_max_time=1000))
    # Alert from 50 to 2000, nothing until 2500, then a new alert.
    sim.plan(x=lambda t: "X" if 50 <= t < 2000 or t >= 2500 else "nothing")
    sim.run(until=3000)
    assert sim.shown == ["A", "X", "A", "X"]
    assert sim.writes[2][0] == pytest.approx(56 + 1000)
    assert 2500 <= sim.writes[3][0] <= 2511


def test_several_alerts_take_turns(tmp_path):
    sim = Sim(tmp_path, rotation("a"), alert("x", display_time=50), alert("y", display_time=50))
    sim.plan(x="X", y="Y")
    sim.run(until=250)
    assert sim.writes == [(1, "X"), (51, "Y"), (101, "X"), (151, "Y"), (201, "X")]


def test_new_alert_after_a_dismissed_one_ended_is_shown_at_once(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=10_000), alert("x", alert_reminder=3000))
    sim.plan(x=lambda t: "X" if 50 <= t < 150 or t >= 200 else "nothing")
    sim.at(100, sim.scheduler.dismiss, "x")
    sim.run(until=300)
    assert sim.writes == [(1, "A"), (56, "X"), (100, "A"), (210, "X")]


def test_alert_safety_limit_wakes_the_scheduler_at_the_exact_time(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=10_000), alert("x", alert_max_time=1003))
    sim.plan(x=between(50, 10_000, "X"))
    sim.run(until=1100)
    assert sim.writes == [(1, "A"), (56, "X"), (56 + 1003, "A")]


def test_alert_that_fails_while_on_screen_gives_the_screen_back(tmp_path):
    sim = Sim(tmp_path, rotation("a"), alert("x"))
    sim.plan(x=lambda t: "X" if 50 <= t < 100 else ("fail" if t >= 100 else "nothing"))
    sim.run(until=150)
    assert sim.writes == [(1, "A"), (56, "X"), (100, "A")]


def test_rotation_plugin_that_reports_alert_is_shown_in_its_turn(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"))
    sim.plan(b="alert:B")
    sim.run(until=250)
    assert sim.writes == [(1, "A"), (101, "alert:B"), (201, "A")]


def test_alert_ends_when_the_plugin_has_nothing(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), alert("x"))
    sim.plan(x=between(150, 180, "X"))
    sim.run(until=300)
    assert sim.shown == ["A", "B", "X", "A", "B"]


# Failures


def test_failing_plugin_is_skipped_and_left_out_after_three_failures(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=60), rotation("b", refresh=60))
    sim.plan(a="fail")
    sim.run(until=2000)
    left_out = limits.LEFT_OUT
    # Fails at 1, 62 and 123; then left out until 123 + 30 minutes.
    assert sim.updates.times("a") == [1, 62, 123, 123 + left_out + 1]
    assert set(sim.shown) == {"B"}


def test_one_good_update_resets_the_failure_count(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=60), rotation("b", refresh=60))
    outcomes = iter(["fail", "fail", "A", "fail", "fail", "A"])
    sim.plan(a=lambda t: next(outcomes, "A"))
    sim.run(until=600)
    assert sim.updates.times("a") == [1, 62, 123, 184, 245, 306, 367, 428, 489, 550]


def test_failure_of_the_plugin_on_screen_moves_on(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=1000), rotation("b"))
    sim.plan(a=lambda t: "A" if t < 30 else "fail")
    sim.run(until=100)
    assert sim.writes == [(1, "A"), (32, "B")]


def test_default_is_shown_when_every_plugin_fails(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), interrupt("m"))
    sim.plan(a="fail", b="fail", m="nothing")
    sim.run(until=100)
    assert sim.shown == ["default 2/3"]


def test_default_is_updated_when_the_count_changes_and_left_when_one_works(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=60), rotation("b", refresh=60))
    sim.plan(a="fail", b=lambda t: "fail" if t < 100 else "B")
    sim.run(until=200)
    assert sim.shown == ["default 2/2", "B"]


def test_default_is_only_updated_when_the_count_changes(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=60), rotation("b", refresh=60))
    sim.plan(a="fail", b=lambda t: "fail" if t < 100 else "nothing")
    sim.run(until=1000)
    # 2 of 2 failing, then 1 of 2 once b works (but has nothing to show).
    assert sim.shown == ["default 2/2", "default 1/2"]
    assert len(sim.updates.times("built-in-default")) == 2


def test_default_block_in_the_config_is_used_and_not_rotated(tmp_path):
    sim = Sim(tmp_path, rotation("a"), 'name = "fallback"\ntype = "default"')
    sim.plan(a=lambda t: "A" if t < 50 else "fail")
    sim.run(until=200)
    assert sim.shown == ["A", "default 1/1"]
    assert sim.updates.times("fallback") == [64]
    assert sim.updates.times("built-in-default") == []


def test_screen_keeps_its_picture_when_default_fails(tmp_path, caplog):
    sim = Sim(tmp_path, rotation("a"))
    sim.plan(a=lambda t: "A" if t < 50 else "fail")
    sim.updates.default_fails = True
    sim.run(until=200)
    assert sim.shown == ["A"]
    assert "the default plugin failed" in caplog.text


def test_default_says_when_no_plugin_is_switched_on(tmp_path):
    sim = Sim(tmp_path, rotation("a") + "\nenabled = false")
    sim.run(until=100)
    assert sim.shown == ["default 0/0"]


def clock_labels(t):
    """A plan for the fallback clock: a new picture every minute."""
    return f"clock {int(t // 60)}"


def test_fallback_clock_when_nothing_has_anything_to_show(tmp_path):
    sim = Sim(tmp_path, interrupt("m"))
    sim.plan(m="nothing", **{"built-in-clock": clock_labels})
    sim.run(until=200)
    # Started once m has reported (t=1); then 1 s after each minute (10:01:01, 10:02:01).
    assert sim.writes == [(2, "clock 0"), (62, "clock 1"), (122, "clock 2"), (182, "clock 3")]


def test_fallback_clock_after_an_alert_ends(tmp_path):
    sim = Sim(tmp_path, interrupt("m"), alert("x"))
    sim.plan(m="nothing", x=between(50, 100, "X"), **{"built-in-clock": clock_labels})
    sim.run(until=150)
    # The clock's picture from t=2 is out of date by then: it waits for a new one.
    assert sim.writes == [(2, "clock 0"), (56, "X"), (101, "clock 1"), (122, "clock 2")]


def test_fallback_clock_waits_until_every_plugin_has_reported(tmp_path):
    sim = Sim(tmp_path, interrupt("m"), rotation("slow"))
    sim.clock.duration = lambda context: 10.0 if context.storage.name == "slow" else 1.0
    sim.plan(m="nothing")
    sim.run(until=50)
    assert sim.writes == [(10, "SLOW")]


def test_screen_keeps_its_picture_when_the_fallback_clock_is_off(tmp_path):
    sim = Sim(tmp_path, interrupt("m"), alert("x"), display="fallback_clock = false")
    sim.plan(m="nothing", x=between(50, 100, "X"))
    sim.run(until=1000)
    assert sim.writes == [(56, "X")]


def test_rotation_goes_on_with_the_next_plugin_after_the_fallback_clock(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    gap = between(50, 200, "nothing", outside="")  # nothing to show from 50 to 200
    sim.plan(a=lambda t: gap(t) or "A", b=lambda t: gap(t) or "B", c=lambda t: gap(t) or "C")
    sim.plan(**{"built-in-clock": clock_labels})
    sim.run(until=300)
    # a was shown last, so b is next, not the first plugin again.
    assert sim.shown == ["A", "clock 1", "clock 2", "clock 3", "B"]


def test_failed_screen_write_is_tried_again_at_the_next_update_and_logged_once(tmp_path, caplog):
    sim = Sim(tmp_path, rotation("a", refresh=30))
    sim.plan(a=lambda t: "A1" if t < 50 else "A2")
    sim.screen.fail = True
    sim.run(until=100)
    # Tried at every update of the plugin on screen, not again and again in between.
    assert sim.writes == [(1, "A1"), (32, "A1"), (63, "A2"), (94, "A2")]
    assert caplog.text.count("screen write failed") == 1
    sim.screen.fail = False
    sim.run(until=130)
    assert sim.writes[-1] == (125, "A2")
    assert "screen writes work again, after 4 failed" in caplog.text


def test_update_that_comes_due_during_a_slow_screen_write_starts_right_after_it(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=30))
    # Each write takes 40 s: from 1 to 41 (a is due at 31), and from 42 to 82 (due at 72).
    sim.screen.write_seconds = 40
    sim.plan(a=lambda t: f"A{t:g}")
    sim.run(until=100)
    assert sim.updates.times("a")[:3] == [1, 42, 83]


# On the minute


def test_on_the_minute_plugin_updates_just_after_the_minute_changes(tmp_path):
    sim = Sim(tmp_path, 'name = "clock"\ntype = "basic_clock"\nlevel = "rotation"')
    sim.clock.start = datetime(2026, 10, 5, 10, 0, 20)
    sim.run(until=200)
    # Started at 10:00:20; then at 10:01:01, 10:02:01 and 10:03:01 (each takes 1 s).
    assert sim.updates.times("clock") == [1, 42, 102, 162]


# Config reload


def test_reload_keeps_unchanged_plugins_and_redraws_a_changed_one(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=1000), rotation("b"))
    sim.run(until=50)
    changed = rotation("a", display_time=1000) + '\ntext = "new"'
    sim.next_config = make_config(changed, rotation("b"))
    sim.plan(a="A new")
    sim.scheduler.reload()
    sim.run(until=100)
    assert sim.writes == [(1, "A"), (51, "A new")]
    # b goes on with its own timer, as if nothing happened (a new b would update at 51).
    assert sim.updates.times("b") == [1, 32, 63, 94]


def test_reload_during_an_update_waits_for_it(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=100))
    sim.clock.duration = lambda context: 10.0
    sim.at(5, sim.scheduler.reload)
    sim.next_config = make_config(rotation("a", refresh=100) + '\ntext = "new"')
    sim.run(until=30)
    # The new version starts when the old update has finished, never both at once.
    assert sim.updates.times("a") == [10, 20]


def test_reload_keeps_a_dismissed_alert_dismissed(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=10_000), alert("x"))
    sim.plan(x=between(50, 10_000, "X"))
    sim.at(100, sim.scheduler.dismiss, "x")
    sim.run(until=150)
    sim.next_config = make_config(rotation("a", display_time=10_000), alert("x", refresh=20))
    sim.scheduler.reload()
    sim.run(until=1000)
    assert sim.shown == ["A", "X", "A"]


def test_reload_removing_the_plugin_on_screen_moves_on_to_the_next(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.run(until=150)  # b is on screen since 101
    sim.next_config = make_config(rotation("a"), rotation("c"))
    sim.scheduler.reload()
    sim.run(until=200)
    assert sim.writes == [(1, "A"), (101, "B"), (150, "C")]


def test_reload_adds_a_new_plugin(tmp_path):
    sim = Sim(tmp_path, rotation("a"))
    sim.run(until=50)
    sim.next_config = make_config(rotation("a"), rotation("b"))
    sim.scheduler.reload()
    sim.run(until=200)
    assert sim.shown == ["A", "B"]


@pytest.mark.parametrize("broken", ["error", "last good copy"])
def test_broken_config_on_reload_keeps_the_old_settings(tmp_path, broken):
    sim = Sim(tmp_path, rotation("a"), rotation("b"))
    sim.run(until=50)
    if broken == "error":
        sim.next_config = config.ConfigError([config.Problem("error", "not valid TOML")])
    else:
        # What config.load gives for a broken file when a last good copy exists.
        sim.next_config = make_config(rotation("z"))
        sim.next_config.from_last_good = True
    sim.scheduler.reload()
    sim.run(until=250)
    assert sim.shown == ["A", "B", "A"]


def test_screen_settings_take_effect_at_the_next_start(tmp_path, caplog):
    sim = Sim(tmp_path, rotation("a"))
    sim.run(until=10)
    sim.next_config = make_config(rotation("a"), display="rotation = 180")
    sim.scheduler.reload()
    sim.run(until=200)
    assert "screen settings take effect at the next start" in caplog.text
    assert sim.screen.sizes == [SIZE]


# The screen


def test_rotated_screen_gets_a_turned_picture(tmp_path):
    sim = Sim(tmp_path, rotation("a"), display="rotation = 90")
    sim.run(until=10)
    assert sim.screen.sizes == [(SIZE[1], SIZE[0])]


def test_very_long_waits_are_cut_short():
    import queue

    from paperpi.scheduler import Clock

    events = queue.SimpleQueue()
    events.put("event")
    assert Clock().wait(events, 1e300) == "event"  # no OverflowError
    assert Clock().wait(events, 0.01) is None


def test_at_most_three_updates_run_at_once(tmp_path):
    scheduler = Scheduler(make_config(rotation("a")), FakeScreen(None, None), state_dir=tmp_path)
    try:
        assert scheduler.executor._max_workers == limits.PARALLEL_UPDATES == 3
    finally:
        scheduler.executor.shutdown()


# With the real parts: plugin processes, the worker pool, the virtual screen


def run_in_thread(scheduler):
    import threading

    thread = threading.Thread(target=scheduler.run)
    thread.start()
    return thread


def test_real_run_with_debugging_plugins(tmp_path):
    import time

    from epdlib import ScreenMode
    from epdlib.drivers.virtual import VirtualDriver

    loaded = make_config(
        rotation("one", display_time=1, refresh=5) + '\ntext = "one"',
        rotation("two", display_time=1, refresh=5) + '\ntext = "two"\ncrash_every = 2',
    )
    screen = VirtualDriver(*SIZE, ScreenMode.gray(16), tmp_path / "screen")
    scheduler = Scheduler(loaded, screen, state_dir=tmp_path)
    with screen:
        thread = run_in_thread(scheduler)
        deadline = time.monotonic() + 30
        while screen.count < 3 and time.monotonic() < deadline:
            time.sleep(0.1)
        scheduler.stop()
        thread.join(30)
    assert not thread.is_alive()
    assert screen.count >= 3  # took turns
    assert (tmp_path / "plugins" / "one" / "count").is_file()
    assert (tmp_path / "plugins" / "two" / "count").is_file()
    assert (tmp_path / "screen" / "latest.png").is_file()


def test_stop_ends_a_hanging_update_at_once(tmp_path):
    import time

    from epdlib import ScreenMode
    from epdlib.drivers.virtual import VirtualDriver

    block = rotation("hang", refresh=100) + "\nhang_every = 1\ntime_limit = 300"
    screen = VirtualDriver(*SIZE, ScreenMode.gray(16), tmp_path / "screen")
    scheduler = Scheduler(make_config(block), screen, state_dir=tmp_path)
    with screen:
        thread = run_in_thread(scheduler)
        count = tmp_path / "plugins" / "hang" / "count"
        deadline = time.monotonic() + 30
        while not count.exists() and time.monotonic() < deadline:
            time.sleep(0.1)  # the update has started, and hangs
        start = time.monotonic()
        scheduler.stop()
        thread.join(30)
    assert not thread.is_alive()
    assert time.monotonic() - start < 10
