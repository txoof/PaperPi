# Screens and drivers

A screen driver is the code that sends a picture to one screen model. The drivers are in epdlib, the separate library that also draws the layouts. PaperPi runs every screen write in a small helper process with a time limit, so a screen that stops answering can never freeze PaperPi. Writes are fast where they can be, full when another plugin comes on the screen, and the screen is cleaned once an hour.

Which screens work, and how to set them up, is on [Supported screens](../screens.md). This page describes how PaperPi talks to them.

## What every driver does

Every driver offers the same parts, so PaperPi works the same on any screen:

| Part          | What it does                                                                                       |
| ------------- | -------------------------------------------------------------------------------------------------- |
| description   | the model, its size in pixels, what it shows (black and white, grays, colors), whether it has fast writes, and whether it was tested |
| `init`        | starts the screen and checks that it answers (the IT8951 board must report the right size)        |
| `write`       | shows a picture, fast or full                                                                      |
| `clear`       | makes the screen blank                                                                             |
| `sleep`       | puts the screen into low power; the next `write` or `clear` wakes it                              |
| `close`       | releases the screen's data line (SPI) and pins (GPIO), also after an error                        |

- **Every part has a time limit.** A driver never waits forever for the screen; when the time is up, it stops with a timeout error.
- **The drivers use only `gpiod` and `spidev`,** the standard Linux libraries for pins and SPI. They work on every Pi from the Pi 3 on.
- **Waveshare's small screens** use Waveshare's own program file for each model, unchanged. Only their shared helper file is replaced: it adds the time limits and claims only the pins the screen needs.

## One write

1. PaperPi sends the picture to the screen's helper process and waits, at most the time limit.
2. The driver wakes the screen, draws the picture and waits until the screen's busy signal (a wire that stays on while the screen redraws) switches off.
3. The screen goes to sleep until the next write.

Note: Waveshare warns that a screen left powered for a long time can be damaged, so the screen sleeps after every write.

**A write that hangs is not waited for:** the helper process is stopped, which makes the operating system release the screen's data line and pins. The next write starts a new helper process, and `init` resets the screen.

## Fast, full and cleaning writes

| Write          | When                                                                   | On the IT8951 screens                                   |
| -------------- | ---------------------------------------------------------------------- | ------------------------------------------------------- |
| **fast**       | a new picture from the plugin already on the screen (a clock tick, the next song) | no flash; only the changed part is sent        |
| **full**       | another plugin comes on the screen, or after `max_refresh` fast writes in a row | a flash, then a clean picture in 16 grays    |
| **cleaning**   | every `clean_every` seconds, at the next write, and at the first write after a start | a longer flash to white, then the picture in full |

- **Plugins don't choose:** PaperPi decides from what changed.
- **Screens without fast writes** always do a full write, which leaves no leftovers, so PaperPi doesn't clean them.
- **Fast writes leave faint leftovers** of earlier pictures. A full write removes most of them; only a cleaning write removes all of them.

## Colors and grays

- The driver says what the screen can show. Each block of a layout is drawn directly in that form.
- **Text is never dithered** (dithering uses dot patterns to fake in-between shades), so it stays sharp. Pictures are dithered on their own block.
- A block marked for color uses color only on color screens; on other screens it is drawn in gray or black and white.
- `color = false` in `[display]` draws in gray on a color screen.

## The virtual screen

The virtual screen saves each picture as a PNG file instead of showing it. It is used for the tests, the pictures in this manual, `paperpi render` and the previews in the web interface. It can be any size and any kind of screen (black and white, 16 grays, 7 colors), so a plugin can be checked for any screen without the hardware.

## Start and stop

- **At start**, PaperPi starts the screen in its own thread and checks that it answers. If it doesn't, PaperPi keeps running and the web interface shows the error, for example "screen not answering: check the cable and the selected model". It does not crash and restart over and over.
- **On a stop that was asked for** (Ctrl+C, `systemctl stop`, a shutdown or restart of the Pi), the screen is cleared, or keeps its picture with `on_exit = "keep"`.
- **After a crash** the picture stays: the restart draws it again soon, and a clear would only add a flash.

