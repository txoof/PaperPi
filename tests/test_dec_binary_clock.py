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


def test_picture_shows_every_dot_ring_and_the_bar():
    # 760x690 is v1's size: 10 pixels per unit. Columns start at 0, 180, 400 and 580 (the
    # bar, 40 wide, sits between the 2nd and 3rd); a dot's centre is 90 pixels in.
    image = picture(14, 49, 760, 690)
    for column, (left, bits) in enumerate(
        zip((0, 180, 400, 580), time_columns(14, 49), strict=True)
    ):
        for row, on in enumerate(bits):
            centre = (left + 90, 90 + 170 * row)
            assert image.getpixel(centre) == (0 if on else 255), (column, row)
    assert image.getpixel((195, 90)) == 0  # ring of the "off" top dot of column 2 (the 4)
    assert image.getpixel((380, 300)) == 0  # the bar
    assert image.getpixel((370, 0)) == 0  # the bar reaches the top, as in v1


def test_draw_fills_the_blocks_of_the_layout():
    values = draw(PLUGIN.sample, context()).values
    assert set(values) == {"dots", "time"}
    assert values["time"] == "14:49"


@pytest.mark.parametrize(
    ("size", "mode"),
    [
        ((800, 480), ScreenMode.bw()),
        ((1200, 825), ScreenMode.gray(16)),
        ((600, 448), ScreenMode.palette()),
        ((250, 122), ScreenMode.bw()),
        ((480, 800), ScreenMode.bw()),
    ],
)
def test_screen_shows_the_dots_unscaled(size, mode):
    # The dots area of the finished screen image is exactly the picture from draw: epdlib
    # did not scale it (that would happen if the dots block got padding or a border).
    ctx = context(*size, mode)
    box = PLUGIN.layout("dots_time", Settings()).prepare(*size, mode).boxes["dots"]
    dots = draw(PLUGIN.sample, ctx).values["dots"]
    screen = draw_update(PLUGIN, ctx, sample=True)[1].convert("L")
    cut = screen.crop((box.x, box.y, box.x + box.width, box.y + box.height))
    assert cut.tobytes() == dots.tobytes()


def test_same_minute_same_picture_next_minute_new_seed():
    def image(minute):
        plugin = replace(PLUGIN, sample=datetime(2026, 10, 5, 14, minute))
        return draw_update(plugin, context(), sample=True)[1].tobytes()

    assert image(49) == image(49)
    # The seed picks the place of the time text, so a new minute gives it a new place.
    seeds = {draw(datetime(2026, 10, 5, 14, m), context()).seed for m in (49, 50)}
    assert len(seeds) == 2


def test_clock_refreshes_on_the_minute():
    assert PLUGIN.refresh == 60
    assert PLUGIN.refresh_on_minute
