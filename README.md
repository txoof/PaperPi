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

`paperpi render` draws one plugin to a PNG file. It needs no screen, no network and no config file:

```bash
uv run paperpi render basic_clock                    # writes basic_clock.png (1200x825, 16 grays)
uv run paperpi render basic_clock --layout time_date --set hours=12 --size 800x480 --mode bw
uv run paperpi render basic_clock --live             # real data (here: the current time)
uv run paperpi render --config paperpi.toml --name "Clock"   # one [[plugin]] block from a config file
```

By default it uses the plugin's sample data. Run `uv run paperpi render --help` for all options. How to write a plugin: [docs/writing-plugins.md](docs/writing-plugins.md).

See [CLAUDE.md](CLAUDE.md) for how work is organized.