Note: the clear at a stop is skipped when a write is still running after 2 seconds, when writes are paused, or when the screen was never started, so stopping stays quick. A second stop signal ends it at once.

## A screen that keeps failing

The screen watchdog is a set of rules for a screen that keeps failing:

1. **After 3 failed writes in a row,** the helper process is restarted, which resets the screen.
2. **When the write after 3 such resets fails too,** writes pause. The next try is after 10 minutes, and each failed try doubles the wait, up to 6 hours. PaperPi keeps running, and the web interface shows the problem.
3. **A config reload, or Try again now,** tries the screen again at once.
4. **When a helper process can't be stopped** (it is stuck inside the operating system), only a restart of PaperPi can help: PaperPi exits and systemd starts it again. This happens at most once an hour, so it can't become a restart loop.

Note: a wrong setting or a switched-off SPI is not fixed by trying again, so trying less often keeps the log short.

## Numbers

| What                                         | Value                                                     | Setting         |
| -------------------------------------------- | --------------------------------------------------------- | --------------- |
| fast writes before a full one                | 4                                                         | `max_refresh`   |
| time between cleaning writes                 | 1 hour (0: never; else at least 10 minutes)               | `clean_every`   |
| what happens at a stop                       | clear the screen                                          | `on_exit`       |
| longest first write, before the redraw time is measured | 2 minutes (color screens: 5 minutes)           | none            |
| longest write after that                     | 3 times the last redraw, at least 30 seconds and at most 5 minutes | none   |
| failed writes before a reset                 | 3 in a row                                                | none            |
| resets before writes pause                   | 3                                                         | none            |
| wait while writes pause                      | 10 minutes, doubled after each failed try, at most 6 hours | none           |
| wait for a running write at a stop           | 2 seconds                                                 | none            |
| longest clear at a stop                      | 30 seconds                                                | none            |
| PaperPi exits for a stuck helper process     | at most once an hour                                      | none            |
| IT8951: one wait for the busy signal         | 2 seconds (5 seconds after the reset in `init`)           | none            |
| IT8951: one whole `init`, `write` or `clear` | 15 seconds                                                | none            |

## Not built yet

- **Red and yellow on three-color screens:** they show only black and white for now.
- **A screen and a HiFiBerry on the e-Paper HAT:** both need GPIO 18, so they can't be used on the same Pi.
- **A memory limit for PaperPi** in its systemd service, as a safety net if it ever used too much memory.

## Why it works this way

- **A helper process for every write:** one stuck call deep inside a library can't always be stopped from inside Python, but a separate process can always be stopped. PaperPi v1 waited for the screen without a time limit, which is the likely cause of its freezes.
- **Waveshare's own files, unchanged:** about 60 models work without writing a driver for each, and only the shared helper file needed the time limits.
- **On the IT8951, fast writes use the DU mode:** the faster A2 mode left lines, stray pixels and negative shadows in the screen tests. A changed part with grays (such as the soft edges of text) uses GL16 instead.
- **Cleaning once an hour:** one full write did not remove all leftovers in the screen tests; the longer flash to white did.
- **The full story** is in the old design notes [`display-driver-interface.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/display-driver-interface.md) and [`it8951-driver.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/it8951-driver.md), and the screen tests in [`it8951-test-report.md`](https://github.com/txoof/PaperPi/blob/main/docs/it8951-test-report.md).

## In the code

- `src/paperpi/screen.py`: the helper process, the time limits and the screen watchdog.
- `src/paperpi/scheduler.py`: choosing fast, full and cleaning writes.
- `src/paperpi/config.py`: the `[display]` settings.
- `src/paperpi/limits.py`: the numbers above that have no setting.
- epdlib (a separate repository, [txoof/epdlib](https://github.com/txoof/epdlib)): the drivers, the layouts and the virtual screen.
