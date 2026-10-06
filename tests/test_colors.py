"""Text and background colours (paperpi.colors)."""

import logging
import random

import pytest
from epdlib import ScreenMode
from PIL import ImageColor

from paperpi.colors import COLORS, FALLBACK, READABLE, screen_colors

GRAY = ScreenMode.gray(16)
COLOUR = ScreenMode.palette()


def test_colour_screens_keep_the_colours():
    assert screen_colors("red", "yellow", COLOUR, random.Random(0)) == ("red", "yellow")


@pytest.mark.parametrize(
    ("text", "background", "shown"),
    [("yellow", "blue", ("white", "black")), ("black", "orange", ("black", "white"))],
)
def test_gray_screens_get_black_or_white(text, background, shown):
    assert screen_colors(text, background, GRAY, random.Random(0)) == shown
    assert screen_colors(text, background, ScreenMode.bw(), random.Random(0)) == shown


def test_same_shade_falls_back_to_white_on_black(caplog):
    with caplog.at_level(logging.WARNING):
        assert screen_colors("yellow", "white", GRAY, random.Random(0)) == FALLBACK
    assert "look the same" in caplog.text


@pytest.mark.parametrize("mode", [GRAY, COLOUR])
@pytest.mark.parametrize(
    ("text", "background"), [("random", "random"), ("random", "white"), ("black", "random")]
)
def test_random_is_always_readable(mode, text, background, caplog):
    for seed in range(100):
        shown = screen_colors(text, background, mode, random.Random(seed))
        assert shown[0] != shown[1]
        assert all(c in COLORS for c in shown)
    assert "look the same" not in caplog.text


@pytest.mark.parametrize("fixed", COLORS)
def test_random_pairs_are_easy_to_read(fixed):
    def brightness(c):
        return ImageColor.getcolor(c, "L")

    seen = set()
    for seed in range(200):
        pair = screen_colors("random", "random", COLOUR, random.Random(seed))
        one = screen_colors(fixed, "random", COLOUR, random.Random(seed))
        for text, background in (pair, one):
            assert abs(brightness(text) - brightness(background)) >= READABLE
        seen.add(pair)
    assert ("white", "yellow") not in seen and ("yellow", "orange") not in seen
    assert len(seen) > 8  # still plenty of different pairs


def test_random_is_repeatable():
    first = screen_colors("random", "random", COLOUR, random.Random(42))
    assert screen_colors("random", "random", COLOUR, random.Random(42)) == first
