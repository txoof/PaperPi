"""Run the test scenarios for one candidate and save the results as CSV.

Usage (from bench/it8951):
    uv run python -m it8951bench <candidate> <scenario> [options]

Scenarios:
    basic   timings for full, partial and fast writes, plus the pin check
    fault   hold the reset line low during a write; does the candidate stop with an
            error, and does the next write work?
    view    a fixed sequence of images for txoof's viewing session (see rubric.md)
    show    show one image (for quick checks)

Every scenario runs in a separate child process. If the candidate hangs, the child
is killed after a time limit, so a stuck driver can never stop the test round.
"""

import argparse
import csv
import importlib
import multiprocessing as mp
import queue
import sys
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ImageDraw

from . import fault, images, pins
from .candidate import Candidate, DeviceInfo, Mode

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
FIELDS = ["time", "candidate", "scenario", "step", "mode", "area", "seconds", "ok", "detail"]

Report = Callable[..., None]


# ---------------------------------------------------------------- child side


def _timed(report: Report, step: str, fn: Callable[[], Any], mode: str = "", area: str = ""):
    """Run fn, report how long it took and whether it raised. Return (ok, result)."""
    start = time.monotonic()
    try:
        result = fn()
        ok, detail = True, ""
    except Exception as e:  # the error itself is the measurement
        result, ok, detail = None, False, f"{type(e).__name__}: {e}"
    report(
        step=step,
        mode=mode,
        area=area,
        seconds=round(time.monotonic() - start, 3),
        ok=ok,
        detail=detail,
    )
    return ok, result


def _area(xy: tuple[int, int], size: tuple[int, int]) -> str:
    return f"{xy[0]},{xy[1]} {size[0]}x{size[1]}"


