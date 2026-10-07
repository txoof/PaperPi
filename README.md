# PaperPi

> **Looking for the working version?** PaperPi version 1 is on the [`v1` branch](https://github.com/txoof/PaperPi/tree/v1). See its [install instructions](https://github.com/txoof/PaperPi/blob/v1/README.md). The last state of version 1 is marked with the tag [`v1-final`](https://github.com/txoof/PaperPi/tree/v1-final).

PaperPi shows information (weather, clocks, music, comics and more) on e-paper displays attached to a Raspberry Pi.

## Status: version 2 is being rewritten

This branch (`main`) holds PaperPi **version 2**, which is being written from scratch. It is not usable yet.

### What version 2 will add
- Support for the IT8951 displays (such as the Waveshare 9.7") on Raspberry Pi OS "trixie"
- A web page for changing settings and plugin options, with a preview before sending to the display
- Settings changes without a restart
- Installation with one command, using Docker (a tool that runs a program together with everything it needs, separate from the rest of the system)
- Generated documentation with example images for every plugin

Progress is tracked in [milestones](https://github.com/txoof/PaperPi/milestones).

## Development

PaperPi needs Python 3.13, the version in Raspberry Pi OS "trixie".

It uses [uv](https://docs.astral.sh/uv/), a tool that installs the right Python version and all the packages PaperPi needs into a separate folder (`.venv`), and [ruff](https://docs.astral.sh/ruff/), a tool that checks code style.

On the Pi, first install a C compiler and Python's header files: `sudo apt install gcc python3-dev`. `spidev`, the library for SPI (the data line to the screen), is built during the install. It and `gpiod` (for the screen's pins) are only installed on Linux, so on other computers PaperPi works with the virtual screen only.

```bash
uv sync                    # install everything
uv run pytest              # run the tests (tests that need a real display are skipped)
uv run pytest -m hardware  # run only the tests that need a real display (on the Pi)
uv run ruff check .        # check code style
uv run ruff format .       # fix code formatting
```

### Draw a plugin without a screen

`paperpi render` draws one plugin to a PNG file. It needs no screen and no config file, and with the plugin's sample data (the default) also no network:

```bash
uv run paperpi render basic_clock                    # writes basic_clock.png (1200x825, gray16)
uv run paperpi render basic_clock --layout time_date --set hours=12 --size 800x480 --mode bw
uv run paperpi render basic_clock --live             # real data (here: the current time)
```

It can also draw one `[[plugin]]` block from a config file, at the size and colours of its `[display]` part. A complete small config file:

```toml
config_version = 1

[display]
type = "virtual"      # no screen: PNG files only
width = 800
height = 480
mode = "bw"

[[plugin]]
name = "Clock"
type = "basic_clock"
layout = "time_date"
```

```bash
uv run paperpi render --config paperpi.toml --name "Clock"   # writes clock.png, named after the plugin's name
```

Run `uv run paperpi render --help` for all options. How to write a plugin: [docs/writing-plugins.md](docs/writing-plugins.md).

### A config file

`paperpi example-config` prints an example config file that works as it is: a virtual screen, a clock, and the weather in Berlin and Rio. Every other setting is a comment with its default and a short help text. [paperpi.example.toml](paperpi.example.toml) is the same text. Before you use the weather blocks, put your own email address in `email` (met.no asks for it). `-o` doesn't replace a file that is already there, unless you add `--force`.

```bash
uv run paperpi example-config -o paperpi.toml
uv run paperpi list --config paperpi.toml
```

`paperpi list` shows the plugins of a config file, one line each, in the order of the file: name, type, on or off, level, display time, refresh, layout and storage (the ones used: the setting, or else the plugin's suggestion or first layout; storage is the size limit and the age limit, for example `500 MB, 30 d`, or `500 MB, no age limit`). Anything wrong with the file is shown first; a block with an error is left out of the list.

```
name            type         on   level     display  refresh  layout
Clock           basic_clock  yes  rotation  120 s    60 s     time
Weather Berlin  met_no       yes  rotation  120 s    1800 s   hours_12
Weather Rio     met_no       yes  rotation  120 s    1800 s   hours_12
```

### Run PaperPi without a screen

`paperpi run` shows the plugins of a config file, the way they will appear on the screen: they take turns, alerts and interrupts take over, failing plugins are skipped. With `type = "virtual"` in `[display]`, every screen write is saved as a numbered PNG file (the newest 50 are kept), and the newest is also `latest.png`. The numbers start again at `0001.png` at every start, so the files of an earlier run are removed first. The first write after a start, and the first write after each hour, first clear the screen (a white PNG; on a real screen this removes leftovers of earlier images); `clean_every = 0` switches this off. When PaperPi is stopped on purpose, the screen is cleared, so `latest.png` is white afterwards; `on_exit = "keep"` keeps the last image.

```bash
uv run paperpi run --config paperpi.toml --out screen/ --state-dir state/ --health-file /run/user/$(id -u)/paperpi-health
```

- It runs until Ctrl+C, or until it gets the stop signal (`kill <process id>`).
- After changing the config file, send it the reload signal SIGHUP (a standard message to a running program, here meaning "read your settings again"): `kill -HUP <process id>`. The process id is printed at the start. Use exactly that number: `pkill -f` would also reach PaperPi's helper processes and stop them. Once PaperPi is installed as a service (M6), `systemctl reload paperpi` does the same. Changes are applied without a restart; a broken file is not applied, and the old settings keep running.
- While it runs, it says "still running" every 30 seconds: to systemd, when it runs as a service, and in the file `/run/paperpi/health`. Only root or the service can make `/run/paperpi`, so the example above uses `--health-file` to put the file in your own folder in `/run/user/`, which is also kept in memory (a file that can't be written is only a warning). `paperpi health` (with the same `--health-file`) prints the last report and ends with an error when there is no report or the last one is more than 2 minutes old. Once an hour the same values (time since the last screen write, whether screen writes work, memory use, open files, free disk) also go to the log, starting with a `health:` line at the start. If PaperPi gets stuck, systemd (or Docker, from M6) uses this to restart it: [docs/decisions/errors-and-time-limits.md](docs/decisions/errors-and-time-limits.md).
- `--state-dir` holds the plugins' own folders, the last good copy of the config and the time PaperPi last exited because of a stuck screen (default `/var/lib/paperpi`). The PNG files go to `screen/` in it, unless `--out` names another folder.

### The web interface

`paperpi run` also starts the web interface, on port 8080: open `http://<the Pi's name or address>:8080` (for example `http://paperpi.local:8080`) on a phone or computer on the same home network. For now it has the log-in and an empty home page; the pages for plugins and settings follow (issue #238).

- **First visit:** the first person to open it sets the web password (at least 8 characters). The browser then stays logged in for a year, until **Log out**.
- **Forgotten password:** you need access to the Pi itself (a keyboard and screen, or SSH).
  1. Run `sudo paperpi reset-password` (add `--config <file>` for another config file). It removes the `password_hash` line from `[web]` in the config file and leaves the rest of the file as it is. Removing the line by hand does the same.
  2. Restart PaperPi, or send it the reload signal (`kill -HUP <process id>`, or `sudo systemctl reload paperpi` once it is a service).
  3. Open the web interface and set a new password. Until then, anyone on your home network can set it.
  A new password logs out every browser.
- **No password at all:** `login = false` in `[web]`. Then anyone on your home network can change PaperPi's settings; the home page says so.
- **Other `[web]` settings:** `enabled = false` (no web interface; `paperpi run --no-web` does the same for one run), `port`, and `address = "127.0.0.1"` to reach it from the Pi only. These three apply at the next start; `login` and the password apply at a reload.
- It uses plain HTTP, not HTTPS: it is for the home network only. Do not open it to the internet.
- If the port is taken by another program, the log says so and PaperPi runs without the web interface.

### Run PaperPi on the 9.7" IT8951 screen

Turn on SPI first: `sudo raspi-config nonint do_spi 0` (the same as raspi-config's menu Interface Options, SPI; `0` means on), then reboot. See epdlib's `docs/it8951.md`. Then set the screen in `[display]`. `vcom` is printed on the screen's ribbon cable; each screen has its own:

```toml
[display]
type = "it8951"
model = "9.7"
vcom = -1.90
```

Then start `paperpi run` as above, as a user in the `spi` and `gpio` groups (the first user on Raspberry Pi OS already is; otherwise `sudo usermod -aG spi,gpio $USER`, then log in again). A new image from the plugin already on screen is a fast refresh of only the changed area. Another plugin gets a full refresh, and so does every 5th fast refresh in a row (`max_refresh = 4`). If the screen does not answer at start, the error is in the log and PaperPi keeps running and tries again.

When no plugin has anything to show (e.g. no music is playing), a small clock is shown at the bottom of the screen, so you can tell the screen still works. `fallback_clock = false` in `[display]` switches it off, which is not recommended.

Which plugin is shown and when: [docs/decisions/plugin-scheduling.md](docs/decisions/plugin-scheduling.md). The `debugging` plugin can crash, hang and switch states on purpose, to try this out.

See [CLAUDE.md](CLAUDE.md) for how work is organized.
