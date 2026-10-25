# Waveshare's small screens

PaperPi can drive Waveshare's small e-paper screens: the ones that plug into Waveshare's e-Paper HAT (the board that sits on the Pi's pins) and have no IT8951 board. The driver comes from epdlib (see epdlib's `docs/waveshare.md` for how it works).

## Set it up

1. **Switch the Pi off** and plug the HAT onto the Pi, with the screen's ribbon cable in the HAT.
2. **Set the HAT's two small switches:**
   - **Display Config: B** for most screens. Waveshare's page for your screen (on [waveshare.com/wiki](https://www.waveshare.com/wiki/Main_Page)) says which one it needs. With the wrong setting the picture can be faint, with gray blacks and light streaks.
   - **Interface Config: 0** (4-line SPI, which PaperPi uses).
3. **Install PaperPi** ([install-systemd.md](install-systemd.md)): its screen menu asks for the board, the size and the model, and turns on SPI (the data line to the screen). Without the installer: `sudo raspi-config nonint do_spi 0`, then reboot.
4. **Or choose the screen later:** on the web interface's **Screen & system** page, **Change screen…**, type **Waveshare small screen**, then the model. Or in the config file:

   ```toml
   [display]
   type = "waveshare"
   model = "epd7in5_V2"   # the name of Waveshare's file for the screen: see the table below
   ```

   The model is the name of Waveshare's program file for the screen, which tells apart screens of the same size (for example `epd7in5` and `epd7in5_V2`). The size in inches is on the screen's box or the sticker on its back; "V2", "V3" and so on are printed there too.

PaperPi then uses the screen from its next start.

## Tested and untested models

Only a few models have been tried on a real screen with PaperPi (Tested: yes in the table). The others use Waveshare's own program code unchanged, so they should work, but nobody has checked yet. The web interface marks them "not tested yet", and at each start PaperPi writes a hint with a link to the report form in its log (also on the Warnings page).

