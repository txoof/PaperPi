# Freeze suspects (v1) and how v2 prevents them

Milestone M1, issue #185. Docs only, no code.

## Problem

PaperPi v1 on the Pi stops updating the e-paper display after 3–6 months. The program does **not** crash: the process keeps running. That matters because the service file only restarts PaperPi when it exits with an error (`Restart=on-failure` in `install/paperpi-daemon.service` on branch `v1`). A program that is stuck, or that keeps looping without drawing anything, is never restarted. So far only a reinstall has fixed it.

Two kinds of fault fit this symptom:

- **Stuck:** the program waits for something (the display, the network) that never answers, with no time limit.
- **Looping without effect:** the program keeps running, but every screen update fails, and it logs the error and tries again forever without fixing the cause.

Note: a reinstall also stops and starts the service (`install/install.sh:71-75`, `:475`) and builds a fresh Python environment (`:242-257`). So "a reinstall fixed it" does not prove the cause was on disk; a plain restart may have been enough (see open question 2).

Evidence from v1 issue #159: after some hours, *every* plugin is reported as "returned invalid image data; screen update skipped". In the log the error comes 5 seconds after the update starts, which matches the 5-second limit in the IT8951 driver's wait for the display (`spi.pyx:101-109`). This points at the display path, not at the plugins (suspect 1). Issue #177 is about install failures on trixie, not the freeze, but it shows the GPIO libraries are fragile (see "Checked, less likely").

Code locations: PaperPi = `txoof/PaperPi` branch `v1`; epdlib = `txoof/epdlib` branch `v0.6`; IT8951 = `GregDMeyer/IT8951` commit `9f13613` (path `src/IT8951/`).

Terms used below:
- **SPI**: the data connection between the Pi and the display board. Opened as the file `/dev/spidev0.0`.
- **GPIO**: the Pi's control pins. The display uses some of them, for example a "busy" pin that the display sets while it is working.
- **File handle**: a number the system gives the program for each open file or device. There is a limit per program (usually 1024).
- **Watchdog**: a timer outside the program that restarts it if it does not report "still working" in time.
- **Monotonic clock**: a clock that only counts forward from boot. Unlike the normal clock, it does not jump when the time is corrected over the network.

## Suspects, ranked

| # | Suspect | How likely | v2 fix in |
|---|---|---|---|
| 1 | Display errors are logged and skipped forever; display never reset | High | M3, M4 |
| 2 | Nothing notices that PaperPi stopped working | High (certain to make 1–7 permanent) | M4 |
| 3 | IT8951 driver waits for the display with no time limit | Medium | M2, M3 |
| 4 | Waveshare drivers wait for the busy pin with no time limit | Medium (only with Waveshare displays) | M3 |
| 5 | SPI/GPIO not released when a display write fails | Medium | M3 |
| 6 | Plugin time limit can be caught by the plugin or cannot interrupt it | Medium | M4 |
| 7 | Network calls with no time limit | Low–medium | M4, M7 |
| 8 | Downloaded images never removed; `/tmp` uses memory on trixie | Low | M4 |
| 9 | Normal clock used for waits and file ages | Low | M3, M4 |
| 10 | SD card full or worn out | Low (unknown) | M4, M6 |
| 11 | HiFiBerry DAC+ and Waveshare driver share GPIO 18 | Low | M2, M6 |

### 1. Display errors are logged and skipped forever
- **Where:** epdlib `epdlib/Screen.py:245-297` turns every driver error into `ScreenError`. PaperPi `paperpi/paperpi.py:556-567` catches `ScreenError`, logs "invalid image data; screen update skipped" and continues the loop. The IT8951 board is only reset when the driver starts (`spi.pyx:74-77`).
- **Why:** if the display board stops answering once (power dip, electrical noise, a board fault), every later write fails the same way. Nothing resets the board or exits, so the program loops forever with a frozen screen. This matches #159.
- **How likely:** high. It matches both the symptom and the #159 log.
- **v2:** M3: on a timeout the driver resets the display and raises a clear error. M4: the core counts failed writes in a row; after a few it resets the display, and if that does not help it exits with an error so systemd or Docker restarts it.
- **Test:** unit test with a fake driver that always fails: check that the core resets, then exits. M2 hardware test: reset or unplug the display during an update and check that PaperPi recovers.

