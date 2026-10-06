"""Pretend screen drivers for tests/test_screen.py. They run in the screen helper process, so
they live in a module of their own that the helper process can import.

Each one notes what it was asked to do in ``<folder>/log`` (one line per operation, with the
process id), so the test can see it from the main process.
"""

import os
import time

from epdlib import ScreenMode
from epdlib.drivers import DisplayError, DisplayInfo, Driver


class Pretend(Driver):
    """A white image is written; a black one hangs, a gray one crashes the process, a
    nearly black one (1) raises an error."""

    def __init__(self, folder, fail_init=False):
        super().__init__()
        self.info = DisplayInfo("pretend", 4, 3, ScreenMode.gray(16))
        self.folder = folder
        self.fail_init = fail_init

    def _note(self, what):
        with open(self.folder / "log", "a") as file:
            file.write(f"{os.getpid()} {what}\n")

    def init(self):
        self._note("init")
        if self.fail_init:
            raise DisplayError("no screen here")

    def write(self, image, *, fast=False):
        shade = image.getpixel((0, 0))
        self._note(f"write {shade}")
        if shade == 0:
            time.sleep(1000)
        elif shade == 128:
            os._exit(3)
        elif shade == 1:
            raise DisplayError("pretend failure")

    def clear(self):
        self._note("clear")

    def sleep(self):
        pass

    def close(self):
        self._note("close")


def notes(folder):
    """The operations, as (process id, what) pairs."""
    path = folder / "log"
    if not path.exists():
        return []
    return [tuple(line.split(" ", 1)) for line in path.read_text().splitlines()]
