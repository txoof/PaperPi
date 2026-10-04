"""Pin check: which GPIO lines does a candidate hold?

We take a snapshot of the GPIO lines in use before the candidate starts, while it
runs, and after it closes. The IT8951 board needs only GPIO 17 (reset) and
GPIO 24 (busy) on top of the SPI pins, which the kernel already holds. The
HiFiBerry DAC+ uses GPIO 18-21 and 2-3, so a candidate that holds only 17 and 24
cannot disturb it.
"""

import os
import re
import subprocess

ALLOWED_NEW = frozenset({17, 24})

_LINE = re.compile(r'^\s*line\s+(\d+):.*?consumer="([^"]*)"', re.MULTILINE)


def parse_gpioinfo(text: str) -> dict[int, str]:
    """Return {line number: consumer name} for every line that is in use."""
    return {int(n): consumer for n, consumer in _LINE.findall(text)}


def snapshot(chip: str = "gpiochip0") -> dict[int, str]:
    """Lines in use right now, read with the ``gpioinfo`` tool from libgpiod.

    Set IT8951BENCH_NO_GPIO=1 to skip this on computers without GPIO (unit tests).
    """
    if os.environ.get("IT8951BENCH_NO_GPIO"):
        return {}
    out = subprocess.run(
        ["gpioinfo", "-c", chip], capture_output=True, text=True, timeout=10, check=True
    )
    return parse_gpioinfo(out.stdout)


def new_lines(before: dict[int, str], after: dict[int, str]) -> dict[int, str]:
    """Lines in use in ``after`` that were not in use in ``before``."""
    return {n: c for n, c in after.items() if n not in before}


def check(before: dict[int, str], during: dict[int, str]) -> tuple[bool, str]:
    """Pass if the candidate took no lines other than 17 and 24."""
    taken = new_lines(before, during)
    extra = sorted(set(taken) - ALLOWED_NEW)
    held = ", ".join(f"{n} ({taken[n]})" for n in sorted(taken)) or "none"
    if extra:
        return False, f"holds unexpected lines {extra}; all new lines: {held}"
    return True, f"new lines: {held}"


def check_released(before: dict[int, str], after_close: dict[int, str]) -> tuple[bool, str]:
    """Pass if every line the candidate took is free again after close()."""
    left = new_lines(before, after_close)
    if left:
        return False, f"still held after close: {sorted(left)}"
    return True, "all lines released"