### 2. Nothing notices that PaperPi stopped working
- **Where:** `install/paperpi-daemon.service`: `Restart=on-failure`, no `WatchdogSec`. The main loop (`paperpi.py:510-573`) never reports progress to anything outside.
- **Why:** not a cause on its own, but it turns any of the other suspects into a permanent freeze.
- **How likely:** certain to be part of the problem.
- **v2:** M4: a systemd watchdog (and a Docker health check from M6). The core reports "working" only after a full loop in which the display is healthy. If no report arrives within the limit, systemd restarts PaperPi. `Restart=always`.
- **Test:** fake driver that hangs forever: check that PaperPi is restarted within the limit. From M4 on, this Pi records time since the last screen update, memory and open files over months.

### 3. IT8951 driver waits for the display with no time limit
- **Where:** IT8951 `interface.py:143-145` (`wait_display_ready` loops while a status register is non-zero), called from `display.py:230`. PaperPi calls the display with no time limit of its own (`paperpi.py:551-557`); the plugin time limit is switched off before the display is called (`library/Plugin.py:168-182`).
- **Why:** if the board keeps reporting "busy", or the data line reads non-zero all the time, the loop never ends. Each register read has a 5-second limit, but the loop around it has none.
- **How likely:** medium. Only happens with a hardware fault, but over months that is plausible.
- **v2:** M2 tests three drivers for exactly this ("does it stop with an error instead of waiting forever"). M3: every wait for the display has a time limit. Watchdog (suspect 2) as the last fallback.
- **Test:** fake GPIO/register that stays busy: the wait ends with a timeout error within the limit. M2 hardware test with the display unplugged during an update.

### 4. Waveshare drivers wait for the busy pin with no time limit
- **Where:** PaperPi `paperpi/waveshare_epd/epd7in5_V2.py:76-84` (`ReadBusy`, loop at lines 80-82). `sleep()` also calls it (`:278-286`). The same kind of loop is in 56 of the files in `paperpi/waveshare_epd/`.
- **Why:** if the busy pin never changes, the loop runs forever. It does not pause between checks, so one CPU core runs at 100%.
- **How likely:** medium if the frozen Pi had a Waveshare display, none if it had the IT8951 (open question 3).
- **v2:** M3: Waveshare driver files are wrapped so every busy wait has a time limit and SPI/GPIO are always released.
- **Test:** fake busy pin that never changes: timeout error within the limit. Hardware test on one small Waveshare display.

### 5. SPI/GPIO not released when a display write fails
- **Where:** epdlib `Screen.py:271-281`: for Waveshare displays, `epd.sleep()` (which closes SPI) only runs if the write succeeded. `Screen.module_exit` (`Screen.py:725-742`) does nothing; its body is commented out. The Waveshare setup opens SPI again on every write (`paperpi/waveshare_epd/epdconfig.py:101-108`).
- **Why:** after a failed write, SPI stays open and is opened again on the next write. This may use up file handles one by one. When the limit is reached, all file and device access fails, including downloads and the display.
- **How likely:** medium. It only grows when writes fail, which fits a fault that builds up over months.
- **v2:** M3: SPI and GPIO are opened once and closed in a `with` block (Python code that always runs its clean-up step, even after an error).
- **Test:** unit test where the write raises an error: SPI and GPIO are closed afterwards. M2 72-hour run and M4 long-term run record the number of open files.

