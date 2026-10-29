# PaperPi

PaperPi shows information on an e-paper screen attached to a Raspberry Pi: clocks, the weather, your calendar, what music is playing, comics, public transport departures and more. You set it up in a web page on your phone or computer.

**The manual: <https://txoof.github.io/PaperPi/>**

## Version 1 is no longer maintained

This branch (`main`) holds PaperPi **version 2**, a rewrite from scratch. Version 1 gets no fixes, and version 2 does not read its config files. Its code stays on the [`v1` branch](https://github.com/txoof/PaperPi/tree/v1), with the last state marked by the tag [`v1-final`](https://github.com/txoof/PaperPi/tree/v1-final).

## Install on a Raspberry Pi

PaperPi needs a Raspberry Pi 3 or 4 with Raspberry Pi OS "trixie", and a screen with Waveshare's IT8951 board (such as the Waveshare 9.7") or one of Waveshare's small screens. One command installs PaperPi as a systemd service (it starts with the Pi and is started again after a crash). It asks which screen is connected:

```bash
curl -fsSL https://raw.githubusercontent.com/txoof/PaperPi/main/install/paperpi-install | sudo bash
```

What you need, the install step by step, and how to update and remove PaperPi: [Install](https://txoof.github.io/PaperPi/install/).

## Development

PaperPi needs Python 3.13 and [uv](https://docs.astral.sh/uv/) (a tool that installs the right Python version and all the packages into `.venv`):

```bash
uv sync                    # install everything
uv run pytest -n auto      # run the tests
uv run paperpi render basic_clock   # draw a plugin to basic_clock.png, without a screen
uv run paperpi new-plugin my_plugin # start a plugin of your own from the template
```

More in the manual: [Running from source](https://txoof.github.io/PaperPi/development/), [Writing plugins](https://txoof.github.io/PaperPi/writing-plugins/). See [CLAUDE.md](CLAUDE.md) for how work is organized.