**Please tell us how your screen works**, good or bad: the [screen report form](https://github.com/txoof/PaperPi/issues/new?template=screen-report.yml) takes a few minutes. The web interface's links to it fill in the model and PaperPi's version for you.

**Screen not in the list?** Use the same [form](https://github.com/txoof/PaperPi/issues/new?template=screen-report.yml) to ask for it, with the name and version from its box and a link to its page on waveshare.com. PaperPi uses a fixed, tested copy of Waveshare's program code (in epdlib), so a new model comes with an epdlib update.

## What to know

- **Fast writes:** only the 7.5" V2 has them now. A new picture from the plugin already on screen then takes about 4 seconds instead of 7; every 5th fast write in a row is a full one (`max_refresh = 4`). On every other model each picture is a full refresh, with the screen flashing black and white. That leaves no leftovers, so PaperPi doesn't clean these screens (`clean_every` and `max_refresh` are not used).
- **Three-colour screens** (models with "B" or "C" in the name, such as the 2.7" B) show only black and white for now. Red and yellow are epdlib issue [#96](https://github.com/txoof/epdlib/issues/96).
- **Colour screens** (the "F", "E" and "G" models: 4, 6 or 7 colours) draw in colour. `color = false` in `[display]` (**Draw in colour** on the web page) makes them draw in black and white.
- **Slow screens:** a full refresh takes about 7 seconds on the 7.5" V2, about 9 on the 5.83" and about 34 on the 5.65" colour screen.
- **Not working:** the 4.2" B V2 (`epd4in2b_V2`, and its older version) sends its data in a way epdlib can't use, so PaperPi refuses it.

## GPIO 18 and HiFiBerry sound cards

Newer Waveshare HATs switch the screen's power on and off with **GPIO 18** (the PWR pin), and PaperPi uses it. HiFiBerry sound cards (and other sound cards that use I2S) need GPIO 18 too, so **a Waveshare screen and a HiFiBerry can't be used on the same Pi** for now. epdlib issue [#109](https://github.com/txoof/epdlib/issues/109) is about fixing that. When PaperPi can't get the screen's pins, the error on the Warnings page and in the log names the pin.

## All models

Tested ones first, then by size. The name is Waveshare's notation, as on their program files and in PaperPi's menus: `7in5_V2` is the 7.5 inch screen, version 2. The config file uses the whole file name (`model =`).

| Name | `model =` | Size (pixels) | Shows | Fast writes | Tested |
|---|---|---|---|---|---|
| 5in65f | `epd5in65f` | 600 × 448 | 7 colours | no | yes |
| 5in83 | `epd5in83` | 600 × 448 | black and white | no | yes |
| 7in5_V2 | `epd7in5_V2` | 800 × 480 | black and white | yes | yes |
| 1in02 | `epd1in02` | 128 × 80 | black and white | no | no |
| 1in54 | `epd1in54` | 200 × 200 | black and white | no | no |
| 1in54_V2 | `epd1in54_V2` | 200 × 200 | black and white | no | no |
| 1in54b | `epd1in54b` | 200 × 200 | black and white (3-colour screen, see above) | no | no |
| 1in54b_V2 | `epd1in54b_V2` | 200 × 200 | black and white (3-colour screen, see above) | no | no |
| 1in54c | `epd1in54c` | 152 × 152 | black and white (3-colour screen, see above) | no | no |
| 1in64g | `epd1in64g` | 168 × 168 | 4 colours | no | no |
| 2in13 | `epd2in13` | 250 × 122 | black and white | no | no |
| 2in13_V2 | `epd2in13_V2` | 250 × 122 | black and white | no | no |
| 2in13_V3 | `epd2in13_V3` | 250 × 122 | black and white | no | no |
| 2in13_V4 | `epd2in13_V4` | 250 × 122 | black and white | no | no |
| 2in13b_V3 | `epd2in13b_V3` | 212 × 104 | black and white (3-colour screen, see above) | no | no |
| 2in13b_V4 | `epd2in13b_V4` | 250 × 122 | black and white (3-colour screen, see above) | no | no |
| 2in13bc | `epd2in13bc` | 212 × 104 | black and white (3-colour screen, see above) | no | no |
| 2in13d | `epd2in13d` | 212 × 104 | black and white | no | no |
| 2in13g | `epd2in13g` | 250 × 122 | 4 colours | no | no |
| 2in15b | `epd2in15b` | 296 × 160 | black and white (3-colour screen, see above) | no | no |
| 2in15g | `epd2in15g` | 296 × 160 | 4 colours | no | no |
| 2in36g | `epd2in36g` | 296 × 168 | 4 colours | no | no |
| 2in66 | `epd2in66` | 296 × 152 | black and white | no | no |
| 2in66b | `epd2in66b` | 296 × 152 | black and white (3-colour screen, see above) | no | no |
| 2in66g | `epd2in66g` | 360 × 184 | 4 colours | no | no |
| 2in7 | `epd2in7` | 264 × 176 | black and white | no | no |
| 2in7_V2 | `epd2in7_V2` | 264 × 176 | black and white | no | no |
| 2in7b | `epd2in7b` | 264 × 176 | black and white (3-colour screen, see above) | no | no |
| 2in7b_V2 | `epd2in7b_V2` | 264 × 176 | black and white (3-colour screen, see above) | no | no |
| 2in9 | `epd2in9` | 296 × 128 | black and white | no | no |
| 2in9_V2 | `epd2in9_V2` | 296 × 128 | black and white | no | no |
| 2in9_V3 | `epd2in9_V3` | 296 × 128 | black and white | no | no |
| 2in9b_V3 | `epd2in9b_V3` | 296 × 128 | black and white (3-colour screen, see above) | no | no |
| 2in9b_V4 | `epd2in9b_V4` | 296 × 128 | black and white (3-colour screen, see above) | no | no |
| 2in9bc | `epd2in9bc` | 296 × 128 | black and white (3-colour screen, see above) | no | no |
| 2in9d | `epd2in9d` | 296 × 128 | black and white | no | no |
| 3in0g | `epd3in0g` | 400 × 168 | 4 colours | no | no |
| 3in52 | `epd3in52` | 360 × 240 | black and white | no | no |
| 3in7 | `epd3in7` | 480 × 280 | black and white | no | no |
| 4in01f | `epd4in01f` | 640 × 400 | 7 colours | no | no |
| 4in2 | `epd4in2` | 400 × 300 | black and white | no | no |
| 4in2_V2 | `epd4in2_V2` | 400 × 300 | black and white | no | no |
| 4in2bc | `epd4in2bc` | 400 × 300 | black and white (3-colour screen, see above) | no | no |
| 4in26 | `epd4in26` | 800 × 480 | black and white | no | no |
| 4in37g | `epd4in37g` | 512 × 368 | 4 colours | no | no |
| 5in79 | `epd5in79` | 792 × 272 | black and white | no | no |
| 5in79b | `epd5in79b` | 792 × 272 | black and white (3-colour screen, see above) | no | no |
| 5in79g | `epd5in79g` | 792 × 272 | 4 colours | no | no |
| 5in83_V2 | `epd5in83_V2` | 648 × 480 | black and white | no | no |
| 5in83b_V2 | `epd5in83b_V2` | 648 × 480 | black and white (3-colour screen, see above) | no | no |
| 5in83bc | `epd5in83bc` | 600 × 448 | black and white (3-colour screen, see above) | no | no |
| 7in3e | `epd7in3e` | 800 × 480 | 6 colours | no | no |
| 7in3f | `epd7in3f` | 800 × 480 | 7 colours | no | no |
| 7in3g | `epd7in3g` | 800 × 480 | 4 colours | no | no |
| 7in5 | `epd7in5` | 640 × 384 | black and white | no | no |
| 7in5_HD | `epd7in5_HD` | 880 × 528 | black and white | no | no |
| 7in5_V2_old | `epd7in5_V2_old` | 800 × 480 | black and white | no | no |
| 7in5b_HD | `epd7in5b_HD` | 880 × 528 | black and white (3-colour screen, see above) | no | no |
| 7in5b_V2 | `epd7in5b_V2` | 800 × 480 | black and white (3-colour screen, see above) | no | no |
| 7in5b_V2_old | `epd7in5b_V2_old` | 800 × 480 | black and white (3-colour screen, see above) | no | no |
| 7in5bc | `epd7in5bc` | 640 × 384 | black and white (3-colour screen, see above) | no | no |
| 13in3b | `epd13in3b` | 960 × 680 | black and white (3-colour screen, see above) | no | no |
| 13in3k | `epd13in3k` | 960 × 680 | black and white | no | no |
