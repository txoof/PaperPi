"""The small interface every IT8951 driver candidate implements for the test round.

Each candidate lives in its own module and provides a function ``make()`` that
returns an object with the methods below. The test tools only talk to that object,
so all three candidates are measured in exactly the same way.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

from PIL import Image


class Mode(IntEnum):
    """IT8951 refresh modes used in the test round (numbers as sent to the chip).

    INIT clears the screen to white with a long flash. GC16 is the full 16-gray
    refresh with a flash. DU and A2 are fast black-and-white modes without a flash.
    """

    INIT = 0
    DU = 1
    GC16 = 2
    A2 = 6


@dataclass(frozen=True)
class DeviceInfo:
    """What the controller reports about itself after start-up."""

    width: int
    height: int
    firmware: str = ""
    lut: str = ""
    vcom: float | None = None


class Candidate(Protocol):
    """One IT8951 driver under test.

    ``write`` must return only when the screen has finished redrawing, so the
    tools can time it. Every method may raise an exception; the tools record it.
    """

    name: str

    def open(self, vcom: float) -> DeviceInfo:
        """Reset the controller, read its device info and set VCOM."""
        ...

    def write(self, image: Image.Image, mode: Mode, xy: tuple[int, int] = (0, 0)) -> None:
        """Show a grayscale ("L") image at position xy and wait until the redraw is done."""
        ...

    def sleep(self) -> None:
        """Put the controller into its low-power sleep state."""
        ...

    def close(self) -> None:
        """Release SPI and GPIO. Must work even after an error."""
        ...
