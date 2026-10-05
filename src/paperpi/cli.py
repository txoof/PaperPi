"""The ``paperpi`` command.

``paperpi render <plugin>`` draws one plugin to a PNG file, without a screen. By default it
uses the plugin's sample data and default settings, so it needs no network and no config
file. Run ``paperpi render --help`` for all options.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import tomllib
from pathlib import Path

from pydantic import ValidationError

from . import __version__, config, limits, plugins
from .plugin import Context, PluginDefinitionError, State
from .runner import PluginFailed, run_update

log = logging.getLogger("paperpi")

SIZE = f"{config.VIRTUAL_WIDTH}x{config.VIRTUAL_HEIGHT}"


class UsageError(Exception):
    """A wrong command line or setting; the message says what to change."""


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    try:
        return args.command(args)
    except UsageError as error:
        print(f"paperpi: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperpi", description="PaperPi " + __version__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--verbose", action="store_true", help="show details while running")
    parser.set_defaults(command=lambda args: parser.print_help() or 2)
    commands = parser.add_subparsers(title="commands")

    render = commands.add_parser(
        "render",
        help="draw a plugin to a PNG file, without a screen",
        description=(
            "Draw a plugin to a PNG file, without a screen. By default it uses the plugin's "
            "sample data and default settings. With --config it draws one [[plugin]] block "
            "from a config file, at the size and colours of its [display]."
        ),
    )
    render.add_argument("plugin", nargs="?", help=f"plugin type: {', '.join(plugins.available())}")
    render.add_argument("--config", type=Path, help="config file to read the plugin from")
    render.add_argument("--name", help='with --config: the plugin\'s name, e.g. "Clock"')
    render.add_argument(
        "--size",
        help=f'width x height in pixels (default: {SIZE}, the 9.7" screen)',
    )
    render.add_argument(
        "--mode",
        choices=config.MODES,
        help=f"what the screen can show (default: {config.VIRTUAL_MODE})",
    )
    render.add_argument("--layout", help="layout name (default: the plugin's first)")
    render.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="SETTING=VALUE",
        help="change one of the plugin's settings, e.g. --set hours=12 (repeat for more)",
    )
    render.add_argument("--live", action="store_true", help="use real data, not the sample")
    render.add_argument("--time-limit", type=float, help="seconds the update may take")
    render.add_argument("-o", "--output", type=Path, help="PNG file to write")
    render.set_defaults(command=_render)
    return parser


def _render(args: argparse.Namespace) -> int:
    if args.config is not None:
        if args.plugin or args.name is None:
            raise UsageError('with --config, give the plugin\'s name: --name "Clock"')
        if args.set or args.size or args.mode:
            raise UsageError("with --config, settings, size and mode come from the config file")
        job = _job_from_config(args)
    else:
        if not args.plugin:
            raise UsageError("which plugin? e.g. paperpi render basic_clock")
        job = _job_from_options(args)
    plugin_type, settings, layout, width, height, mode, time_limit, output = job
    if args.layout is not None:
        layout = args.layout
    plugin = plugins.load(plugin_type)
    if layout not in plugin.layouts:
        raise UsageError(f"unknown layout {layout!r}; choose from: {', '.join(plugin.layouts)}")
    if args.time_limit is not None:
        time_limit = args.time_limit
    if not 0 < time_limit <= limits.PLUGIN_UPDATE_MAX:
        raise UsageError(f"--time-limit must be above 0 and at most {limits.PLUGIN_UPDATE_MAX:g}")

    with tempfile.TemporaryDirectory(prefix="paperpi-render-") as storage:
        context = Context(settings, width, height, mode, Path(storage), layout)
        try:
            result = run_update(plugin_type, context, sample=not args.live, time_limit=time_limit)
        except PluginFailed as error:
            print(f"paperpi: {error}", file=sys.stderr)
            if error.details:
                log.debug("%s", error.details)
            return 1
    if result.state is State.NOTHING:
        print(f"{plugin_type} has nothing to show right now; no image written")
        return 0
    output = args.output or output
    result.image.save(output)
    alert = " (alert)" if result.state is State.ALERT else ""
    shades = "" if mode.kind in ("bw", "rgb") else f" {mode.levels}"
    print(
        f"saved {output}: {width}x{height} {mode.kind}{shades}, {layout}{alert}, "
        f"{result.seconds:.2f} s"
    )
    return 0


def _job_from_options(args: argparse.Namespace):
    try:
        plugin = plugins.load(args.plugin)
    except KeyError:
        raise UsageError(
            f"unknown plugin {args.plugin!r}; known: {', '.join(plugins.available())}"
        ) from None
    except PluginDefinitionError as error:
        raise UsageError(f"the plugin itself is broken: {error}") from None
    values = dict(_parse_set(item) for item in args.set)
    unknown = sorted(set(values) - set(plugin.settings.model_fields))
    if unknown:
        known = ", ".join(plugin.settings.model_fields) or "none"
        raise UsageError(f"unknown setting {', '.join(unknown)}; {args.plugin} has: {known}")
    try:
        settings = plugin.settings.model_validate(values)
    except ValidationError as error:
        problems = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in error.errors())
        raise UsageError(problems) from None
    width, height = _parse_size(args.size or SIZE)
    output = Path(f"{plugin.type}.png")
    mode = config.MODES[args.mode or config.VIRTUAL_MODE]
    return (
        plugin.type,
        settings,
        plugin.default_layout,
        width,
        height,
        mode,
        limits.PLUGIN_UPDATE,
        output,
    )


def _job_from_config(args: argparse.Namespace):
    try:
        loaded = config.load(args.config, state_dir=None)
    except config.ConfigError as error:
        raise UsageError(f"the config file can't be used:\n{error}") from None
    try:
        found = loaded.plugin(args.name)
    except KeyError:
        names = ", ".join(repr(p.entry.name) for p in loaded.plugins) or "none"
        raise UsageError(
            f"no usable plugin named {args.name!r} in {args.config} (problems are shown "
            f"above); plugins without errors: {names}"
        ) from None
    width, height = loaded.display.layout_size
    mode = loaded.display.screen_mode
    output = Path(f"{found.folder_name}.png")
    return (
        found.plugin.type,
        found.settings,
        found.layout,
        width,
        height,
        mode,
        found.entry.time_limit,
        output,
    )


def _parse_set(item: str) -> tuple[str, object]:
    key, sep, value = item.partition("=")
    if not sep or not key.strip():
        raise UsageError(f"--set needs SETTING=VALUE, got {item!r}")
    try:
        parsed = tomllib.loads(f"v = {value}")["v"]  # numbers, true/false, "text"
    except tomllib.TOMLDecodeError:
        parsed = value  # plain text without quotes
    return key.strip(), parsed


def _parse_size(text: str) -> tuple[int, int]:
    width, sep, height = text.lower().partition("x")
    try:
        size = (int(width), int(height))
    except ValueError:
        size = (0, 0)
    if not sep or not all(0 < n <= 10_000 for n in size):
        raise UsageError(f"--size must be WIDTHxHEIGHT, e.g. 1200x825; got {text!r}")
    return size
