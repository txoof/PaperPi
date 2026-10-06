# Display driver interface

Status: proposed (M1, issue #188). Decided with txoof.

This note covers epdlib, the separate library that draws layouts and talks to the screen. It is kept here so all M1 notes are in one place. It does not choose the IT8951 driver; that is done by testing in M2.

## Problem

A display driver is the code that sends an image to one screen model. v2 needs one agreement that every driver follows, so PaperPi works the same on any screen and a broken screen can never freeze it.

What v1 does badly:
- Every wait for the screen has no time limit. The screen's busy signal (a wire that stays on while the screen is redrawing) is read in a loop that never gives up (`epd7in5_V2.py` `ReadBusy`, IT8951 `interface.py`).
- When a write fails, the SPI and GPIO connections (the data lines and control pins to the screen) are not released (`Screen.py` `_spi_handler`).
- Waveshare's helper file uses the old `RPi.GPIO` / `gpiozero` libraries, which are unreliable on new kernels and fail on the Pi 5.
- Driver code and layout code are mixed in one class, so tests and previews need hardware libraries installed.

What v1 does well and v2 keeps:
- Waveshare's own files for each screen model (about 60 models).
- Layouts know the screen type before drawing, so text stays sharp and colour is used only where a layout asks for it.
- The screen sleeps after every write.

## Options considered

**Waveshare screens**
1. Write our own driver for each model. Clean, but a lot of work, and we can test only two models here.
2. **Keep Waveshare's per-model files unchanged and replace only their shared helper file (`epdconfig.py`).** Chosen.

**Where screen writes run**
1. Inside PaperPi (v1). Simple, but one stuck call deep in a library freezes everything; a Python time limit can't always stop it.
2. **In a separate helper process that PaperPi can stop.** Chosen.

**Colour and grayscale**
1. Plugins draw in full colour; epdlib converts the finished image at the end. Rejected: thin text gets speckled edges, coloured text can disappear on black/white screens, and text and photos can't be treated differently.
2. **Keep v1's method: each block is drawn directly in what the screen can show.** Chosen.

## Decision (proposed)

### What every driver provides

| Part | What it does |
|---|---|
| description | Model name, size in pixels, what it can show (1-bit, gray levels, colours), whether it has a fast refresh, and its status: tested or untested. |
| `init` | Wake the screen and check it answers (IT8951: the size it reports must match the model). |
| `write(image, fast)` | Show an image. `fast` is only a request; see refresh types below. |
| `clear` | Make the screen blank. |
| `sleep` | Put the screen into low power. |
| `close` | Release the SPI and GPIO connections. Always runs, even after an error. |

Every operation has a time limit. When it runs out, the driver stops with a timeout error. It never waits forever.

Drivers use only `gpiod` and `spidev`. Importing epdlib's layout code never imports these, so tests, previews and the docs work on any computer.

### Waveshare screens

- Waveshare's per-model files are copied in unchanged, with a note of the version they came from.
- Their shared helper file is replaced by ours. It uses `gpiod`/`spidev`, claims only the pins the screen needs (so the HiFiBerry keeps its pins), and always releases them.
- Waveshare's busy loops call the helper's `digital_read` on every pass. Our helper checks a deadline there and stops with a timeout error, so no per-model file has to change for time limits.
- We change a per-model file only when it is broken, and record each change.

### Screen writes run in a helper process

- Every screen write runs in a small separate helper process.
- If a write takes longer than its time limit, PaperPi stops that helper and starts a new one. The operating system then releases the pins and data lines, so the next write starts clean.
- Normal writes are not slower. A restart costs about a second.
- How many failed writes lead to a display reset, and how many to PaperPi exiting, is decided in the error-handling note (#190) and `freeze-prevention.md`.

### Refresh types

- PaperPi asks the driver for either a **full** refresh (the screen flashes and shows a clean image; takes seconds, much longer on colour screens) or a **fast** refresh (no flash, quick, but faint leftovers of old images build up).
- Each driver maps this to its own modes. On the IT8951, full uses its best grayscale mode (GC16) and fast uses its quick black-and-white mode **DU** (chosen in M2: A2 left lines, stray pixels and negative shadows; see `docs/it8951-test-report.md`).
- **Screens without a fast mode always do a full refresh**, whatever the settings say.
- Plugins don't choose. PaperPi uses fast for small changes of the plugin already on screen (clock tick, next track) and full when another plugin comes on screen.
- After a set number of fast refreshes in a row, the next write is a full one. Setting `max_refresh`, default **4**.
- **Cleaning refresh:** a single full GC16 refresh does not remove all leftovers; the IT8951's INIT mode (a longer flash to white) does (M2 viewing test). PaperPi does a cleaning refresh (INIT, then the image in GC16) once an hour; the interval is a setting. Checked by eye on the screen in M4.
- *Correction (M2):* this note first said `max_refresh` worked "like v1". v1 actually drew every update with a full GC16 refresh, never a fast one, and cleared the screen with INIT before every 4th update (`max_refresh = 4`). v2 keeps that cleaning idea but needs it less often, because most small updates are fast ones.
- PaperPi measures how long each redraw takes (until the busy signal switches off) and never sends a new image before the screen is ready (see `plugin-interface.md`).

### Colour and grayscale

- The driver says what the screen can show. Layouts draw each block directly in that form.
- Text is never dithered (dithering means using dot patterns to fake in-between shades), so it stays sharp. Images are dithered on their own block.
- A layout block marked `rgb_support` uses colour only on colour screens; on others it is drawn in gray or black/white.
- If a plugin draws its whole image itself, epdlib converts it as a last step so it always matches the screen.
- A setting turns colour off on colour screens, as in v1.

### The virtual (PNG) driver

- Writes each image to a PNG file instead of a screen. Used for tests, the docs gallery, `paperpi render` and web interface previews.
- It can pretend to be any screen type (1-bit, 16 grays, 7 colours, any size), so a plugin can be checked for any screen without the hardware.

### Sleep, start-up and exit

- The screen sleeps after every write and is woken for the next one. Waveshare warns that a screen left powered for long periods can be damaged.
- At start, PaperPi checks that the screen answers. If it doesn't, PaperPi keeps running and shows a clear error in the web interface, e.g. "screen not answering: check the cable and the selected model". It does not crash and restart in a loop.
- On exit the screen is cleared by default, or keeps the last image if the user chose that (setting, see `config-format.md`).

### Supported screens

- The web interface and the docs list every model, generated from the driver descriptions.
- Each is marked **tested** (checked on real hardware: for now the 9.7" IT8951 and the 7.5" V2) or **untested** (should work; reports welcome).
- Untested screens are not blocked. The web interface shows a short note when one is selected. A user report that a model works can move it to tested.

## Open questions

None. All points above were agreed with txoof on 2026-10-04. Which IT8951 driver to use is decided in M2.
