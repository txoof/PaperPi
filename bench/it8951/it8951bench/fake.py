"""A fake candidate with no hardware, used by the unit tests of the test tools.

Set FAKE_HANG=1 to make every write after the first hang forever, like v1 did.
"""

import os
import time

from PIL import Image

from .candidate import DeviceInfo, Mode


class Fake:
    name = "fake"

    def __init__(self) -> None:
        self.writes = 0
        self.is_open = False

    def open(self, vcom: float) -> DeviceInfo:
        self.is_open = True
        return DeviceInfo(width=1200, height=825, firmware="fake", lut="fake", vcom=vcom)

    def write(self, image: Image.Image, mode: Mode, xy: tuple[int, int] = (0, 0)) -> None:
        if not self.is_open:
            raise RuntimeError("not open")
        if image.mode != "L":
            raise ValueError("image must be grayscale")
        self.writes += 1
        if os.environ.get("FAKE_HANG") and self.writes > 1:
            while True:
                time.sleep(1)
        time.sleep(0.001)

    def sleep(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False


def make() -> Fake:
    return Fake()
