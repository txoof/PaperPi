# IT8951 driver

Status: proposed (M2, issue #201). Final once the 72-hour endurance run passes and txoof approves.

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
- Time limits (defaults, settings in the driver): 2 s waiting for the busy line, 15 s for a redraw. On timeout the driver raises `DisplayTimeout`; PaperPi then handles it as decided in `errors-and-time-limits.md` (retry, reset, and so on).

## Open questions

- Endurance run result (ends about 2026-10-07 21:14). If it shows a leak or a hang, this decision is reopened.