### 6. Plugin time limit can be caught or cannot interrupt
- **Where:** `library/Plugin.py:142-143` and `:168-182` use an alarm signal to stop a slow plugin. The exception it raises is a normal `Exception`. Plugins catch all exceptions, for example `plugins/xkcd_comic/xkcd_comic.py:147-151`.
- **Why:** if the alarm fires inside such a block, the plugin logs it and continues, now with no time limit at all. The next network call can hang forever. The alarm also cannot stop code that is stuck inside a C library.
- **How likely:** medium.
- **v2:** M4: each plugin update runs in a separate worker process with a deadline. The core stops the worker when the deadline passes; plugin code cannot catch that.
- **Test:** plugins that sleep forever, that catch all exceptions, and that block in C code: the core moves on within the limit and stops the worker.

### 7. Network calls with no time limit
- **Where:** `library/CacheFiles.py:112` and `:122` (download, then reading the data), `plugins/met_no/met_no.py:92` and `:489`, `plugins/moon_phase/moon_phase.py:96` and `:525`, `plugins/reddit_quote/reddit_quote.py:59`, `plugins/xkcd_comic/xkcd_comic.py:37`, `plugins/librespot_client/librespot_client.py:39`, `plugins/newyorker/newyorker.py:95` (feedparser). `lms_client` uses the `lmsquery` library, not checked.
- **Why:** a server that accepts the connection but never answers keeps the call waiting forever. Normally the plugin alarm (suspect 6) stops it, so this only freezes PaperPi together with suspect 6.
- **How likely:** low–medium.
- **v2:** M4: one shared helper for web requests with a connect time limit and a total time limit. Plugins (M4, M7) must use it; a test fails if a plugin calls the network another way.
- **Test:** a local test server that accepts and never answers: the call ends with an error within the limit.

### 8. Downloaded images never removed; `/tmp` uses memory
- **Where:** `library/CacheFiles.py:59` puts the cache in a folder under `/tmp`. `lms_client`, `librespot_client` and `newyorker` remove old files; `xkcd_comic` never does.
- **Why:** the cache grows with every new comic. On trixie, `/tmp` is stored in memory (tmpfs), so a growing cache uses RAM. On older Raspberry Pi OS versions `/tmp` is on the SD card. The growth is slow and has an upper bound (the number of xkcd comics), so it is unlikely to freeze v1 on its own.
- **How likely:** low for v1. Important for v2 on trixie.
- **v2:** M4: a cache folder outside `/tmp` (a Docker volume from M6) with a size limit and an age limit.
- **Test:** fill the cache past the limit: the oldest files are removed and the size stays under the limit.

### 9. Normal clock used for waits and file ages
- **Where:** IT8951 `spi.pyx:105-107` measures its 5-second limit with the normal clock. `plugins/moon_phase/moon_phase.py:495` and `library/CacheFiles.py:171` compare the normal clock with file times. (Most v1 timers already use the monotonic clock: epdlib `Screen.py:186-188`, `Plugin.py:135`.)
- **Why:** the Pi has no battery clock. Its time is set over the network and can jump. If it jumps back, the 5-second limit lasts as long as the jump. If a file looks newer than "now", cached data is used and never refreshed.
- **How likely:** low.
- **v2:** rule: all durations use the monotonic clock (M3 drivers, M4 core).
- **Test:** unit tests with a fake clock that jumps backwards and forwards.

### 10. SD card full or worn out
- **Where:** OS level. v1 writes little itself (logs go to the system journal, the cache to `/tmp`), but other software on the Pi may fill the card, and old cards fail.
- **Why:** a full or failing card makes writes fail or the system switch the card to read-only. A fresh install on a new card would then "fix" it.
- **How likely:** low, but unknown without data from the frozen Pi (open question 1).
- **v2:** M4: logs with a size limit; the health check reports free disk space and memory. M6: the install checks free space.
- **Test:** run with a small, full disk area: PaperPi reports a clear error instead of hanging.

