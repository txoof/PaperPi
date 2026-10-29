# Troubleshooting

## Where to look first

1. **The Warnings page** of the web interface. It lists what needs attention now, such as a plugin that keeps failing or a screen that does not answer, each with a button that helps. Below that are the latest warnings and errors.
2. **On the Pi**, if the web interface doesn't open:

    ```bash
    systemctl status paperpi          # is it running? "active (running)" means yes
    journalctl -u paperpi -n 50       # the last 50 lines of its log
    ```

## The screen stays blank or never changes

**Is PaperPi running?** Run `systemctl status paperpi`. If it says `failed`, PaperPi crashed 5 times within 10 minutes and systemd stopped trying. The log (`journalctl -u paperpi -n 50`) shows why. After fixing the cause, start it again:

```bash
sudo systemctl reset-failed paperpi
sudo systemctl start paperpi
```

**Does the screen answer?** On **Screen & system**, the Screen section says "✓ Answers", or that the screen does not answer. If it doesn't:

- Shut the Pi down (`sudo shutdown now`), unplug the power, and check the screen's ribbon cable and that the board sits firmly on all 40 pins. Never connect or disconnect anything while the Pi has power.
- Check that the screen type and model on **Screen & system** match your screen. **Change screen…** fixes them.
- Check that SPI is switched on: `ls /dev/spidev0.0` must show that file. If not, run `sudo raspi-config nonint do_spi 0` and restart the Pi.
- A small screen on the e-Paper HAT: check the HAT's **Display Config** switch (**B** for most screens) and **Interface Config** (**0**).
- A HiFiBerry sound card on the same Pi as the e-Paper HAT doesn't work: both need GPIO 18 ([more](waveshare-screens.md#gpio-18-and-hifiberry-sound-cards)).

When the screen stops answering while PaperPi runs, PaperPi pauses writing to it and tries again, with longer waits each time. **Try again now** on the Warnings page tries at once.

## The picture looks wrong

- **Faint, washed out or too dark (IT8951 screens):** the VCOM is probably wrong. It must be exactly the number printed on the screen's ribbon cable, with its minus sign. Change it with **Change screen…** on **Screen & system**.
- **Gray blacks or light streaks (small screens):** set the HAT's **Display Config** switch to the other position (with the Pi off). Waveshare's page for your screen says which one it needs.
- **Faint leftovers of earlier pictures:** e-paper keeps traces of what it showed before. **Refresh** on the Home page redraws the screen in full. To clean it more often, lower **Clean the screen every** under **Screen care** on **Screen & system**.
- **Upside down or sideways:** set **Rotation** on **Screen & system**.
- **Only black and white on a colour screen:** check that **Draw in colour** is on. Three-colour screens (red or yellow) show black and white only for now.

## The web interface doesn't open

- Use the phone or computer on the **same home network** as the Pi (not on mobile data).
- Type the address with `http://` and the port, for example `http://192.168.1.20:8080`. Not `https://`, and not a name such as `paperpi.local`: those don't work.
- The Pi's address can change when the router restarts. The screen shows the current one at every start of PaperPi; on the Pi, `hostname -I` prints it. Many routers can give the Pi a fixed address.
- After changing the port or address on **Screen & system**: run `sudo paperpi web-defaults` and `sudo systemctl restart paperpi` on the Pi. It goes back to port 8080, open to every device on your home network.
- Forgot the password: see [Forgotten password](web-interface.md#forgotten-password).

## A plugin is not shown

Look at its card on the Home page:

- **Off:** switch it on.
- **Configuration Required:** a required setting is missing; the card says which. Open **Settings** and fill it in.
- **Paused due to errors:** it failed 3 times in a row, so it is left out for 30 minutes. The Warnings page and the card show the error. Often the internet is down or a website doesn't answer; then it comes back by itself. **Try again now** tries at once.
- **Not used: has errors:** one of its settings is wrong. Open **Settings**: the wrong setting is marked.
- **Waiting:** it has nothing to show right now, which is normal for a music plugin while nothing plays, or its data isn't in yet. With an error next to it, the last try failed, and PaperPi tries again at its next refresh.

A weather plugin needs your real email address: met.no refuses made-up ones such as `you@example.com`.

How PaperPi chooses which plugin to show: [Understanding Plugin Schedules](take-turns.md).

## The config file has a mistake

If you edited `/etc/paperpi/paperpi.toml` by hand and it has a mistake, PaperPi keeps running with the settings it had, and the Warnings page shows the mistake with its line number. Fix the file, then press **Load the file again** (or run `sudo paperpi reload`). `sudo paperpi reload --check` only checks the file. **Review changes** in the web interface can also undo your hand edits.

## After an update

- Something still works the old way: run `sudo paperpi-install update` once more. The first update after a change to the install script still runs the old script ([more](update.md)).
- The new version has a problem: go back to the version before with `sudo paperpi-install update --ref v<version>`, for example `--ref v2.0.0`. Your settings stay.

## The Pi restarts or becomes slow

- A weak power supply can make the Pi restart, often while the screen draws. Use the official power supply for your Pi.
- A full SD card: `df -h /` shows the free space. PaperPi keeps 2 GB free and asks its plugins not to save more.

## Asking for help

Report a problem on GitHub with the [bug report form](https://github.com/txoof/PaperPi/issues/new?template=bug.yml). It asks for:

- **What happened:** what you did, what you expected, and what happened instead.
- **PaperPi's version:** on **Screen & system**, under **This Pi** (or `paperpi --version` on the Pi).
- **The Pi and the screen:** for example "Raspberry Pi 4, Waveshare 9.7 inch with IT8951".
- **The log:** **Download log** on the Warnings page (in the **Full log** tab), or `journalctl -u paperpi -n 200 > paperpi-log.txt` on the Pi. Check the log for anything private before you post it, such as calendar addresses.

For a small Waveshare screen that works badly, or not at all, use the [screen report form](https://github.com/txoof/PaperPi/issues/new?template=screen-report.yml) instead.
