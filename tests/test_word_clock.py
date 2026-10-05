"""The word_clock plugin's own logic."""

import random
from datetime import datetime
from pathlib import Path

import pytest
from epdlib import ScreenMode

from paperpi.plugin import Context, draw_update
from paperpi.plugins.word_clock import (
    PLUGIN,
    Settings,
    all_sentences,
    draw,
    openings,
    sentence,
    step_of,
    words,
)


def at(hour, minute):
    return datetime(2026, 10, 5, hour, minute)


def context(layout="words_time", mode=None, **settings):
    return Context(Settings(**settings), 400, 300, mode or ScreenMode.gray(16), Path("."), layout)


@pytest.mark.parametrize(
    ("time", "step"),
    [((20, 21), (20, 20)), ((20, 24), (20, 20)), ((20, 25), (20, 30)), ((23, 55), (0, 0))],
)
def test_step_rounds_to_ten_minutes(time, step):
    rounded = step_of(at(*time))
    assert (rounded.hour, rounded.minute) == step


def test_openings_fit_the_time():
    # 20:18 is before twenty after, 20:22 after it, 20:20 exactly on it.
    assert set(openings(at(20, 18))) == set(words.ALWAYS + words.BEFORE)
    assert set(openings(at(20, 22))) == set(words.ALWAYS + words.AFTER)
    assert set(openings(at(20, 20))) == set(words.ALWAYS)


def test_never_nearly_when_already_past():
    for seed in range(200):
        text = sentence(at(20, 21), random.Random(seed))
        assert not any(text.startswith(o) for o in words.BEFORE), text


@pytest.mark.parametrize(
    ("time", "hour"),
    [((20, 21), 20), ((20, 38), 21), ((23, 50), 0), ((11, 57), 12), ((0, 2), 0)],
)
def test_names_the_right_hour(time, hour):
    """From :35 on, the sentence counts to the next hour ("Ten 'Til Nine")."""
    for seed in range(50):
        text = sentence(at(*time), random.Random(seed))
        assert any(w.title() in text for w in words.HOURS[hour]), text


def test_full_hour_puts_the_hour_first():
    text = sentence(at(8, 0), random.Random(1))
    assert any(text.endswith(f" {w.title()}") for w in words.MINUTES[0]), text


def test_all_sentences():
    found = all_sentences()
    assert len(found) == 7140
    assert max(map(len, found)) == 46
    assert not any("Why Aren't You In Bed" in s for s in found)
    assert "It's nearly Ten 'Til Bedtime" in found
    assert "Give or take, it's Breakfast Sharp" in found


def test_words_vary_per_step_but_stay_within_a_step():
    before = {draw(at(20, m), context()).values["words"] for m in range(15, 20)}
    assert len(before) == 1  # 20:15-20:19 are one step, with the same words
    over_a_day = {draw(at(h, 20), context()).values["words"].split(" Twenty")[0] for h in range(24)}
    assert len(over_a_day) > 3  # different openings at different times


def test_same_minute_same_picture_next_minute_moves(tmp_path):
    def picture(minute):
        plugin = PLUGIN
        ctx = Context(Settings(), 400, 300, ScreenMode.gray(16), tmp_path, "words")
        drawn = plugin.draw(at(20, minute), ctx)
        layout = plugin.layout("words", ctx.settings, drawn.colors).prepare(400, 300, ctx.mode)
        return drawn.values["words"], layout.render(dict(drawn.values), seed=drawn.seed)

    words_a, one = picture(16)
    _, again = picture(16)
    words_b, other = picture(17)
    assert one.tobytes() == again.tobytes()
    assert words_a == words_b  # same step, same words
    assert one.tobytes() != other.tobytes()  # but the text has moved


def test_time_only_in_words_time():
    assert draw(at(20, 21), context()).values["time"] == "20:21"
    assert "time" not in draw(at(20, 21), context("words")).values


def test_colours():
    drawn = draw(
        at(20, 21), context(mode=ScreenMode.rgb(), text_color="yellow", background_color="blue")
    )
    assert drawn.colors == ("yellow", "blue")
    # On a gray screen yellow is white and blue is black.
    drawn = draw(at(20, 21), context(text_color="yellow", background_color="blue"))
    assert drawn.colors == ("white", "black")


def test_random_colours_change_per_step():
    def colors(hour, minute):
        return draw(
            at(hour, minute),
            context(mode=ScreenMode.palette(), text_color="random", background_color="random"),
        ).colors

    assert colors(20, 16) == colors(20, 24)
    assert len({colors(h, 0) for h in range(24)}) > 3


def test_draws_on_a_black_background(tmp_path):
    ctx = Context(Settings(), 400, 300, ScreenMode.bw(), tmp_path, "words_time")
    _, image = draw_update(PLUGIN, ctx, sample=True)
    histogram = image.convert("L").histogram()
    assert histogram[0] > histogram[255]  # mostly black, as v1


def test_refreshes_on_the_minute():
    assert PLUGIN.refresh_on_minute
