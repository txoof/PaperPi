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

`paperpi example-config` prints an example config file that works as it is: a virtual screen, a clock, and the weather in Berlin and Rio. Every other setting is a comment with its default and a short help text. [paperpi.example.toml](paperpi.example.toml) is the same text.

```bash
uv run paperpi example-config -o paperpi.toml
uv run paperpi list --config paperpi.toml
```

`paperpi list` shows the plugins of a config file, one line each, in the order of the file: name, type, on or off, level, display time, refresh and layout (the ones used: the setting, or the plugin's own suggestion). Anything wrong with the file is shown first; a block with an error is left out of the list.

```
name            type         on   level     display  refresh  layout
Clock           basic_clock  yes  rotation  120 s    60 s     time
Weather Berlin  met_no       yes  rotation  120 s    1800 s   hours_12
Weather Rio     met_no       yes  rotation  120 s    1800 s   hours_12
```

### Run PaperPi without a screen

`paperpi run` shows the plugins of a config file, the way they will appear on the screen: they take turns, alerts and interrupts take over, failing plugins are skipped. Until the real screens are added, it only works with `type = "virtual"` in `[display]`: every screen write is saved as a numbered PNG file (the newest 50 are kept), and the newest is also `latest.png`. The numbers start again at `0001.png` at every start, so the files of an earlier run are removed first.

```bash
uv run paperpi run --config paperpi.toml --out screen/ --state-dir state/ --health-file /run/user/$(id -u)/paperpi-health
```

- It runs until Ctrl+C, or until it gets the stop signal (`kill <process id>`).
- After changing the config file, send it the reload signal SIGHUP (a standard message to a running program, here meaning "read your settings again"): `kill -HUP <process id>`. The process id is printed at the start. Use exactly that number: `pkill -f` would also reach PaperPi's helper processes and stop them. Once PaperPi is installed as a service (M6), `systemctl reload paperpi` does the same. Changes are applied without a restart; a broken file is not applied, and the old settings keep running.
- While it runs, it says "still running" every 30 seconds: to systemd, when it runs as a service, and in the file `/run/paperpi/health`. Only root or the service can make `/run/paperpi`, so the example above uses `--health-file` to put the file in your own folder in `/run/user/`, which is also kept in memory (a file that can't be written is only a warning). `paperpi health` (with the same `--health-file`) prints the last report and ends with an error when there is no report or the last one is more than 2 minutes old. Once an hour the same values (time since the last screen write, memory use, open files, free disk) also go to the log, starting with a `health:` line at the start. If PaperPi gets stuck, systemd (or Docker, from M6) uses this to restart it: [docs/decisions/errors-and-time-limits.md](docs/decisions/errors-and-time-limits.md).
- `--state-dir` holds the plugins' own folders and the last good copy of the config (default `/var/lib/paperpi`). The PNG files go to `screen/` in it, unless `--out` names another folder.

When no plugin has anything to show (e.g. no music is playing), a small clock is shown at the bottom of the screen, so you can tell the screen still works. `fallback_clock = false` in `[display]` switches it off, which is not recommended.

Which plugin is shown and when: [docs/decisions/plugin-scheduling.md](docs/decisions/plugin-scheduling.md). The `debugging` plugin can crash, hang and switch states on purpose, to try this out.

See [CLAUDE.md](CLAUDE.md) for how work is organized.