def _clock_xy(info: DeviceInfo) -> tuple[int, int]:
    """Bottom centre, on a multiple of 8 pixels (the controller packs 4 pixels per word)."""
    w, h = images.CLOCK_SIZE
    return ((info.width - w) // 2 // 8 * 8, (info.height - h - 40) // 8 * 8)


def _labelled(img, text: str):
    """Write a step label in the top-left corner, so txoof can see which step is shown."""
    img = img.copy()
    draw = ImageDraw.Draw(img)
    font = images._font(28, bold=True)
    box = draw.textbbox((10, 10), text, font=font)
    draw.rectangle([box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6], fill=255, outline=0)
    draw.text((10, 10), text, fill=0, font=font)
    return img


def _open(cand: Candidate, report: Report, vcom: float) -> DeviceInfo | None:
    ok, info = _timed(report, "open", lambda: cand.open(vcom))
    if ok:
        report(step="device info", ok=True, detail=f"{info}")
        return info
    _timed(report, "close after failed open", cand.close)
    return None


def _finish(cand: Candidate, report: Report, before: dict[int, str]) -> None:
    _timed(report, "sleep", cand.sleep)
    _timed(report, "close", cand.close)
    ok, detail = pins.check_released(before, pins.snapshot())
    report(step="pins released", ok=ok, detail=detail)


def scenario_basic(cand: Candidate, report: Report, opts: dict, _: Any) -> None:
    before = pins.snapshot()
    info = _open(cand, report, opts["vcom"])
    if info is None:
        return
    ok, detail = pins.check(before, pins.snapshot())
    report(step="pin check", ok=ok, detail=detail)

    full = (info.width, info.height)
    whole = _area((0, 0), full)
    _timed(report, "clear", lambda: cand.write(images.blank(*full), Mode.INIT), "INIT", whole)
    for name, make in (
        ("gray steps", images.gray_steps),
        ("fine text", images.fine_text),
        ("gradient", images.gradient),
    ):
        img = make(*full)
        for i in range(opts["repeat"]):
            _timed(
                report,
                f"full {name} #{i + 1}",
                lambda img=img: cand.write(img, Mode.GC16),
                "GC16",
                whole,
            )

    xy = _clock_xy(info)
    clock_area = _area(xy, images.CLOCK_SIZE)
    for mode in (Mode.GC16, Mode.DU, Mode.A2):
        for i in range(opts["repeat"]):
            img = images.clock()
            _timed(
                report,
                f"partial clock #{i + 1}",
                lambda img=img, mode=mode: cand.write(img, mode, xy),
                mode.name,
                clock_area,
            )

    text_bw = images.to_black_white(images.fine_text(*full))
    for mode in (Mode.DU, Mode.A2):
        for i in range(opts["repeat"]):
            _timed(
                report,
                f"fast full text #{i + 1}",
                lambda mode=mode: cand.write(text_bw, mode),
                mode.name,
                whole,
            )

    _timed(report, "clear", lambda: cand.write(images.blank(*full), Mode.INIT), "INIT", whole)
    _finish(cand, report, before)


def scenario_fault(cand: Candidate, report: Report, opts: dict, link: Any) -> None:
    results, to_child = link
    before = pins.snapshot()
    info = _open(cand, report, opts["vcom"])
    if info is None:
        return
    full = (info.width, info.height)
    whole = _area((0, 0), full)
    img = images.gray_steps(*full)
    _timed(report, "write before fault", lambda: cand.write(img, Mode.GC16), "GC16", whole)

    results.put({"event": "writing"})
    _timed(report, "write during fault", lambda: cand.write(img, Mode.GC16), "GC16", whole)
    results.put({"event": "write returned"})

    # Wait until the parent has released the reset line, then try to recover without
    # restarting the process: close, open again and write.
    to_child.get(timeout=120)
    _timed(report, "close after fault", cand.close)
    info = _open(cand, report, opts["vcom"])
    if info is not None:
        _timed(report, "write after reopen", lambda: cand.write(img, Mode.GC16), "GC16", whole)
        _finish(cand, report, before)


def scenario_recover(cand: Candidate, report: Report, opts: dict, _: Any) -> None:
    """Fresh process after a fault: does the screen work again?"""
    before = pins.snapshot()
    info = _open(cand, report, opts["vcom"])
    if info is None:
        return
    full = (info.width, info.height)
    _timed(
        report,
        "write in new process",
        lambda: cand.write(images.fine_text(*full), Mode.GC16),
        "GC16",
        _area((0, 0), full),
    )
    _finish(cand, report, before)


def scenario_view(cand: Candidate, report: Report, opts: dict, _: Any) -> None:
    """The fixed sequence for the viewing session. Each image carries its step label."""
    before = pins.snapshot()
    info = _open(cand, report, opts["vcom"])
    if info is None:
        return
    full = (info.width, info.height)
    whole = _area((0, 0), full)
    hold = opts["hold"]
    name = cand.name

    def show(label: str, img, mode: Mode, xy=(0, 0), area=whole, wait=hold):
        _timed(report, label, lambda img=img, mode=mode: cand.write(img, mode, xy), mode.name, area)
        time.sleep(wait)

    show("clear", images.blank(*full), Mode.INIT, wait=1)
    show(
        "step 1 gray steps",
        _labelled(images.gray_steps(*full), f"{name}  step 1: gray steps GC16"),
        Mode.GC16,
    )
    show(
        "step 2 fine text",
        _labelled(images.fine_text(*full), f"{name}  step 2: fine text GC16"),
        Mode.GC16,
    )
    show(
        "step 3 gradient",
        _labelled(images.gradient(*full), f"{name}  step 3: gradient GC16"),
        Mode.GC16,
    )

    base = _labelled(images.blank(*full), f"{name}  step 4: clock, 10 fast updates DU")
    show("step 4 base", base, Mode.GC16, wait=1)
    xy = _clock_xy(info)
    clock_area = _area(xy, images.CLOCK_SIZE)
    for _i in range(10):
        show("step 4 clock DU", images.clock(), Mode.DU, xy, clock_area, wait=1)
    time.sleep(hold)

    base = _labelled(images.blank(*full), f"{name}  step 5: clock, 10 fast updates A2")
    show("step 5 base", base, Mode.GC16, wait=1)
    for _i in range(10):
        show("step 5 clock A2", images.clock(), Mode.A2, xy, clock_area, wait=1)
    time.sleep(hold)

    text_bw = images.to_black_white(images.fine_text(*full, title=f"{name}  step 6: text DU"))
    show("step 6 text DU", text_bw, Mode.DU)
    show(
        "step 7 gray steps again",
        _labelled(images.gray_steps(*full), f"{name}  step 7: gray steps GC16 again"),
        Mode.GC16,
    )
    show("clear", images.blank(*full), Mode.INIT, wait=0)
    _finish(cand, report, before)


def scenario_show(cand: Candidate, report: Report, opts: dict, _: Any) -> None:
    before = pins.snapshot()
    info = _open(cand, report, opts["vcom"])
    if info is None:
        return
    full = (info.width, info.height)
    makers = {
        "gray": lambda: images.gray_steps(*full),
        "text": lambda: images.fine_text(*full),
        "gradient": lambda: images.gradient(*full),
        "blank": lambda: images.blank(*full),
    }
    mode = Mode[opts["mode"]]
    img = makers[opts["image"]]()
    if mode in (Mode.DU, Mode.A2):
        img = images.to_black_white(img)
    _timed(
        report,
        f"show {opts['image']}",
        lambda: cand.write(img, mode),
        mode.name,
        _area((0, 0), full),
    )
    _finish(cand, report, before)


SCENARIOS = {
    "basic": scenario_basic,
    "fault": scenario_fault,
    "recover": scenario_recover,
    "view": scenario_view,
    "show": scenario_show,
}


def load_candidate(name: str) -> Candidate:
    return importlib.import_module(f"it8951bench.{name}").make()


def _child(name: str, scenario: str, opts: dict, results: mp.Queue, link: Any) -> None:
    def report(**row: Any) -> None:
        results.put(row)

    try:
        cand = load_candidate(name)
        SCENARIOS[scenario](cand, report, opts, link)
    except Exception:
        report(step="crash", ok=False, detail=traceback.format_exc(limit=5))


# ---------------------------------------------------------------- parent side


class Recorder:
    """Collects result rows, prints them and appends them to a CSV file."""

    def __init__(self, path: Path | None, candidate: str, echo: bool = True):
        self.path = path
        self.candidate = candidate
        self.echo = echo
        self.rows: list[dict] = []

    def add(self, scenario: str, row: dict) -> None:
        row = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "candidate": self.candidate,
            "scenario": scenario,
            **row,
        }
        row = {k: row.get(k, "") for k in FIELDS}
        self.rows.append(row)
        if self.echo:
            mark = "ok  " if row["ok"] else "FAIL"
            print(
                f"{mark} {scenario:8} {row['step']:28} {row['mode']:5} {row['seconds']!s:>8}  "
                f"{row['detail']}",
                flush=True,
            )
        if self.path is not None:
            new = not self.path.exists()
            with self.path.open("a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    writer.writeheader()
                writer.writerow(row)


def run_child(
    name: str,
    scenario: str,
    opts: dict,
    rec: Recorder,
    limit: float,
    on_event: Callable[[str], None] | None = None,
) -> bool:
    """Run one scenario in a child process. Return False if it had to be killed."""
    ctx = mp.get_context("spawn")
    results: mp.Queue = ctx.Queue()  # result rows and events, in the order they happened
    to_child: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=_child, args=(name, scenario, opts, results, (results, to_child)))
    proc.start()
    deadline = time.monotonic() + limit

    def handle(item: dict) -> None:
        if "event" not in item:
            rec.add(scenario, item)
            return
        if on_event is not None:
            on_event(item["event"])
        if item["event"] == "write returned":
            to_child.put("released")

    def drain() -> None:
        while True:
            try:
                handle(results.get_nowait())
            except queue.Empty:
                return

    while proc.is_alive() and time.monotonic() < deadline:
        try:
            handle(results.get(timeout=0.05))
        except queue.Empty:
            continue
    drain()
    if proc.is_alive():
        proc.kill()
        proc.join(10)
        drain()
        rec.add(
            scenario,
            {
                "step": "hung",
                "ok": False,
                "seconds": limit,
                "detail": f"child process killed after {limit:.0f} s",
            },
        )
        return False
    proc.join()
    drain()
    return True


