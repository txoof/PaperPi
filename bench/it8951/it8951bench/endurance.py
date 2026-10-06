"""Endurance run: one candidate updates the screen for many hours (M2, issue #201).

Purpose: catch slow problems a short test cannot see, such as memory that is never
given back, SPI or GPIO handles that are never closed, leftover processes, rare hangs
and write times that slowly grow.

Pattern (decided with txoof): one write every 60 seconds. Each write is a fast DU update
of a small clock area; after every 4 fast writes comes a full GC16 refresh of the whole
screen. Every 10th write fails on purpose: the reset line is held low during the write
(software only, see fault.py), and the run then recovers the way PaperPi would: close,
open again, carry on. The screen sleeps after every write.

After every write one CSV row records the result and the process's memory, open files,
threads and child processes, plus the free memory of the whole Pi.

Usage (from bench/it8951; runs in the foreground, start it with setsid/nohup):
    uv run python -m it8951bench.endurance new --vcom <v> --hours 72
"""

import argparse
import csv
import importlib
import os
import sys
import threading
import time
from datetime import datetime

from . import fault, images
from .candidate import Mode
from .run import RESULTS_DIR, _labelled

FIELDS = [
    "time", "n", "kind", "mode", "seconds", "ok", "detail",
    "rss_kb", "open_files", "threads", "children", "mem_available_kb",
]  # fmt: skip

FAST_PER_FULL = 4
FAULT_EVERY = 10
WRITE_LIMIT = 120  # seconds; a write longer than this counts as a hang and ends the run


def _status_kb(field: str, path: str = "/proc/self/status") -> int:
    with open(path) as f:
        for line in f:
            if line.startswith(field + ":"):
                return int(line.split()[1])
    return -1


def _children() -> int:
    total = 0
    for task in os.listdir("/proc/self/task"):
        try:
            with open(f"/proc/self/task/{task}/children") as f:
                total += len(f.read().split())
        except OSError:
            pass
    return total


def health() -> dict:
    """Resource use of this process and free memory of the Pi, right now."""
    return {
        "rss_kb": _status_kb("VmRSS"),
        "open_files": len(os.listdir("/proc/self/fd")),
        "threads": threading.active_count(),
        "children": _children(),
        "mem_available_kb": _status_kb("MemAvailable", "/proc/meminfo"),
    }


def kind_of(n: int) -> str:
    """What write number n (counting from 1) does: 'fault', 'full' or 'fast'."""
    if n % FAULT_EVERY == 0:
        return "fault"
    if n % (FAST_PER_FULL + 1) == 0:
        return "full"
    return "fast"


class Watchdog:
    """Ends the run if one write takes longer than WRITE_LIMIT (the driver hung)."""

    def __init__(self, on_hang) -> None:
        self.deadline: float | None = None
        self.on_hang = on_hang
        threading.Thread(target=self._loop, daemon=True).start()

    def arm(self) -> None:
        self.deadline = time.monotonic() + WRITE_LIMIT

    def disarm(self) -> None:
        self.deadline = None

    def _loop(self) -> None:
        while True:
            time.sleep(1)
            if self.deadline is not None and time.monotonic() > self.deadline:
                self.on_hang()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="it8951bench.endurance",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("candidate")
    parser.add_argument(
        "--vcom", type=float, required=True, help="VCOM voltage printed on the panel's ribbon cable"
    )
    parser.add_argument("--hours", type=float, default=72)
    parser.add_argument("--interval", type=float, default=60, help="seconds between writes")
    args = parser.parse_args(argv)

    cand = importlib.import_module(f"it8951bench.{args.candidate}").make()
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"endurance-{args.candidate}-{datetime.now():%Y%m%d-%H%M%S}.csv"
    out = path.open("w", newline="", buffering=1)
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    writer.writeheader()
    print(f"writing {path}", flush=True)

    def record(n: int, kind: str, mode: str, seconds: float, ok: bool, detail: str) -> None:
        writer.writerow(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "n": n,
                "kind": kind,
                "mode": mode,
                "seconds": round(seconds, 3),
                "ok": ok,
                "detail": detail,
                **health(),
            }
        )
        out.flush()

    def on_hang() -> None:
        record(-1, "hung", "", WRITE_LIMIT, False, f"a write took over {WRITE_LIMIT} s")
        fault.release_reset()
        os._exit(3)

    watchdog = Watchdog(on_hang)

    info = cand.open(args.vcom)
    full = (info.width, info.height)
    xy = (
        (info.width - images.CLOCK_SIZE[0]) // 2 // 8 * 8,
        (info.height - images.CLOCK_SIZE[1] - 40) // 8 * 8,
    )
    pages = (images.gray_steps, images.fine_text, images.gradient)
    cand.write(images.blank(*full), Mode.INIT)
    cand.sleep()

    end = time.monotonic() + args.hours * 3600
    next_at = time.monotonic()
    n = 0
    while time.monotonic() < end:
        next_at += args.interval
        n += 1
        kind = kind_of(n)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if kind in ("full", "fault"):
            # Full pages rotate and carry a time stamp, so the image always changes.
            # Fault writes are full GC16 writes (about 1 s), so the fault surely hits
            # while the write is running.
            page = pages[(n // (FAST_PER_FULL + 1)) % len(pages)](*full)
            img, mode, at = _labelled(page, f"endurance #{n}  {stamp}"), Mode.GC16, (0, 0)
        else:
            img, mode, at = images.clock(), Mode.DU, xy

        timer = None
        if kind == "fault":
            timer = threading.Timer(0.3, fault.hold_reset_low)
            timer.start()
        watchdog.arm()
        start = time.monotonic()
        try:
            cand.write(img, mode, at)
            ok, detail = True, ""
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        seconds = time.monotonic() - start
        watchdog.disarm()
        if timer is not None:
            timer.join()
            fault.release_reset()

        if ok:
            try:
                cand.sleep()
            except Exception as e:
                ok, detail = False, f"sleep: {type(e).__name__}: {e}"
        if kind == "fault":
            # The fault is expected to fail the write; "ok" here means it did.
            detail = ("expected error: " + detail) if not ok else "write did NOT fail"
            ok = not ok
        record(n, kind, mode.name, seconds, ok, detail)

        if kind == "fault" or not ok:
            # Recover the way PaperPi would: release everything, open again.
            watchdog.arm()
            start = time.monotonic()
            try:
                cand.close()
                cand.open(args.vcom)
                cand.sleep()
                rok, rdetail = True, ""
            except Exception as e:
                rok, rdetail = False, f"{type(e).__name__}: {e}"
            watchdog.disarm()
            record(n, "recover", "", time.monotonic() - start, rok, rdetail)

        time.sleep(max(0.0, next_at - time.monotonic()))

    try:
        cand.write(images.blank(*full), Mode.INIT)
        cand.sleep()
    finally:
        cand.close()
    record(n, "end", "", 0, True, "run finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
