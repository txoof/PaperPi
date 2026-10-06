# Freezes: how v2 prevents, notices and recovers from them

Milestone M1, issue #185. Docs only, no code.

## Problem

PaperPi v1 stopped updating the display after 3–6 months but did not crash, so systemd never restarted it. We do not investigate the old code further; we first assumed the cause was the quality of the v1 code (see below). The freezes happened on the 9.7" IT8951 setup. A 7.5" Waveshare display on a Pi 3 ran v1 for a very long time without freezing (never with the HiFiBerry).

Added on 2026-10-06 (txoof, M4 issue #222): restarting PaperPi, or the whole Pi, did **not** fix a frozen v1. Reinstalling PaperPi did not fix it either; only wiping the SD card and installing everything again did (txoof, M4 issue #224). So the cause was something kept on the SD card outside PaperPi's own files (for example a file of the system that kept growing or was damaged, or installed packages that changed over time), not something in memory and not PaperPi's saved files. Restarts are still the right answer to a hang, but v2 must also keep what it stores on the SD card limited in size and replaceable (last row of the checklist).

Terms: **SPI** is the data connection to the display board; **GPIO** are the Pi's control pins; a **watchdog** is a timer outside the program that restarts it if it stops reporting "still working"; the **monotonic clock** only counts forward and does not jump when the time is corrected.

## Checklist

| Fault | Prevent | Notice | Recover | Milestone |
|---|---|---|---|---|
| Display does not answer | Driver chosen after a recovery test (M2) | Write ends with a timeout error | Reset the display; exit after repeated failures so systemd/Docker restarts PaperPi | M2, M3, M4 |
| Wait with no time limit | Every wait (display, network, plugin, file) has a time limit | Timeout error is logged | Caller handles the error or exits | M3, M4 |
| SPI/GPIO not released | Opened once, always closed, also after an error (`with` blocks) | Open-file count in the health data | Process restart releases everything | M3 |
| Plugin stuck | Each plugin update runs in a worker process with a deadline it cannot catch | Deadline passes | Core stops the worker, keeps the last good image, moves on | M4 |
| Network hang | One shared web-request helper with connect and total time limits | Timeout error is logged | Plugin shows its last good data or an error screen | M4, M7 |
| Memory or disk growth | Cache and logs have size and age limits and live outside `/tmp` (in RAM on trixie) | Memory and free disk in the health data | Files changed longest ago are removed from plugin folders; below 2 GB free, plugins are asked not to save more; watchdog restart as last resort | M4, M6 |
| Clock jumps | All durations use the monotonic clock | Not needed | Not needed | M3, M4 |
| Nothing notices the program stopped | systemd watchdog and Docker health check; `Restart=always` | No "healthy" report within the limit | systemd/Docker restarts PaperPi | M4, M6 |
| Something kept on the SD card grows or goes bad (v1's freeze survived restarts) | PaperPi keeps its files in `/var/lib/paperpi` (state) and `/run/paperpi` (in memory); logs have a size limit, plugin folders have size and age limits, and PaperPi keeps 2 GB free (`errors-and-time-limits.md`); files are replaced in one step (`paperpi.files.write_atomic`), so a power cut can't leave half a file; the config has a last good copy; the Docker install gives a fresh copy of the program at every update | Free disk in the health data; config problems are shown | Remove or replace the bad file; a reinstall of the container replaces the program | M4, M6 |
| GPIO shared with HiFiBerry DAC+ | Drivers claim only the pins they need; install warns about conflicts | Clear start-up error if a pin is busy | Not needed (setup error, not a freeze) | M2, M6 |

Test for each row: a fake driver, fake plugin or fake server that fails or hangs, checked in unit tests; hardware tests in M2 (including unplugging the display and playing music on the HiFiBerry); and a long run on this Pi from M4 that records time since the last screen update, memory, open files and free disk.

## Rules for v2

1. Every wait has a time limit.
2. All durations use the monotonic clock.
3. Hardware is opened once and always closed, also after an error.
4. An error is either handled (with a retry limit) or ends the program. No loop logs the same error forever.
5. Plugins run in a worker process with a deadline.
6. Caches and logs have size limits and live outside `/tmp`.
7. A watchdog restarts PaperPi if it stops reporting "healthy".
8. PaperPi records time since the last screen update, memory, open files and free disk.

## Decided elsewhere

`errors-and-time-limits.md` (#190) defines what counts as "healthy" for the watchdog, what happens when display writes keep failing, and the default time limits and size limits.
