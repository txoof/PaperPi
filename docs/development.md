# Running from source

This page is for working on PaperPi's code, or trying it without installing it: it runs PaperPi from a copy of the repository. To install PaperPi on a Raspberry Pi, see [Install](install.md).

## Set up

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

## Draw a plugin without a screen

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
id = "basic_clock-5c1e0a7b"
type = "basic_clock"
layout = "time_date"
```

Every `[[plugin]]` block has its own `id`, which names the plugin's storage folder. The web interface and `paperpi example-config` make it: the plugin type and 8 random letters and digits, as in the examples here.

```bash
uv run paperpi render --config paperpi.toml --id basic_clock-5c1e0a7b   # writes basic-clock-5c1e0a7b.png, named after the plugin's ID
```

Run `uv run paperpi render --help` for all options. How to write a plugin: [Writing plugins](writing-plugins.md).

## A config file

`paperpi example-config` prints an example config file that loads without errors: a virtual screen, a clock, and weather blocks for Berlin and Rio. Every other setting is a comment with its default and a short help text. [paperpi.example.toml](https://github.com/txoof/PaperPi/blob/main/paperpi.example.toml) is the same text, except that the printed copy gives each plugin a new random `id`. The weather blocks are not shown until you remove the `#` in front of `email` and fill in your own, real email address: met.no's terms of service ask for it, so the example leaves it empty. Until then `paperpi list` shows them as "needs email". `-o` doesn't replace a file that is already there, unless you add `--force`.

```bash
uv run paperpi example-config -o paperpi.toml
uv run paperpi list --config paperpi.toml
```

