"""Show now, Skip to next, Refresh, Try again now and the summary of the scheduler
(paperpi.scheduler), run with the fake clock of ``test_scheduler``."""

from datetime import timedelta

from paperpi import limits
from paperpi.screen import ScreenResting

from .test_scheduler import Sim, alert, between, interrupt, make_config, rotation


def at_seconds(sim, seconds):
    return sim.clock.start + timedelta(seconds=seconds)


# Show now


def test_show_now_is_an_extra_turn_and_the_order_goes_on_as_planned(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.at(50, sim.scheduler.show_now, "c")
    sim.run(until=400)
    # A's turn is cut short; B was next and is still next.
    assert sim.writes == [(1, "A"), (50, "C"), (150, "B"), (250, "C"), (350, "A")]


def test_show_now_of_the_next_plugin_does_not_give_it_two_turns_in_a_row(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.at(50, sim.scheduler.show_now, "b")
    sim.run(until=300)
    assert sim.writes == [(1, "A"), (50, "B"), (150, "C"), (250, "A")]


def test_show_now_wins_over_an_alert_which_then_comes_back(tmp_path):
    sim = Sim(tmp_path, alert("x"), rotation("a", refresh=1000))
    sim.plan(x=between(0, 1000, "X"))
    sim.at(100, sim.scheduler.show_now, "a")
    sim.run(until=300)
    assert sim.writes == [(1, "X"), (100, "A"), (200, "X")]


def test_show_now_wins_over_an_interrupt(tmp_path):
    sim = Sim(tmp_path, interrupt("m"), rotation("a", refresh=1000))
    sim.plan(m="M")
    sim.at(100, sim.scheduler.show_now, "a")
    sim.run(until=300)
    assert sim.writes == [(1, "M"), (100, "A"), (200, "M")]


def test_show_now_without_a_picture_updates_first(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=1000), rotation("b", refresh=1000))
    sim.plan(b=lambda t: "fail" if t < 10 else "B")
    sim.at(50, sim.scheduler.show_now, "b")
    sim.run(until=200)
    assert sim.updates.times("b") == [1, 51]
    assert sim.writes == [(1, "A"), (51, "B"), (151, "A")]


def test_show_now_of_a_paused_plugin_updates_it_at_once(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=1000), rotation("b", refresh=5))
    sim.plan(b=lambda t: "fail" if t < 20 else "B")
    sim.at(100, sim.scheduler.show_now, "b")
    sim.run(until=150)
    # Failed 3 times (left out for LEFT_OUT seconds), then updated at once.
    assert sim.updates.times("b")[:4] == [1, 7, 13, 101]
    assert sim.writes == [(1, "A"), (101, "B")]


def test_show_now_that_fails_changes_nothing_and_shows_the_error(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=1000), rotation("b", refresh=1000))
    sim.plan(b="fail")
    sim.at(50, sim.scheduler.show_now, "b")
    sim.run(until=300)
    assert sim.updates.times("b") == [1, 51]
    assert sim.writes == [(1, "A")]
    b = sim.scheduler.summary.plugins[1]
    assert b.status == "waiting" and "fake failure" in b.error


def test_show_now_of_an_interrupt_with_nothing_changes_nothing(tmp_path):
    sim = Sim(tmp_path, interrupt("m", refresh=1000), rotation("a", refresh=1000))
    sim.plan(m="nothing")
    sim.at(50, sim.scheduler.show_now, "m")
    sim.run(until=300)
    assert sim.updates.times("m") == [1, 51]
    assert sim.writes == [(1, "A")]


def test_show_now_of_a_plugin_that_is_off_does_nothing(tmp_path, caplog):
    sim = Sim(tmp_path, rotation("a"), rotation("b") + "\nenabled = false")
    sim.at(50, sim.scheduler.show_now, "b")
    sim.run(until=150)
    assert sim.writes == [(1, "A")]
    assert "no plugin 'b' is switched on" in caplog.text


def test_show_now_ends_the_splash_screen(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), display="splash_time = 60")
    sim.at(10, sim.scheduler.show_now, "b")
    sim.run(until=150)
    assert sim.shown[:2] == ["BUILT-IN-SPLASH", "B"]
    assert sim.writes[1][0] == 10


