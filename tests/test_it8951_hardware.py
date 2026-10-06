"""The real IT8951 screen through PaperPi's screen helper process. Needs the screen attached.

Run on the Pi with the vcom printed on the screen's ribbon cable:

    PAPERPI_VCOM=-1.90 uv run pytest -m hardware tests/test_it8951_hardware.py

The screen flashes white, shows a black square that moves twice (fast writes), and is
cleared at the end.
"""

import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from paperpi import config
from paperpi.screen import Screen, driver_for

pytestmark = pytest.mark.hardware


def page(x: int) -> Image.Image:
    image = Image.new("L", (1200, 825), 255)
    ImageDraw.Draw(image).rectangle((x, 300, x + 199, 499), fill=0)
    return image


def test_write_fast_writes_and_clear_on_the_real_screen():
    vcom = os.environ.get("PAPERPI_VCOM")
    if vcom is None:
        pytest.skip("set PAPERPI_VCOM to the value on the screen's ribbon cable")
    text = f'config_version = 1\n[display]\ntype = "it8951"\nmodel = "9.7"\nvcom = {vcom}\n'
    display = config.parse(text).display
    with Screen(driver_for(display, Path("unused"))) as screen:
        screen.check()
        screen.clear()
        screen.write(page(100))
        full = screen.redraw
        screen.write(page(400), fast=True)  # after sleep: woken without a reset
        screen.write(page(700), fast=True)
        fast = screen.redraw
        screen.clear()
    assert fast < full, (fast, full)  # only the changed area was sent