def run_fault(name: str, opts: dict, rec: Recorder) -> None:
    """Fault test: reset held low during a write, then recovery checks."""
    state = {"held_at": None}

    def on_event(event: str) -> None:
        if event == "writing":
            time.sleep(opts["fault_delay"])
            fault.hold_reset_low()
            state["held_at"] = time.monotonic()
            rec.add("fault", {"step": "reset held low", "ok": True})
        elif event == "write returned":
            held = time.monotonic() - state["held_at"] if state["held_at"] else 0
            fault.release_reset()
            rec.add("fault", {"step": "reset released", "ok": True, "seconds": round(held, 3)})

    try:
        run_child(name, "fault", opts, rec, opts["hang_limit"], on_event)
    finally:
        fault.release_reset()
    time.sleep(1)
    run_child(name, "recover", opts, rec, opts["limit"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="it8951bench",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("candidate", help="module name in it8951bench, e.g. greg, waveshare_c, new")
    parser.add_argument("scenario", choices=["basic", "fault", "view", "show"])
    parser.add_argument(
        "--vcom",
        type=float,
        required=True,
        help="VCOM voltage printed on the panel's ribbon cable, e.g. -1.93. "
        "No default: a wrong value can give a poor image.",
    )
    parser.add_argument("--repeat", type=int, default=5, help="repeats per step in basic")
    parser.add_argument("--hold", type=float, default=20, help="seconds per image in view")
    parser.add_argument("--image", choices=["gray", "text", "gradient", "blank"], default="gray")
    parser.add_argument("--mode", choices=[m.name for m in Mode], default="GC16")
    parser.add_argument(
        "--fault-delay",
        type=float,
        default=0.3,
        help="seconds after the write starts before reset is held low",
    )
    parser.add_argument(
        "--hang-limit",
        type=float,
        default=60,
        help="seconds before a faulted candidate counts as hung",
    )
    parser.add_argument("--limit", type=float, default=900, help="time limit per scenario")
    parser.add_argument("--no-save", action="store_true", help="print only, no CSV file")
    args = parser.parse_args(argv)

    opts = vars(args)
    path = None
    if not args.no_save:
        RESULTS_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = RESULTS_DIR / f"{args.candidate}-{args.scenario}-{stamp}.csv"
    rec = Recorder(path, args.candidate)
    if args.scenario == "fault":
        run_fault(args.candidate, opts, rec)
    else:
        run_child(args.candidate, args.scenario, opts, rec, args.limit)
    if path is not None:
        print(f"saved {path}")
    failed = [r for r in rec.rows if not r["ok"]]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