def test_show_now_survives_a_reload_that_changes_the_plugin(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"))
    sim.next_config = make_config(rotation("a"), rotation("b", display_time=50))
    sim.at(30, sim.scheduler.show_now, "b")
    sim.at(40, sim.scheduler.reload)
    sim.run(until=200)
    assert sim.writes[:3] == [(1, "A"), (30, "B"), (80, "A")]


# Skip to next


def test_skip_ends_the_turn(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.at(50, sim.scheduler.skip)
    sim.run(until=300)
    assert sim.writes == [(1, "A"), (50, "B"), (150, "C"), (250, "A")]


def test_skip_ends_an_extra_turn_and_the_order_goes_on(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.at(50, sim.scheduler.show_now, "c")
    sim.at(80, sim.scheduler.skip)
    sim.run(until=150)
    assert sim.writes == [(1, "A"), (50, "C"), (80, "B")]


def test_skip_dismisses_an_alert(tmp_path):
    sim = Sim(tmp_path, alert("x", alert_reminder=300), rotation("a", refresh=1000))
    sim.plan(x=between(0, 1000, "X"))
    sim.at(100, sim.scheduler.skip)
    sim.run(until=450)
    assert sim.writes == [(1, "X"), (100, "A"), (400, "X")]


def test_skipped_interrupt_stays_away_until_its_picture_changes(tmp_path):
    sim = Sim(tmp_path, interrupt("m"), rotation("a", refresh=1000))
    sim.plan(m=lambda t: "M1" if t < 300 else "M2")
    sim.at(100, sim.scheduler.skip)
    sim.run(until=400)
    assert sim.shown == ["M1", "A", "M2"]
    assert sim.writes[1][0] == 100 and 300 < sim.writes[2][0] < 310


def test_skipped_interrupt_comes_back_after_it_had_nothing(tmp_path):
    sim = Sim(tmp_path, interrupt("m"), rotation("a", refresh=1000))
    sim.plan(m=lambda t: "nothing" if 200 <= t < 250 else "M")
    sim.at(100, sim.scheduler.skip)
    sim.run(until=400)
    assert sim.shown == ["M", "A", "M"]


def test_skip_ends_the_splash_screen(tmp_path):
    sim = Sim(tmp_path, rotation("a"), display="splash_time = 60")
    sim.at(10, sim.scheduler.skip)
    sim.run(until=50)
    assert sim.shown == ["BUILT-IN-SPLASH", "A"]
    assert sim.writes[1][0] == 10


# Refresh


def test_refresh_updates_and_draws_in_full_after_a_clear(tmp_path):
    sim = Sim(tmp_path, rotation("a", display_time=1000, refresh=300), display="clean_every = 0")
    sim.at(50, sim.scheduler.refresh)
    sim.run(until=100)
    assert sim.updates.times("a") == [1, 51]
    # Written again, although the picture did not change.
    assert sim.writes == [(1, "A"), (51, "A")]
    assert sim.screen.clears == [51]
    assert sim.screen.fast == [False, False]


def test_refresh_that_fails_changes_nothing(tmp_path):
    sim = Sim(
        tmp_path,
        rotation("a", display_time=1000, refresh=300),
        rotation("b", refresh=1000),
        display="clean_every = 0",
    )
    sim.plan(a=lambda t: "fail" if t > 10 else "A")
    sim.at(50, sim.scheduler.refresh)
    sim.run(until=100)
    # A has nothing now, so B takes over, without a clear.
    assert sim.writes == [(1, "A"), (51, "B")]
    assert sim.screen.clears == []


def test_refresh_of_a_built_in_plugin_draws_its_picture_again(tmp_path):
    sim = Sim(tmp_path, display="clean_every = 0")  # no plugins: the splash screen stays
    sim.at(50, sim.scheduler.refresh)
    sim.run(until=100)
    assert sim.writes == [(1, "BUILT-IN-SPLASH"), (50, "BUILT-IN-SPLASH")]
    assert sim.screen.clears == [50]


# Try again now


def test_try_again_updates_a_paused_plugin_at_once(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=1000), rotation("b", refresh=5))
    sim.plan(b=lambda t: "fail" if t < 20 else "B")
    sim.run(until=50)
    assert sim.scheduler.summary.plugins[1].status == "paused"
    assert sim.scheduler.summary.plugins[1].paused_until == at_seconds(sim, 13 + limits.LEFT_OUT)
    sim.at(100, sim.scheduler.try_again, "b")
    sim.run(until=150)
    assert sim.updates.times("b")[:4] == [1, 7, 13, 101]
    assert sim.scheduler.summary.plugins[1].status == "on_screen"  # after A's turn


def test_try_again_tries_a_paused_screen_at_once(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=1000))
    sim.at(0.5, setattr, sim.screen, "fail", ScreenResting("paused", wait=600))
    sim.run(until=50)
    assert sim.scheduler.summary.screen == "paused"
    assert sim.scheduler.summary.screen_retry_at == at_seconds(sim, 601)
    sim.screen.fail = False
    sim.at(60, sim.scheduler.try_again)
    sim.run(until=100)
    assert sim.writes == [(1, "A"), (60, "A")]
    # The screen's own waits start from zero.
    assert sim.screen.changes == [("retry", True)]
    assert sim.scheduler.summary.screen == "ok"


# Summary


def test_summary_tells_what_is_on_screen_and_what_comes_next(tmp_path):
    sim = Sim(
        tmp_path,
        rotation("a", refresh=1000),
        rotation("b", refresh=1000),
        rotation("c", display_time=50, refresh=1000),
        rotation("d") + "\nenabled = false",
        'id = "moon"\ntype = "moon_phase"',
    )
    sim.run(until=50)
    summary = sim.scheduler.summary
    assert summary.on_screen == "a"
    assert summary.since == at_seconds(sim, 1)
    assert sim.labels.label(summary.picture) == "A"
    assert (summary.next, summary.next_at) == ("b", at_seconds(sim, 101))
    assert not summary.extra and not summary.alert
    assert summary.screen == "ok"
    plugins = {p.id: p for p in summary.plugins}
    assert list(plugins) == ["a", "b", "c", "d", "moon"]
    assert [p.status for p in plugins.values()] == [
        "on_screen",
        "next",
        "rotation",
        "off",
        "needs_settings",
    ]
    assert plugins["c"].shows_at == at_seconds(sim, 201)
    assert plugins["b"].drawn_at == at_seconds(sim, 1)
    assert sim.labels.label(plugins["b"].picture) == "B"
    assert plugins["moon"].missing == ("lat", "lon", "email")


def test_summary_of_an_extra_turn(tmp_path):
    sim = Sim(tmp_path, rotation("a"), rotation("b"), rotation("c"))
    sim.at(50, sim.scheduler.show_now, "c")
    sim.run(until=60)
    summary = sim.scheduler.summary
    assert (summary.on_screen, summary.extra) == ("c", True)
    assert (summary.next, summary.next_at) == ("b", at_seconds(sim, 150))


def test_summary_of_an_alert_and_a_dismissed_one(tmp_path):
    sim = Sim(tmp_path, alert("x"), rotation("a", refresh=1000))
    sim.plan(x=between(0, 1000, "X"))
    sim.run(until=50)
    summary = sim.scheduler.summary
    assert (summary.on_screen, summary.alert, summary.next) == ("x", True, None)
    sim.at(60, sim.scheduler.dismiss, "x")
    sim.run(until=100)
    summary = sim.scheduler.summary
    assert (summary.on_screen, summary.alert) == ("a", False)
    assert [p.status for p in summary.plugins] == ["dismissed", "on_screen"]


def test_summary_keeps_the_last_picture_after_a_failure(tmp_path):
    sim = Sim(tmp_path, rotation("a", refresh=1000), rotation("b", refresh=30))
    sim.plan(b=lambda t: "B" if t < 10 else "fail")
    sim.run(until=50)
    b = sim.scheduler.summary.plugins[1]
    assert b.status == "waiting"
    assert sim.labels.label(b.picture) == "B" and b.drawn_at == at_seconds(sim, 1)
    assert "fake failure" in b.error
