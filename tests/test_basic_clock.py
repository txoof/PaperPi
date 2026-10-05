"""The basic_clock plugin's own logic."""

from datetime import datetime
from pathlib import Path

import pytest
from epdlib import ScreenMode

from paperpi.plugin import Context
from paperpi.plugins.basic_clock import PLUGIN, Settings, draw, format_date, format_time


@pytest.mark.parametrize(
    ("hour", "minute", "hours", "text"),
    [
        (0, 5, 12, "12:05 AM"),
        (12, 0, 12, "12:00 PM"),
        (13, 7, 12, "1:07 PM"),
        (23, 59, 12, "11:59 PM"),
        (0, 5, 24, "00:05"),
        (13, 7, 24, "13:07"),
    ],
)
def test_format_time(hour, minute, hours, text):
    assert format_time(datetime(2026, 10, 5, hour, minute), hours) == text


def test_format_date():
    assert format_date(datetime(2026, 9, 30)) == "Wednesday 30 September"


@pytest.mark.parametrize(
    ("layout", "blocks"), [("time", {"time"}), ("time_date", {"time", "date"})]
)
def test_draw_fills_the_blocks_of_the_layout(layout, blocks):
    context = Context(Settings(), 100, 100, ScreenMode.bw(), Path("."), layout)
    assert set(draw(datetime(2026, 10, 5, 10, 42), context)) == blocks


def test_clock_refreshes_on_the_minute():
    assert PLUGIN.refresh == 60
    assert PLUGIN.refresh_on_minute
