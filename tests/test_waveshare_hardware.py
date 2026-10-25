"""A real Waveshare screen through PaperPi's screen helper process. Needs the screen attached.

Run on the Pi, with the model of the screen (default: the 7.5" V2):

    PAPERPI_WAVESHARE_MODEL=epd7in5_V2 uv run pytest -m hardware tests/test_waveshare_hardware.py

The screen is cleared, shows a black square, then (on a model with fast writes) the square
moves twice, and is cleared at the end.
"""

import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from paperpi import config
from paperpi.screen import Screen, driver_for

pytestmark = pytest.mark.hardware


def page(size: tuple[int, int], x: int) -> Image.Image:
    width, height = size
    side = height // 3
    image = Image.new("L", size, 255)
    ImageDraw.Draw(image).rectangle((x, side, x + side - 1, 2 * side - 1), fill=0)
    return image


def test_write_fast_writes_and_clear_on_the_real_screen():
    model = os.environ.get("PAPERPI_WAVESHARE_MODEL", "epd7in5_V2")
    text = f'config_version = 1\n[display]\ntype = "waveshare"\nmodel = "{model}"\n'
    display = config.parse(text).display
    size = display.size
    with Screen(driver_for(display, Path("unused"))) as screen:
        screen.check()
        screen.clear()
        screen.write(page(size, size[0] // 8))
        full = screen.redraw
        if display.model_info.fast_refresh:
            screen.write(page(size, size[0] // 3), fast=True)  # after sleep: woken again
            screen.write(page(size, size[0] // 2), fast=True)
            assert screen.redraw < full, (screen.redraw, full)
        screen.clear()
