# PaperPi

PaperPi shows information (weather, clocks, music, comics and more) on e-paper displays attached to a Raspberry Pi.

## Status: version 2 is being rewritten

This branch (`main`) holds PaperPi **version 2**, which is being written from scratch. It is not usable yet.

**Looking for the working version?** PaperPi version 1 is on the [`v1` branch](https://github.com/txoof/PaperPi/tree/v1) (last state tagged [`v1-final`](https://github.com/txoof/PaperPi/releases/tag/v1-final)). Its install instructions are in the README on that branch.

### What version 2 will add
- Support for the IT8951 displays (such as the Waveshare 9.7") on Raspberry Pi OS "trixie"
- A web page for changing settings and plugin options, with a preview before sending to the display
- Settings changes without a restart
- Installation with one command (Docker)
- Generated documentation with example images for every plugin

Progress is tracked in [milestones](https://github.com/txoof/PaperPi/milestones).

## Development

PaperPi uses [uv](https://docs.astral.sh/uv/) to manage Python and its dependencies.

```bash
uv sync                 # create the environment and install everything
uv run pytest           # run the tests
uv run ruff check .     # check code style
```

See [CLAUDE.md](CLAUDE.md) for how work is organized.
