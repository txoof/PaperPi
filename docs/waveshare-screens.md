# Waveshare's small screens

PaperPi can drive Waveshare's small e-paper screens: the ones that plug into Waveshare's e-Paper HAT (the board that sits on the Pi's pins) and have no IT8951 board. The driver comes from epdlib (see epdlib's `docs/waveshare.md` for how it works).

## Set it up

1. **Switch the Pi off** and plug the HAT onto the Pi, with the screen's ribbon cable in the HAT.
2. **Set the HAT's two small switches:**
   - **Display Config: B** for most screens. Waveshare's page for your screen (on [waveshare.com/wiki](https://www.waveshare.com/wiki/Main_Page)) says which one it needs. With the wrong setting the picture can be faint, with gray blacks and light streaks.
   - **Interface Config: 0** (4-line SPI, which PaperPi uses).
3. **Install PaperPi** ([Install](install.md)): its screen menu asks for the board, the size and the model, and turns on SPI (the data line to the screen). Without the installer: `sudo raspi-config nonint do_spi 0`, then reboot.
4. **Or choose the screen later:** on the web interface's **Screen & system** page, **Change screen…**, type **Waveshare small screen**, then the model. Or in the config file:

   ```toml
   [display]
   type = "waveshare"
   model = "epd7in5_V2"   # the name of Waveshare's file for the screen: see Supported screens
   ```

   The model is the name of Waveshare's program file for the screen, which tells apart screens of the same size (for example `epd7in5` and `epd7in5_V2`). The size in inches is on the screen's box or the sticker on its back; "V2", "V3" and so on are printed there too.

PaperPi then uses the screen from its next start.

## Tested and untested models

Only a few models have been tried on a real screen with PaperPi (Tested: yes on [Supported screens](screens.md#waveshare)). The others use Waveshare's own program code unchanged, so they should work, but nobody has checked yet. The web interface marks them "not tested yet", and at each start PaperPi writes a hint with a link to the report form in its log (also on the Warnings page).

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

The list of every model, with its size, colours and whether it was tested, is on [Supported screens](screens.md#waveshare). It is made from epdlib's list of models, so it always matches the installed version.
