"""Candidate 1: GregDMeyer's IT8951 driver (github.com/GregDMeyer/IT8951).

Tested at upstream commit 9f136139 (2023-11-08), installed unchanged from a local
checkout. It builds and runs on trixie without fixes when the venv uses the Raspberry
Pi OS packages (``RPi.GPIO`` from ``python3-rpi-lgpio``); see README.md.

This adapter calls the driver's low-level ``EPD`` class in the same order as the
driver's own ``AutoEPDDisplay.update``, plus a wake-up before each write (the screen
sleeps after every write) and a final wait so the write can be timed.
"""

import gc

from PIL import Image

from .candidate import DeviceInfo, Mode


class Greg:
    name = "greg"

    def __init__(self) -> None:
        self.epd = None

    def open(self, vcom: float) -> DeviceInfo:
        from IT8951.interface import EPD

        self.epd = EPD(vcom=vcom, data_hz=24_000_000)
        e = self.epd
        return DeviceInfo(
            width=e.width,
            height=e.height,
            firmware=e.firmware_version.strip("\x00"),
            lut=e.lut_version.strip("\x00"),
            vcom=e.get_vcom(),
        )

    def write(self, image: Image.Image, mode: Mode, xy: tuple[int, int] = (0, 0)) -> None:
        e = self.epd
        if e is None:
            raise RuntimeError("not open")
        e.run()
        e.wait_display_ready()
        e.load_img_area(image.tobytes(), xy=xy, dims=image.size)
        e.display_area(xy, image.size, int(mode))
        e.wait_display_ready()

    def sleep(self) -> None:
        if self.epd is not None:
            self.epd.sleep()

    def close(self) -> None:
        # The driver has no close method: it releases its pins and SPI only in SPI.__del__,
        # which runs when the object is freed. Calling __del__ directly closes the SPI
        # file twice (it does not forget the closed file number), so drop the reference
        # and let Python free it.
        self.epd = None
        gc.collect()


def make() -> Greg:
    return Greg()