### 11. HiFiBerry DAC+ and Waveshare driver share GPIO 18
- **Where:** `paperpi/waveshare_epd/epdconfig.py:45` claims GPIO 18 as the display power pin. The HiFiBerry DAC+ uses GPIO 18–21 for audio (I2S). The IT8951 board uses GPIO 8, 17 and 24 (`constants.py:4-6`) and SPI, so it does not conflict.
- **Why:** with a Waveshare display and the DAC+ on one Pi, both drive the same pin. This would more likely break audio or the display from the start than freeze after months.
- **How likely:** low.
- **v2:** M2 tests the display while music plays. Drivers claim only the pins they need. M6: the install warns about pin conflicts.
- **Test:** M2 and M6 tests with the DAC+ playing music while the display updates.

### Checked, less likely
- **Font size search** (epdlib `Layout.py:302-318`) loops without a limit, but it always ends because the test text grows with each step.
- **Images opened and not closed** (epdlib `Block.py:1161`, `xkcd_comic.py:161`): Python frees them when they are no longer used.
- **Memory growth:** no clear leak found by reading the code. Not measured; the M2 and M4 long runs will measure it.
- **Log volume:** several log lines per plugin every 5 seconds go to the system journal (`config/logging.cfg`, `paperpi.py:451-476`). The journal limits its own size. On Raspberry Pi OS it is kept in memory, so logs are lost on reboot.
- **GPIO library mix** (#177; epdlib `setup.py` installs `RPi.GPIO`, `gpiozero` and `lgpio`): breaks start-up on trixie, not a freeze after months. v2 uses only `gpiod` and `spidev`.

## Options considered

1. **Fix each cause only.** Needed, but we cannot be sure the list is complete.
2. **Watchdog only.** Simple, but it hides faults: PaperPi would restart over and over without anyone knowing why.
3. **Both** (proposed): time limits and clean-up in every layer, plus a watchdog as the last fallback, plus logs and health data that show *why* it restarted.

## Decision (proposed): rules for v2

1. Every wait has a time limit: display, network, plugins, files. No `while` loop waits for hardware without one.
2. All durations use the monotonic clock.
3. Hardware (SPI, GPIO) is opened once and always closed, also after an error (`with` blocks).
4. An error is either handled (with a retry limit) or ends the program. No loop logs the same error forever.
5. After a few failed display writes in a row, reset the display; if that fails, exit with an error so systemd/Docker restarts PaperPi.
6. A watchdog restarts PaperPi if the main loop has not finished a healthy pass within N minutes (systemd `WatchdogSec`, Docker health check). `Restart=always`.
7. Plugins run in a worker process with a deadline that plugin code cannot catch.
8. Caches and logs have size limits and live outside `/tmp`.
9. PaperPi records time since the last screen update, memory, open files and free disk, and shows them in the logs and the health check.
10. Each rule has a test with a fake driver or fake server, and the long-term run on this Pi (from M4) checks them over months.

## Open questions for txoof

1. Do you have any logs from a frozen Pi? On Raspberry Pi OS the system journal is kept in memory, so it is lost after a reboot or reinstall. Next time it freezes, before restarting anything, could you save: `journalctl -u paperpi-daemon`, `top` (is one CPU core at 100%?), `free -m`, `df -h`, `dmesg | tail -50`, and the number of open files (`sudo ls /proc/$(pidof -s python3)/fd | wc -l`)?
2. When it froze, did you try only `sudo systemctl restart paperpi-daemon` or a reboot before reinstalling? Did that help?
3. Which display and plugins were on the Pi(s) that froze: the 9.7" IT8951 or a Waveshare display? Was the HiFiBerry attached?
4. Which OS version was it running (bullseye or bookworm)?
5. When it froze, was the last image complete, or half drawn? Was the screen blank?
6. Is #159 ("all plugins return invalid image data") the same fault as the freeze, or a different one?
7. Watchdog limit: PaperPi skips the screen update when nothing changed, so "no screen update for N minutes" can be normal. Is it OK to define "healthy" as "the main loop finished a pass and the last display write (if any) succeeded", with a limit of 10 minutes?
8. How many failed display writes in a row before v2 resets the display, and how many before it exits? Proposal: reset after 2, exit after 5.
