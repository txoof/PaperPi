# IT8951 driver test round (M2)

Status: endurance run in progress (started 2026-10-04 21:25, ends about 2026-10-07 21:25; a first start at 21:13 was stopped after 7 writes for a reboot).

Tested on this Pi 4 (Raspberry Pi OS trixie, Python 3.13) with the Waveshare 9.7" e-paper HAT: IT8951 controller, firmware `WS_v.0.2T1`, LUT `8M14T`, 1200 × 825 pixels, VCOM -1.90 (from the ribbon cable). Test programs and raw results (CSV): `bench/it8951/`.

## Candidates

| # | Candidate | Result |
|---|---|---|
| 1 | GregDMeyer's Python/Cython driver (`9f136139`, 2023-11) | Tested. Builds and runs unchanged when the Python environment uses Raspberry Pi OS's `RPi.GPIO` compatibility package (`python3-rpi-lgpio`). |
| 2 | Waveshare's C driver called from Python | **Not tested** (txoof's decision). It switches the SPI chip-select pin (GPIO 8) by hand, but the kernel owns that pin on a normal setup, so it needs direct chip access or a `config.txt` change and a reboot. Its busy waits have no time limit. Details: `bench/it8951/results/waveshare_c.md`. |
| 3 | New small Python driver using `spidev` and `gpiod`, written for this test | Tested. |

## Timings

Median time per write, in seconds, measured until the controller reports the redraw is done. Each write starts by waking the controller.

| Write | Mode | Candidate 1 | Candidate 3 |
|---|---|---|---|
| Clear screen (full) | INIT | 1.61 | 1.78 |
| Full screen, 16 grays | GC16 | 0.71–0.94 | 0.81–1.01 |
| Small area 480 × 160 | GC16 | 0.52 | 0.62 |
| Small area 480 × 160 | DU | 0.32 | 0.39 |
| Small area 480 × 160 | A2 | 0.18 | 0.20 |
| Full screen, black and white | DU | 0.52 | 0.57 |
| Full screen, black and white | A2 | 0.37 | 0.40 |

Candidate 3 is about 0.1 s slower. Most of each write is spent waiting for the controller, so this makes no visible difference on an e-paper screen. Both are far faster than PaperPi needs: plugins update every few minutes, and music plugins accept a delay of a few seconds.

## Pin check

The test lists the GPIO pins in use (`gpioinfo`) before, during and after each run.

| | Candidate 1 | Candidate 3 |
|---|---|---|
| Pins taken | 17 (reset), 24 (busy) | 17 (reset), 24 (busy) |
| Released after close | yes | yes |

Both leave GPIO 18–21 and 2–3 alone, so neither can disturb the HiFiBerry DAC+ (decided with txoof: this check replaces a test with music playing).

## Recovery when the screen stops answering

Simulated in software only: the reset line is held low with `pinctrl` while a full write runs, at 0.05 s, 0.3 s and 0.6 s after the write starts (during the data transfer and during the redraw). Nothing is unplugged.

| | Candidate 1 | Candidate 3 |
|---|---|---|
| Write during fault | stops with `TimeoutError` after about 5 s | stops with `DisplayTimeout` after about 2 s |
| Next write, same process (close + open) | works | works |
| Next write, new process | works | works |
| Pins released afterwards | yes | yes |

Both pass. Notes:
- Candidate 1 has a fixed 5-second limit while waiting for the busy line, but its wait for the end of a redraw (`wait_display_ready`) has no limit. It passed because the busy line also went low during the fault.
- Candidate 1 has no close method. It releases its pins and SPI only when Python deletes the driver object (`SPI.__del__`), and calling that method directly closes the SPI file twice. Over months, a leftover reference (for example in an error report) would keep the pins taken.
- Candidate 3 has a time limit on every wait (2 s for the busy line, 15 s for a redraw, both settings) and a `close()` that always releases everything and can be called more than once.

## Viewing session

txoof judged the screen step by step. Image quality is decided by the controller, the panel and VCOM, not by the driver, so the full set of questions was done once (with candidate 1) and candidate 3 got a short check that it draws correctly. Answers: `bench/it8951/results/*-rubric.md`.

| What | Result |
|---|---|
| 16 gray levels | All 16 bars visible |
| Fine text | 9 px readable, sharpness 4 of 5 ("looks great") |
| Gradient | 16 clear bands, as expected without dithering (dithering of photos is done in epdlib, M3) |
| Fast updates, DU | Minimal ghosting (4 of 5) with candidate 1; no visible ghosting with candidate 3 |
| Fast updates, A2 | Clearly worse: vertical lines, leftover pixels, negative shadows |
| Full-screen DU over earlier content | Earlier digits show through |
| One full GC16 refresh afterwards | Still some ghosts (digits, lines, text) |
| INIT refresh | Removed all ghosts |
| Candidate 3 correctness | Gray bars and clock area correct, same as candidate 1 |

Conclusions:
- **Fast mode: DU**, not A2.
- **A cleaning refresh with INIT is needed now and then.** GC16 alone does not remove all leftovers. v1 did this too: it cleared with INIT before every 4th update (`max_refresh = 4`).

## Endurance run (candidate 3)

Decided with txoof: 72 hours, one write every 60 s (about 4,300 writes, under 0.5% of the 1 million refreshes Waveshare rates the panel for). Each write is a fast DU update of the clock area; every 5th write is a full GC16 page; every 10th write fails on purpose (reset held low during a full write), followed by close and open as PaperPi would do. After every write the run records the process's memory, open files, threads and child processes, and the Pi's free memory.

Purpose: find slow problems a short test cannot show: memory that is not given back, SPI or GPIO handles that are not closed (especially after errors), leftover processes, rare hangs, and write times that slowly grow.

A 2-minute trial before the real run (22 writes, 2 faults) showed: all faults stopped with an error and recovered in 2.6 s; open files stayed at 7, memory at about 24 MB.

Results: *to be added when the run ends.*
