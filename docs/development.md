# Running from source

This page is for working on PaperPi's code, or trying it out without installing it. It runs PaperPi from a copy of the code, on a Raspberry Pi or another computer. To install PaperPi on a Raspberry Pi for everyday use, see [Install](install.md) instead.

## Set up

PaperPi needs Python 3.13, the version in Raspberry Pi OS "trixie", and two tools:

- [uv](https://docs.astral.sh/uv/) installs the right Python version and all the packages PaperPi needs, in a folder of its own (`.venv`).
- [ruff](https://docs.astral.sh/ruff/) checks the code's style; uv installs it.

On a Raspberry Pi, first install a C compiler and Python's header files, which are needed to build the library for the screen's data line (`spidev`):

```bash
sudo apt install gcc python3-dev
```

Then get the code and install everything:

```bash
git clone https://github.com/txoof/PaperPi.git
cd PaperPi
uv sync
```

On a computer that is not a Raspberry Pi, the libraries for the screen are left out, so PaperPi works with the virtual screen only: it saves pictures instead of showing them.

The everyday commands:

| Command | What it does |
|---|---|
| `uv run pytest -n auto` | run all tests, on every processor core |
| `uv run pytest tests/test_<name>.py` | run the tests of one part |
| `uv run pytest -m hardware` | run the tests that need a real screen (on the Pi) |
| `uv run ruff check .` | check the code's style |
| `uv run ruff format .` | fix the code's layout |

## Draw a plugin to a picture

`paperpi render` draws one plugin and saves it as a PNG file. It needs no screen and no config file. With the plugin's made-up sample data (the default) it needs no network either:

```bash
uv run paperpi render basic_clock                    # writes basic_clock.png (1200x825, 16 grays)
uv run paperpi render basic_clock --layout time_date --set hours=12 --size 800x480 --mode bw
uv run paperpi render basic_clock --live             # real data (here: the current time)
```

`uv run paperpi render --help` lists every option. To make a plugin of your own: [Writing a plugin](writing-plugins.md).

## Make a config file

PaperPi's settings are in one config file. `paperpi example-config` writes an example: a virtual screen, a clock, and the weather for Berlin and Rio. Every other setting is in it as a comment, with its default and a help text. What every setting means: [Settings reference](settings.md).

```bash
uv run paperpi example-config -o paperpi.toml
uv run paperpi list --config paperpi.toml
```

The weather blocks are not shown until you fill in your own email address in them (remove the `#` in front of `email`): met.no, the weather service, asks for one. `paperpi list` shows each plugin on one line, with "needs email" until then:

```
name            type         on   level     display  refresh  layout
Clock           basic_clock  yes  rotation  120 s    60 s     time
Weather Berlin  met_no       yes  rotation  120 s    1800 s   hours_12
Weather Rio     met_no       yes  rotation  120 s    1800 s   hours_12
```

A small config file looks like this:

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

Every `[[plugin]]` block has its own `id`: the plugin's type and 8 random letters and digits. It names the plugin's folder for saved files. The web interface and `example-config` make it for you. `paperpi render --config paperpi.toml --id basic_clock-5c1e0a7b` draws one block of a config file.

## Run PaperPi

`paperpi run` shows the plugins of a config file, as they will appear on a screen: they take turns, interrupts and alerts take over, and failing plugins are skipped. It also starts the web interface, at `http://<the computer's address>:8080`.

```bash
uv run paperpi run --config paperpi.toml --state-dir state --health-file state/health
```

It runs until you press Ctrl+C. The options:

| Option | What it is |
|---|---|
| `--config` | the config file (default `/etc/paperpi/paperpi.toml`) |
| `--state-dir` | the folder for what PaperPi keeps: the plugins' saved files, the log file, the last good copy of the config, the Plugin Library's example pictures (default `/var/lib/paperpi`) |
| `--health-file` | where PaperPi writes its health report every 30 seconds (default `/run/paperpi/health`, which only the service can write) |
| `--out` | the folder for the virtual screen's pictures (default `screen/` in the state folder) |
| `--no-web` | no web interface |
| `-v` | show every log line in the terminal, not only warnings and errors |

**The virtual screen** saves every picture as a numbered PNG file (the newest 50), and the newest also as `latest.png`. The numbers start again at every start. Like a real screen, it is cleaned (a white picture) at the first write and then once an hour, and made blank when PaperPi stops.

**After changing the config file,** run `paperpi reload` with the same options. It tells the running PaperPi to read the file again and use the changes, without a restart, and prints what changed. A file with a mistake is not used: it prints the mistake and its line, and the old settings keep running. `--check` only checks.

```bash
uv run paperpi reload --config paperpi.toml --state-dir state --health-file state/health
```

**Health:** `uv run paperpi health --health-file state/health` prints the last health report: when the screen was last written, memory use, open files, free disk. It ends with an error when the report is more than 2 minutes old, which is how systemd notices that PaperPi is stuck. Once an hour the same values also go to the log.

**Logs:** warnings and errors go to the terminal, and to `paperpi.log` in the state folder (at most about 2 MB, with the older `paperpi.log.1`). The web interface shows them on its Warnings page.

**The web interface's password and address,** when they are lost:

```bash
uv run paperpi reset-password --config paperpi.toml                   # then paperpi reload, or start paperpi run again
uv run paperpi web-defaults --config paperpi.toml --state-dir state   # then start paperpi run again
```

## Run it on a real screen

On a Raspberry Pi with a screen connected ([Hardware](hardware.md)):

1. Switch on SPI, the data line to the screen: `sudo raspi-config nonint do_spi 0`, then restart the Pi.
2. Run PaperPi as a user in the `spi` and `gpio` groups. The first user on Raspberry Pi OS already is; otherwise `sudo usermod -aG spi,gpio $USER`, then log in again.
3. Set the screen in the config file's `[display]` part, and start `paperpi run` as above.

For a screen with the IT8951 board, `vcom` is the number printed on the screen's ribbon cable:

```toml
[display]
type = "it8951"
model = "9.7"
vcom = -1.90
```

For a small screen on the e-Paper HAT, the model is the name of Waveshare's file for it (all names: [Supported screens](screens.md#waveshare)):

```toml
[display]
type = "waveshare"
model = "epd7in5_V2"
```

If the screen doesn't answer at start, the error is in the log, and PaperPi keeps running and tries again. More about the screens: epdlib's [IT8951 guide](https://github.com/txoof/epdlib/blob/main/docs/it8951.md) and [Waveshare screens](waveshare-screens.md).

To try how PaperPi handles plugins that crash, hang or come and go, add the `debugging` plugin: it does all of these on purpose. How the plugins take turns: [Understanding Plugin Schedules](take-turns.md).

## Work on the manual

This website is made from the Markdown files in `docs/` by [MkDocs](https://www.mkdocs.org/), with the [Material](https://squidfunk.github.io/mkdocs-material/) theme. The menu is in `mkdocs.yml`.

```bash
uv run --group docs mkdocs serve              # then open http://127.0.0.1:8000
uv run --group docs mkdocs build --strict     # stops on a broken link, as the check on GitHub does
```

`serve` shows every saved change at once. On the Pi, add `-a 0.0.0.0:8000` to open it from another computer on your home network.

Some pages are made from the code while the site is built, so they always match it: the settings reference, the supported screens, and a page for each plugin (its README, its settings and its sample pictures). `src/paperpi/manual.py` writes them and `mkdocs_hooks.py` adds them. To change a plugin's page, change its README or the help texts of its settings.

Write every page for people: plain sentences, steps, examples and pictures. The design notes in `docs/decisions/` are working notes for the people and agents building PaperPi, and are not part of the site.

GitHub builds the site for every pull request, and publishes it at <https://txoof.github.io/PaperPi/> after every merge to `main`.

## How the work is organised

Issues, pull requests and the rules for both are described in [CLAUDE.md](https://github.com/txoof/PaperPi/blob/main/CLAUDE.md).