`paperpi list` shows the plugins of a config file, one line each, in the order of the file: id, name (the id when it has none), type, on (`yes`, `no`, or `needs <settings>` when a required setting is missing), level, display time, refresh, layout and storage (the ones used: the setting, or else the plugin's suggestion or first layout; storage is the size limit and the age limit, for example `500 MB, 30 d`, or `500 MB, no age limit`). Anything wrong with the file is shown first; a block with an error is left out of the list.

```
name            type         on   level     display  refresh  layout
Clock           basic_clock  yes  rotation  120 s    60 s     time
Weather Berlin  met_no       yes  rotation  120 s    1800 s   hours_12
Weather Rio     met_no       yes  rotation  120 s    1800 s   hours_12
```

## Run PaperPi without a screen

`paperpi run` shows the plugins of a config file, the way they will appear on the screen: they take turns, alerts and interrupts take over, failing plugins are skipped. With `type = "virtual"` in `[display]`, every screen write is saved as a numbered PNG file (the newest 50 are kept), and the newest is also `latest.png`. The numbers start again at `0001.png` at every start, so the files of an earlier run are removed first. The first write after a start, and the first write after each hour, first clear the screen (a white PNG; on a real screen this removes leftovers of earlier images); `clean_every = 0` switches this off. When PaperPi is stopped on purpose, the screen is cleared, so `latest.png` is white afterwards; `on_exit = "keep"` keeps the last image.

```bash
uv run paperpi run --config paperpi.toml --out screen/ --state-dir state/ --health-file /run/user/$(id -u)/paperpi-health
```

- It runs until Ctrl+C, or until it gets the stop signal (`kill <process id>`).
- After changing the config file, run `paperpi reload`. It tells the running PaperPi to read the file again and apply the changes without a restart, and prints what changed (the same list as the web interface's Review changes page). A file with a mistake is not applied: it prints the mistake with its line, and the old settings keep running. It ends with exit status 0 when the changes were applied, else 1. `paperpi reload --check` only prints the mistakes and the changes, and applies nothing. It finds PaperPi by the process id in the health report, which PaperPi writes to `/run/paperpi/health`; started by hand, PaperPi may not write there, so give both commands the same `--health-file` (and `--config` and `--state-dir`), for example `paperpi run --config my.toml --state-dir state --health-file state/health`, then `paperpi reload --config my.toml --state-dir state --health-file state/health`. Once PaperPi is installed as a service ([Install](install.md)), use `sudo paperpi reload` (`sudo systemctl reload paperpi` does the same, but shows no details). Instead of `paperpi reload`, the reload signal SIGHUP (a standard message to a running program, here meaning "read your settings again") does the same without the report: `kill -HUP <process id>`. The process id is printed at the start. Use exactly that number: `pkill -f` would also reach PaperPi's helper processes and stop them.
- While it runs, it says "still running" every 30 seconds: to systemd, when it runs as a service, and in the file `/run/paperpi/health`. Only root or the service can make `/run/paperpi`, so the example above uses `--health-file` to put the file in your own folder in `/run/user/`, which is also kept in memory (a file that can't be written is only a warning). `paperpi health` (with the same `--health-file`) prints the last report and ends with an error when there is no report or the last one is more than 2 minutes old. Once an hour the same values (time since the last screen write, whether screen writes work, memory use, open files, free disk) also go to the log, starting with a `health:` line at the start. If PaperPi gets stuck, systemd uses this to restart it.
- **Logs:** warnings and errors go to the terminal (with `-v`, every line), or the system log when PaperPi runs as a service. They are also kept in `paperpi.log` in the state folder (at most about 2 MB with the older `paperpi.log.1`). The web interface shows them on its Warnings page ([more](web-interface.md#warnings)).
- `--state-dir` holds the plugins' own folders, the log file, the last good copy of the config, the Plugin Library's example pictures (`library-pictures/`, a few hundred KB) and the time PaperPi last exited because of a stuck screen (default `/var/lib/paperpi`). The PNG files go to `screen/` in it, unless `--out` names another folder.

## The web interface

`paperpi run` also starts the web interface, on port 8080 (`[web] port`; `--no-web` runs without it). What its pages do: [The web interface](web-interface.md). The commands for a lost password and a lost address need the same files as `paperpi run` here:

```bash
uv run paperpi reset-password --config paperpi.toml    # then restart paperpi run, or paperpi reload
uv run paperpi web-defaults --config paperpi.toml --state-dir state   # then restart paperpi run
```

## Run PaperPi on the 9.7" IT8951 screen

Turn on SPI first: `sudo raspi-config nonint do_spi 0` (the same as raspi-config's menu Interface Options, SPI; `0` means on), then reboot. See epdlib's [IT8951 guide](https://github.com/txoof/epdlib/blob/main/docs/it8951.md). Then set the screen in `[display]`. `vcom` is printed on the screen's ribbon cable; each screen has its own:

```toml
[display]
type = "it8951"
model = "9.7"
vcom = -1.90
```

Then start `paperpi run` as above, as a user in the `spi` and `gpio` groups (the first user on Raspberry Pi OS already is; otherwise `sudo usermod -aG spi,gpio $USER`, then log in again). A new image from the plugin already on screen is a fast refresh of only the changed area. Another plugin gets a full refresh, and so does every 5th fast refresh in a row (`max_refresh = 4`). If the screen does not answer at start, the error is in the log and PaperPi keeps running and tries again.

## Run PaperPi on a small Waveshare screen

Waveshare's small screens (1.02" to 13.3", on Waveshare's e-Paper HAT, without an IT8951 board) work too: set the HAT's **Display Config** switch to **B** for most screens, turn on SPI as above, and set the screen's model, the name of Waveshare's file for it. [Waveshare screens](waveshare-screens.md) has the steps, every model, and which ones were tested:

```toml
[display]
type = "waveshare"
model = "epd7in5_V2"
```

At start, PaperPi first shows its name, version and the address of its web interface (with a QR code to open it on a phone) for a minute, while the plugins get their first pictures. `splash_time` in `[display]` sets how long, in seconds (`0`: not at all). With no plugin ready to show, for example right after installing, it stays on screen until one is, so the address to set PaperPi up is always there.

When no plugin has anything to show (e.g. no music is playing), a small clock is shown at the bottom of the screen, so you can tell the screen still works. `fallback_clock = false` in `[display]` switches it off, which is not recommended.

Which plugin is shown and when: [How plugins take turns](take-turns.md). The `debugging` plugin can crash, hang and switch states on purpose, to try this out.

## The manual

This website is made from the Markdown files in `docs/` by [MkDocs](https://www.mkdocs.org/) with the [Material](https://squidfunk.github.io/mkdocs-material/) theme. The menu is set in `mkdocs.yml`. To see it while writing, with every saved change shown at once:

```bash
uv run --group docs mkdocs serve      # then open http://127.0.0.1:8000
uv run --group docs mkdocs build --strict   # what the docs workflow runs: a broken link is an error
```

Some pages are made from the code while the site is built, so they always match it: the settings reference, the supported screens, and the list of plugins with a page for each (the plugin's README, its settings and its sample pictures). `src/paperpi/manual.py` writes them, and `mkdocs_hooks.py` adds them to the site. To change a plugin's page, change its README or the descriptions of its settings.

On the Pi, add `-a 0.0.0.0:8000` to `serve` to open it from another computer on the home network, at the Pi's address. `.github/workflows/docs.yml` builds the site for every PR and publishes it to <https://txoof.github.io/PaperPi/> on every merge to `main`.

See [CLAUDE.md](https://github.com/txoof/PaperPi/blob/main/CLAUDE.md) for how work is organized.
