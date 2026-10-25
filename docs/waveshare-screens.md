# Waveshare's small screens

PaperPi can drive Waveshare's small e-paper screens: the ones that plug into Waveshare's e-Paper HAT (the board that sits on the Pi's pins) and have no IT8951 board. The driver comes from epdlib (see epdlib's `docs/waveshare.md` for how it works).

## Set it up

1. **Switch the Pi off** and plug the HAT onto the Pi, with the screen's ribbon cable in the HAT.
2. **Set the HAT's two small switches:**
   - **Display Config: B** for most screens. Waveshare's page for your screen (on [waveshare.com/wiki](https://www.waveshare.com/wiki/Main_Page)) says which one it needs. With the wrong setting the picture can be faint, with gray blacks and light streaks.
   - **Interface Config: 0** (4-line SPI, which PaperPi uses).
3. **Turn on SPI** (the data line to the screen): `sudo raspi-config nonint do_spi 0`, then reboot.
4. **Choose the screen:** on the web interface's **Screen & system** page, **Change screen…**, type **Waveshare small screen**, then the model. Or in the config file:

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

## What to know

- **Fast writes:** only the 7.5" V2 has them now. A new picture from the plugin already on screen then takes about 4 seconds instead of 7; every 5th fast write in a row is a full one (`max_refresh = 4`). On every other model each picture is a full refresh, with the screen flashing black and white. That leaves no leftovers, so PaperPi doesn't clean these screens (`clean_every` and `max_refresh` are not used).
- **Three-colour screens** (models with "B" or "C" in the name, such as the 2.7" B) show only black and white for now. Red and yellow are epdlib issue [#96](https://github.com/txoof/epdlib/issues/96).
- **Colour screens** (the "F", "E" and "G" models: 4, 6 or 7 colours) draw in colour. `color = false` in `[display]` (**Draw in colour** on the web page) makes them draw in black and white.
- **Slow screens:** a full refresh takes about 7 seconds on the 7.5" V2, about 9 on the 5.83" and about 34 on the 5.65" colour screen.
- **Not working:** the 4.2" B V2 (`epd4in2b_V2`, and its older version) sends its data in a way epdlib can't use, so PaperPi refuses it.

## GPIO 18 and HiFiBerry sound cards

Newer Waveshare HATs switch the screen's power on and off with **GPIO 18** (the PWR pin), and PaperPi uses it. HiFiBerry sound cards (and other sound cards that use I2S) need GPIO 18 too, so **a Waveshare screen and a HiFiBerry can't be used on the same Pi** for now. epdlib issue [#109](https://github.com/txoof/epdlib/issues/109) is about fixing that. When PaperPi can't get the screen's pins, the error on the Warnings page and in the log names the pin.

## All models

Tested ones first, then by size.

| Model | `model =` | Size (pixels) | Shows | Fast writes | Tested |
|---|---|---|---|---|---|
| 5.65" F | `epd5in65f` | 600 × 448 | 7 colours | no | yes |
| 5.83" | `epd5in83` | 600 × 448 | black and white | no | yes |
| 7.5" V2 | `epd7in5_V2` | 800 × 480 | black and white | yes | yes |
| 1.02" | `epd1in02` | 128 × 80 | black and white | no | no |
| 1.54" | `epd1in54` | 200 × 200 | black and white | no | no |
| 1.54" B | `epd1in54b` | 200 × 200 | black and white (3-colour screen, see below) | no | no |
| 1.54" C | `epd1in54c` | 152 × 152 | black and white (3-colour screen, see below) | no | no |
| 1.54" V2 | `epd1in54_V2` | 200 × 200 | black and white | no | no |
| 1.54" B V2 | `epd1in54b_V2` | 200 × 200 | black and white (3-colour screen, see below) | no | no |
| 1.64" G | `epd1in64g` | 168 × 168 | 4 colours | no | no |
| 2.13" | `epd2in13` | 250 × 122 | black and white | no | no |
| 2.13" B/C | `epd2in13bc` | 212 × 104 | black and white (3-colour screen, see below) | no | no |
| 2.13" D | `epd2in13d` | 212 × 104 | black and white | no | no |
| 2.13" G | `epd2in13g` | 250 × 122 | 4 colours | no | no |
| 2.13" V2 | `epd2in13_V2` | 250 × 122 | black and white | no | no |
| 2.13" V3 | `epd2in13_V3` | 250 × 122 | black and white | no | no |
| 2.13" B V3 | `epd2in13b_V3` | 212 × 104 | black and white (3-colour screen, see below) | no | no |
| 2.13" V4 | `epd2in13_V4` | 250 × 122 | black and white | no | no |
| 2.13" B V4 | `epd2in13b_V4` | 250 × 122 | black and white (3-colour screen, see below) | no | no |
| 2.15" B | `epd2in15b` | 296 × 160 | black and white (3-colour screen, see below) | no | no |
| 2.15" G | `epd2in15g` | 296 × 160 | 4 colours | no | no |
| 2.36" G | `epd2in36g` | 296 × 168 | 4 colours | no | no |
| 2.66" | `epd2in66` | 296 × 152 | black and white | no | no |
| 2.66" B | `epd2in66b` | 296 × 152 | black and white (3-colour screen, see below) | no | no |
| 2.66" G | `epd2in66g` | 360 × 184 | 4 colours | no | no |
| 2.7" | `epd2in7` | 264 × 176 | black and white | no | no |
| 2.7" B | `epd2in7b` | 264 × 176 | black and white (3-colour screen, see below) | no | no |
| 2.7" V2 | `epd2in7_V2` | 264 × 176 | black and white | no | no |
| 2.7" B V2 | `epd2in7b_V2` | 264 × 176 | black and white (3-colour screen, see below) | no | no |
| 2.9" | `epd2in9` | 296 × 128 | black and white | no | no |
| 2.9" B/C | `epd2in9bc` | 296 × 128 | black and white (3-colour screen, see below) | no | no |
| 2.9" D | `epd2in9d` | 296 × 128 | black and white | no | no |
| 2.9" V2 | `epd2in9_V2` | 296 × 128 | black and white | no | no |
| 2.9" V3 | `epd2in9_V3` | 296 × 128 | black and white | no | no |
| 2.9" B V3 | `epd2in9b_V3` | 296 × 128 | black and white (3-colour screen, see below) | no | no |
| 2.9" B V4 | `epd2in9b_V4` | 296 × 128 | black and white (3-colour screen, see below) | no | no |
| 3.0" G | `epd3in0g` | 400 × 168 | 4 colours | no | no |
| 3.52" | `epd3in52` | 360 × 240 | black and white | no | no |
| 3.7" | `epd3in7` | 480 × 280 | black and white | no | no |
| 4.01" F | `epd4in01f` | 640 × 400 | 7 colours | no | no |
| 4.2" | `epd4in2` | 400 × 300 | black and white | no | no |
| 4.2" B/C | `epd4in2bc` | 400 × 300 | black and white (3-colour screen, see below) | no | no |
| 4.2" V2 | `epd4in2_V2` | 400 × 300 | black and white | no | no |
| 4.26" | `epd4in26` | 800 × 480 | black and white | no | no |
| 4.37" G | `epd4in37g` | 512 × 368 | 4 colours | no | no |
| 5.79" | `epd5in79` | 792 × 272 | black and white | no | no |
| 5.79" B | `epd5in79b` | 792 × 272 | black and white (3-colour screen, see below) | no | no |
| 5.79" G | `epd5in79g` | 792 × 272 | 4 colours | no | no |
| 5.83" B/C | `epd5in83bc` | 600 × 448 | black and white (3-colour screen, see below) | no | no |
| 5.83" V2 | `epd5in83_V2` | 648 × 480 | black and white | no | no |
| 5.83" B V2 | `epd5in83b_V2` | 648 × 480 | black and white (3-colour screen, see below) | no | no |
| 7.3" E | `epd7in3e` | 800 × 480 | 6 colours | no | no |
| 7.3" F | `epd7in3f` | 800 × 480 | 7 colours | no | no |
| 7.3" G | `epd7in3g` | 800 × 480 | 4 colours | no | no |
| 7.5" | `epd7in5` | 640 × 384 | black and white | no | no |
| 7.5" HD | `epd7in5_HD` | 880 × 528 | black and white | no | no |
| 7.5" B HD | `epd7in5b_HD` | 880 × 528 | black and white (3-colour screen, see below) | no | no |
| 7.5" B/C | `epd7in5bc` | 640 × 384 | black and white (3-colour screen, see below) | no | no |
| 7.5" V2 (old) | `epd7in5_V2_old` | 800 × 480 | black and white | no | no |
| 7.5" B V2 | `epd7in5b_V2` | 800 × 480 | black and white (3-colour screen, see below) | no | no |
| 7.5" B V2 (old) | `epd7in5b_V2_old` | 800 × 480 | black and white (3-colour screen, see below) | no | no |
| 13.3" B | `epd13in3b` | 960 × 680 | black and white (3-colour screen, see below) | no | no |
| 13.3" K | `epd13in3k` | 960 × 680 | black and white | no | no |
