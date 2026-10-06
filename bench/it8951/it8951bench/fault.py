"""Fault injection: make the screen stop answering, in software only.

We hold the IT8951's reset line (GPIO 17) low while a write is running. The
controller then stops working and never reports "ready", the same situation that
froze v1. Nobody touches the hardware: never unplug a cable while the Pi is powered.

The candidate already holds GPIO 17 through gpiod, so a second gpiod request would
be refused. ``pinctrl`` (from Raspberry Pi OS) sets the pin directly instead. This
is safe because the pin is already an output from the Pi to the board: we only
change its level, never the direction of a pin the board drives. It is used only
by this test tool, never by a driver.
"""

import subprocess

RESET_PIN = 17


def _pinctrl(*args: str) -> None:
    subprocess.run(["pinctrl", "set", str(RESET_PIN), *args], check=True, timeout=10)


def hold_reset_low() -> None:
    _pinctrl("op", "dl")


def release_reset() -> None:
    _pinctrl("op", "dh")
