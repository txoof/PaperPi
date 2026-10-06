"""The dec_binary_clock plugin's own logic."""

from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from epdlib import ScreenMode

from paperpi.plugin import Context, draw_update
from paperpi.plugins.dec_binary_clock import PLUGIN, Settings, draw
from paperpi.plugins.dec_binary_clock.dots import digit_bits, picture, time_columns


def context(width=800, height=480, mode=None):
    return Context(Settings(), width, height, mode or ScreenMode.bw(), Path("."), "dots_time")


@pytest.mark.parametrize(
    ("digit", "bits"),
    [
        (0, (False, False, False, False)),
        (1, (False, False, False, True)),
        (4, (False, True, False, False)),
        (9, (True, False, False, True)),
    ],
)
def test_digit_bits_top_is_worth_8(digit, bits):
    assert digit_bits(digit) == bits


def test_every_digit_reads_back():
    for digit in range(10):
        assert sum(v for v, on in zip((8, 4, 2, 1), digit_bits(digit), strict=True) if on) == digit


@pytest.mark.parametrize("digit", [-1, 10])
def test_digit_bits_refuses_more_than_one_digit(digit):
    with pytest.raises(ValueError):
        digit_bits(digit)


def test_time_columns_are_the_four_digits():
    # 14:49 -> 1, 4, 4, 9 (the example in v1's help text)
    assert time_columns(14, 49) == [digit_bits(d) for d in (1, 4, 4, 9)]
    # Single-digit hours and minutes get a leading 0.
    assert time_columns(7, 5) == [digit_bits(d) for d in (0, 7, 0, 5)]


@pytest.mark.parametrize("size", [(760, 690), (1200, 733), (250, 100), (3, 2)])
def test_picture_has_the_size_asked_for(size):
    assert picture(23, 59, *size).size == size


def test_picture_is_only_black_and_white():
    # No gray edges, so nothing turns into dots on black-and-white screens.
    colors = {value for _, value in picture(14, 49, 800, 420).getcolors()}
    assert colors == {0, 255}


def test_filled_dot_is_black_in_the_middle_and_ring_is_white():
    # 01:00: only the lowest dot of the second column is on.
    image = picture(1, 0, 760, 690)  # 10 pixels per unit, v1's size
    # Middle of the second column's dots: x = 18 units + 9, y = 1 + 8 (+17 per row).
    middle = [(270, 90 + 170 * row) for row in range(4)]
    assert [image.getpixel(p) for p in middle] == [255, 255, 255, 0]


def test_draw_makes_the_dots_exactly_the_size_of_their_block():
    values = draw(PLUGIN.sample, context()).values
    assert values["time"] == "14:49"
    prepared = PLUGIN.layout("dots_time", Settings()).prepare(800, 480, ScreenMode.bw())
    assert values["dots"].size == prepared.boxes["dots"].size


def test_same_minute_same_picture_next_minute_the_time_moves():
    def image(minute):
        plugin = replace(PLUGIN, sample=datetime(2026, 10, 5, 14, minute))
        return draw_update(plugin, context(), sample=True)[1].tobytes()

    assert image(49) == image(49)
    # The time text is the only thing that moves; 14:50 also has other dots, so compare
    # the seeds that place the text.
    seeds = {draw(datetime(2026, 10, 5, 14, m), context()).seed for m in (49, 50)}
    assert len(seeds) == 2


def test_clock_refreshes_on_the_minute():
    assert PLUGIN.refresh == 60
    assert PLUGIN.refresh_on_minute
