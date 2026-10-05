"""The word_clock plugin's own logic."""

import functools
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from epdlib import ScreenMode
from PIL import ImageFont

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
from paperpi.plugins.word_clock.layouts import FONT, WIDEST


def at(hour, minute):
    return datetime(2026, 10, 5, hour, minute)


def context(layout="words_time", mode=None, **settings):
    return Context(Settings(**settings), 400, 300, mode or ScreenMode.gray(16), Path("."), layout)


@pytest.mark.parametrize(
    ("time", "step"),
    [
        ((20, 21), (20, 20)),
        ((20, 24), (20, 20)),
        ((20, 25), (20, 30)),
        ((23, 55), (0, 0)),
        ((20, 34), (20, 30)),
        ((20, 35), (20, 40)),
    ],
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
    for day in range(1, 29):
        for hour in range(24):
            text = sentence(datetime(2026, 2, day, hour, 21))
            assert not any(text.startswith(o) for o in words.BEFORE), text


@pytest.mark.parametrize(
    ("time", "hour"),
    [
        ((20, 21), 20),
        ((20, 34), 20),
        ((20, 35), 21),
        ((23, 35), 0),
        ((23, 50), 0),
        ((11, 57), 12),
        ((0, 2), 0),
    ],
)
def test_names_the_right_hour(time, hour):
    """From :35 on, the sentence counts to the next hour ("Ten 'Til Nine")."""
    names = "|".join(re.escape(w.title()) for w in words.HOURS[hour])
    for day in range(1, 29):
        text = sentence(datetime(2026, 2, day, *time))
        # The hour words end the sentence, or come just before the full-hour words.
        full_hour = "|".join(re.escape(w.title()) for w in words.MINUTES[0])
        assert re.search(rf" ({names})( ({full_hour}))?$", text), text


def test_full_hour_puts_the_hour_first():
    text = sentence(at(8, 0))
    assert any(text.endswith(f" {w.title()}") for w in words.MINUTES[0]), text


def test_all_sentences():
    found = all_sentences()
    assert len(found) == 7140
    assert max(map(len, found)) == 46
    assert not any("Why Aren't You In Bed" in s for s in found)
    assert "It's nearly Ten 'Til Bedtime" in found
    assert "Give or take, it's Breakfast Sharp" in found


def split_opening(text):
    """(opening, time words) of a sentence."""
    for opening in sorted(words.ALWAYS + words.BEFORE + words.AFTER, key=len, reverse=True):
        if text.startswith(opening + " "):
            return opening, text[len(opening) + 1 :]
    raise AssertionError(text)


def test_words_stay_within_a_step_unless_the_truth_changes():
    """Within a step the time words never change, and the opening changes only where the
    truth does: once before the step, once on it, once after it."""
    for hour in range(24):
        for step in range(0, 60, 10):
            centre = datetime(2026, 10, 5, hour, step)
            texts = [sentence(centre + timedelta(minutes=m)) for m in range(-5, 5)]
            parts = [split_opening(t) for t in texts]
            assert len({time for _, time in parts}) == 1, texts
            assert len({o for o, _ in parts[:5]}) == 1 and len({o for o, _ in parts[6:]}) == 1


def test_words_vary_between_steps():
    over_a_day = {sentence(at(h, 20)).split(" Twenty")[0] for h in range(24)}
    assert len(over_a_day) > 3


@functools.cache
def by_width() -> list[str]:
    """All sentences, narrowest first. Pillow's basic text layout (the one epdlib uses)
    doesn't move letters closer together, so a sentence's width is the sum of its letters'
    widths: much quicker than measuring all 7140 sentences."""
    font = ImageFont.truetype(FONT, 100, layout_engine=ImageFont.Layout.BASIC)
    width = functools.cache(font.getlength)
    return sorted(sorted(all_sentences()), key=lambda s: sum(width(c) for c in s))


def test_widest_is_still_the_widest():
    assert by_width()[-1] == WIDEST


@pytest.mark.parametrize("screen", [(1200, 825), (600, 448), (480, 800)])
@pytest.mark.parametrize("layout", ["words_time", "words"])
def test_every_sentence_fits(screen, layout):
    """No sentence is cut off with "…". The widest 40 are checked (each check takes about
    0.1 s on a Pi); the others are narrower."""
    from epdlib import Layout, text

    prepared = Layout(PLUGIN.layouts[layout](Settings())).prepare(*screen, ScreenMode.gray(16))
    block = prepared.layout.blocks["words"]
    inner = prepared._inner(block)
    widest = by_width()[-40:]
    o = block.options
    for sentence_ in widest:
        fit = text.fit_text(
            o["font"],
            prepared.font_sizes["words"],
            sentence_,
            inner.width,
            inner.height,
            o["max_lines"],
            o["shrink"],
            o["ellipsis"],
        )
        assert "…" not in "".join(fit.lines), sentence_


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
