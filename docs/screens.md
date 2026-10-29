# Supported screens

PaperPi works with two kinds of Waveshare e-paper screen, and with a virtual screen for trying it out without one. How to connect a screen: [Hardware](hardware.md). You choose the screen during the [install](install.md), or later on the web interface's **Screen & system** page with **Change screen…**. In the config file it is `type` and `model` in `[display]` (see the [settings reference](settings.md#display)).

The tables on this page are made from epdlib's lists of models (epdlib is the library that drives the screens), so they always match the installed version.

## Is your screen tested? { #tested }

Only a few models have been tried on a real screen with PaperPi: they say "yes" under **Tested**. The others use Waveshare's own program code unchanged, so they should work, but nobody has checked yet. The web interface marks them "not tested yet", and at each start PaperPi writes a hint with a link to the report form in its log (also on the Warnings page).

**Please tell us how your screen works**, good or bad: the [screen report form](https://github.com/txoof/PaperPi/issues/new?template=screen-report.yml) takes a few minutes. The web interface's links to it fill in the model and PaperPi's version for you.

**Screen not in the list?** Use the same [form](https://github.com/txoof/PaperPi/issues/new?template=screen-report.yml) to ask for it, with the name and version from its box and a link to its page on waveshare.com. PaperPi uses a fixed, tested copy of Waveshare's program code (in epdlib), so a new model comes with an epdlib update.

## IT8951 screens { #it8951 }

Waveshare's larger screens with the IT8951 board, which shows 16 shades of gray. In the config file: `type = "it8951"`, `model` is the size in inches, and `vcom` is the number printed on the screen's ribbon cable.

<!-- made from epdlib: it8951 models -->

## Waveshare's small screens { #waveshare }

The screens on Waveshare's e-Paper HAT, without an IT8951 board. In the config file:

```toml
[display]
type = "waveshare"
model = "epd7in5_V2"   # from "All models" below
```

The model tells apart screens of the same size, for example `epd7in5` and `epd7in5_V2`. The size in inches is on the screen's box or the sticker on its back; "V2", "V3" and so on are printed there too. The installer turns on SPI (the data line to the screen) for you; without the installer: `sudo raspi-config nonint do_spi 0`, then restart the Pi.

### What to know

- **Faint picture,** with gray blacks and light streaks: check the HAT's **Display Config** switch ([Hardware](hardware.md#typical-non-it8951-pin-out)). Most screens need **B**; Waveshare's page for your screen (on [waveshare.com/wiki](https://www.waveshare.com/wiki/Main_Page)) says which one.
- **Fast writes:** only the 7.5" V2 has them now. A new picture from the plugin already on screen then takes about 4 seconds instead of 7; every 5th fast write in a row is a full one (`max_refresh = 4`). On every other model each picture is a full refresh, with the screen flashing black and white. That leaves no leftovers, so PaperPi doesn't clean these screens (`clean_every` and `max_refresh` are not used).
- **Three-colour screens** (models with "B" or "C" in the name, such as the 2.7" B) show only black and white for now. Red and yellow are epdlib issue [#96](https://github.com/txoof/epdlib/issues/96).
- **Colour screens** (the "F", "E" and "G" models: 4, 6 or 7 colours) draw in colour. `color = false` in `[display]` (**Draw in colour** on the web page) makes them draw in black and white.
- **Slow screens:** a full refresh takes about 7 seconds on the 7.5" V2, about 9 on the 5.83" and about 34 on the 5.65" colour screen.
<!-- made from epdlib: not working -->

### GPIO 18 and HiFiBerry sound cards

PaperPi uses **GPIO 18** (the PWR pin, which switches the screen's power on newer HATs) for every screen on the e-Paper HAT. HiFiBerry sound cards (and other sound cards that use I2S) need GPIO 18 too, so **a screen on the e-Paper HAT and a HiFiBerry can't be used on the same Pi** for now. epdlib issue [#109](https://github.com/txoof/epdlib/issues/109) is about fixing that. When PaperPi can't get the screen's pins, the error on the Warnings page and in the log names the pin. The IT8951 board doesn't use GPIO 18, so it works with a HiFiBerry.

### All models

Tested ones first, then by size. The name is Waveshare's: `7in5_V2` is the 7.5 inch screen, version 2. The config file uses the whole name of Waveshare's file (`model =`).

<!-- made from epdlib: waveshare models -->

## Virtual screen { #virtual }

`type = "virtual"`: no screen; every picture is saved as a PNG file. Any `width` and `height`, and a `mode`: <!-- made from epdlib: virtual modes -->. Without them it is like the 9.7" IT8951 screen.
