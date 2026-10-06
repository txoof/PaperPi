# IT8951 driver

Status: proposed (M2, issue #201). Endurance run passed (34 hours, see the test report); final when txoof approves.

## Problem

epdlib v1 needs a driver for the IT8951 controller of the 9.7" display. It must never wait forever (the likely cause of the v1 freeze), must always release its pins and SPI, and may use only `gpiod` and `spidev` (see `display-driver-interface.md`).

## Options considered

Measured on the real screen; full results in `docs/it8951-test-report.md`.

1. **GregDMeyer's driver** (used by v1). Works on trixie unchanged, passes the fault test, and is slightly faster. But: no close method (pins are released only when Python deletes the object), its wait for the end of a redraw has no time limit, it needs a C build step (Cython) and the `RPi.GPIO` compatibility layer, and it has had no changes since November 2023.
2. **Waveshare's C driver.** Not tested: needs direct chip access or a `config.txt` change to control the chip-select pin, and its waits have no time limit.
3. **A new small Python driver** (`bench/it8951/it8951bench/new.py`, about 250 lines). Passes all tests, draws the same image, a time limit on every wait, a `close()` that always releases everything, only `gpiod` and `spidev`, no build step.

## Decision (proposed)

- **Use candidate 3** as the starting point for epdlib's IT8951 driver in M3. It is rewritten there properly with unit tests (a fake SPI and GPIO), following `display-driver-interface.md`; the M2 file is a test version.
- **Fast refresh on the IT8951 is DU.** A2 is faster but left lines, stray pixels and negative shadows.
- **Full refresh is GC16.** After 4 fast refreshes in a row the next write is full (`max_refresh`, default 4).
- **Cleaning refresh once an hour:** INIT, then the image in GC16 (interval is a setting). One GC16 refresh did not remove all leftovers; INIT did.
- Time limits (defaults, settings in the driver): 2 s for one wait for the busy line, 15 s for one whole operation (init, write or clear). On timeout the driver raises `DisplayTimeout`; PaperPi then handles it as decided in `errors-and-time-limits.md` (retry, reset, and so on).
- **No planned daily restart of the screen helper process** (changed on 2026-10-06, M4 issue #222). This note first asked for one, because in the first hours of the endurance run the process's memory grew by about 8 KB per hour. That growth levelled off, so there was no leak. txoof added that v1's freeze was not fixed by restarting PaperPi or the Pi, only by installing everything again, so its cause was something kept on the SD card, not in memory (see `freeze-prevention.md`). A restart can't fix that. The helper process is still restarted whenever a write fails or hangs (`errors-and-time-limits.md`).
- **Memory limit in the Docker setup** (M6), with a restart policy, as a safety net: if PaperPi ever goes over the limit, Docker restarts it instead of letting the Pi run short of memory. Together with the watchdog (`errors-and-time-limits.md`), a leak can at worst cause a restart, never a slow freeze.

## Open questions

None. The endurance run passed: 2,063 writes, 0 unexpected failures, 206 of 206 planned faults recovered, open files flat, no memory leak (growth levelled off in the first 13 hours, so the `tracemalloc` check is not needed). Decided with txoof: the report uses the first 34 hours; the run keeps going until the screen is needed, and this decision is reopened only if later data shows a problem.
