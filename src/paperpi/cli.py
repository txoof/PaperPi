"""The ``paperpi`` command.

- ``paperpi render <plugin>`` draws one plugin to a PNG file, without a screen. By default it
  uses the plugin's sample data and default settings, so it needs no network and no config
  file.
- ``paperpi run`` shows the plugins of a config file: it runs the scheduler until it is
  stopped. With ``type = "virtual"`` it writes PNG files; with ``type = "it8951"`` or
  ``"waveshare"`` it writes to the real screen.
- ``paperpi list`` shows the plugins of a config file; ``paperpi example-config`` prints an
  example config file.
- ``paperpi reset-password`` removes the web password, so a new one can be set in the web
  interface.
- ``paperpi web-defaults`` puts the web interface back on its default address and port,
  for when a new address or port in the web interface can't be reached.
- ``paperpi health`` says whether ``paperpi run`` still reports "healthy"; Docker's health
  check uses it.
- ``paperpi reload`` tells the running ``paperpi run`` to apply changes to the config file,
  and prints what changed, or the mistake that stops it (:mod:`paperpi.reload`).
- ``paperpi new-plugin <type>`` starts a new plugin from the template
  (:mod:`paperpi.newplugin`).

Run ``paperpi <command> --help`` for all options.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from epdlib import ScreenMode
from pydantic import ValidationError

from . import (
    __version__,
    config,
    example,
    health,
    limits,
    logbook,
    newplugin,
    plugins,
    reload,
    storage,
)
from .files import write_atomic
from .plugin import Context, Plugin, PluginSettings, State
from .runner import PluginFailed, run_update
from .scheduler import Scheduler
from .screen import Screen, ScreenStuck, driver_for
from .web import config_file, keep
from .web.password import PasswordError, save_password_hash

log = logging.getLogger("paperpi")

SIZE = f"{config.VIRTUAL_WIDTH}x{config.VIRTUAL_HEIGHT}"
#: ``paperpi run``'s exit status after "Restart PaperPi" in the web interface. The service
#: (install/paperpi.service) counts it as a clean stop and starts PaperPi again.
RESTART_STATUS = 75


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
    render.add_argument("--id", help="with --config: the plugin's ID, e.g. clock")
    render.add_argument(
        "--size",
        help=f'WIDTHxHEIGHT in pixels, e.g. 800x480 (default: {SIZE}, the 9.7" screen)',
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

    run = commands.add_parser(
        "run",
        help="show the plugins of a config file, until stopped",
        description=(
            "Show the plugins of a config file: run the scheduler until Ctrl+C or the "
            "service is stopped. The virtual screen saves every screen write as a PNG file "
            "(the newest is latest.png). paperpi reload (or the signal SIGHUP) applies "
            "changes to the config file."
        ),
    )
    run.add_argument(
        "--config", type=Path, default=config.CONFIG_FILE, help=f"default: {config.CONFIG_FILE}"
    )
    run.add_argument(
        "--out", type=Path, help="folder for the PNG files (default: screen/ in --state-dir)"
    )
    run.add_argument(
        "--state-dir",
        type=Path,
        default=config.STATE_DIR,
        help=(
            "folder for plugin files, the last good config and the screen-stuck time "
            f"({config.STATE_DIR})"
        ),
    )
    run.add_argument(
        "--health-file",
        type=Path,
        default=health.HEALTH_FILE,
        help=f"where to write the health report (default: {health.HEALTH_FILE})",
    )
    run.add_argument(
        "--no-web", action="store_true", help="don't start the web interface (see [web])"
    )
    run.set_defaults(command=_run)

    listing = commands.add_parser(
        "list",
        help="show the plugins of a config file",
        description=(
            "Show the plugins of a config file, one line each, in the order of the file. "
            "Anything wrong with the file is shown first; a block with an error is not in the "
            "list. Refresh and layout are the ones used: the setting, or else the plugin's "
            'suggested refresh and its first layout. The "on" column says "needs '
            '<settings>" for a plugin that is switched on but not shown, because a required '
            "setting is missing."
        ),
    )
    listing.add_argument(
        "--config", type=Path, default=config.CONFIG_FILE, help=f"default: {config.CONFIG_FILE}"
    )
    listing.set_defaults(command=_list)

    sample = commands.add_parser(
        "example-config",
        help="print an example config file",
        description=(
            "Print an example config file that works as it is: a clock and the weather in two "
            "places, with every other setting as a comment with its default and help text. "
            "Each plugin gets a new random ID. With --setup: the first config of a new install."
        ),
    )
    sample.add_argument("-o", "--output", type=Path, help="file to write instead of printing")
    sample.add_argument(
        "--setup",
        action="store_true",
        help="the first config of a new install instead: a clock and a screen that asks to set "
        "PaperPi up in the web interface",
    )
    sample.add_argument("--display", default="virtual", help="[display] type (default: virtual)")
    sample.add_argument("--model", help='[display] model, e.g. "9.7"')
    sample.add_argument("--vcom", type=float, help="[display] vcom, e.g. -1.90 (it8951)")
    sample.add_argument(
        "--force", action="store_true", help="with -o: replace the file if it is already there"
    )
    sample.add_argument(
        "--fixed-ids",
        action="store_true",
        help="keep the example's fixed plugin IDs (to make paperpi.example.toml again)",
    )
    sample.set_defaults(command=_example_config)

    new = commands.add_parser(
        "new-plugin",
        help="start a new plugin from the template",
        description=(
            "Make the folder of a new plugin in src/paperpi/plugins/ from PaperPi's template: "
            "a small working plugin that shows a greeting and today's date. Then change it "
            "into your own plugin: https://txoof.github.io/PaperPi/writing-plugins/"
        ),
    )
    new.add_argument("type", help="the plugin's type: lowercase letters, digits and _")
    new.add_argument("--title", help="its name in the web interface (default: from the type)")
    new.set_defaults(command=_new_plugin)

    check = commands.add_parser(
        "health",
        help='check that "paperpi run" is still running its loop',
        description=(
            "Check the health report of paperpi run. Ends with exit status 0 (healthy) when "
            f"the last report is at most {limits.HEALTH_STALE:.0f} s old, else 1 (the number a "
            "program returns to say it failed). Docker's health check uses this command."
        ),
    )
    check.add_argument(
        "--health-file",
        type=Path,
        default=health.HEALTH_FILE,
        help=f"the health report to check (default: {health.HEALTH_FILE})",
    )
    check.set_defaults(command=_health)

    again = commands.add_parser(
        "reload",
        help="apply changes to the config file to the running PaperPi",
        description=(
            "Tell the running paperpi run to load the config file again, without a restart, "
            "and print what changed. A file with a mistake is not applied: the mistake is "
            "printed and the old settings keep running. Ends with exit status 0 when the "
            "changes were applied, else 1. PaperPi is found by the process id in its health "
            "report. Use the same --config, --state-dir and --health-file as paperpi run. "
            "As a service, run it with sudo."
        ),
    )
    again.add_argument(
        "--config", type=Path, default=config.CONFIG_FILE, help=f"default: {config.CONFIG_FILE}"
    )
    again.add_argument(
        "--state-dir",
        type=Path,
        default=config.STATE_DIR,
        help=f"where the last good copy of the config is, to list the changes ({config.STATE_DIR})",
    )
    again.add_argument(
        "--health-file",
        type=Path,
        default=health.HEALTH_FILE,
        help=f"the health report of paperpi run (default: {health.HEALTH_FILE})",
    )
    again.add_argument(
        "--check",
        action="store_true",
        help="only print the mistakes and the changes; send nothing (PaperPi need not run)",
    )
    again.set_defaults(command=_reload)

    reset = commands.add_parser(
        "reset-password",
        help="remove the web password, for when it is forgotten",
        description=(
            "Remove the web password (password_hash in [web]) from the config file; the rest "
            "of the file stays as it is. Run it with sudo when the config file belongs to "
            "root, as in /etc/paperpi. Then restart PaperPi, or run paperpi reload (sudo "
            "paperpi reload once it runs as a service), and open the web interface to set a "
            "new password. Until then, anyone "
            "on the home network can set it."
        ),
    )
    reset.add_argument(
        "--config", type=Path, default=config.CONFIG_FILE, help=f"default: {config.CONFIG_FILE}"
    )
    reset.set_defaults(command=_reset_password)

    defaults = commands.add_parser(
        "web-defaults",
        help="put the web interface back on port 8080 for every device",
        description=(
            "Take the web interface's address and port out of [web] in the config file, so "
            "it uses the defaults again: port 8080, for every device on the home network. "
            "For when the web interface can't be reached after a change. The rest of the "
            "file stays as it is. Run it with sudo when the config file belongs to root, as "
            "in /etc/paperpi. Then restart PaperPi."
        ),
    )
    defaults.add_argument(
        "--config", type=Path, default=config.CONFIG_FILE, help=f"default: {config.CONFIG_FILE}"
    )
    defaults.add_argument(
        "--state-dir",
        type=Path,
        default=config.STATE_DIR,
        help=(
            "PaperPi's state folder, where the old web address is kept: the same as for "
            f"paperpi run ({config.STATE_DIR})"
        ),
    )
    defaults.set_defaults(command=_web_defaults)
    return parser


@dataclass(frozen=True)
class _Job:
    """What to render, from the command line or from a config file."""

    plugin: Plugin
    settings: PluginSettings
    layout: str
    width: int
    height: int
    mode: ScreenMode
    time_limit: float
    output: Path


def _render(args: argparse.Namespace) -> int:
    if args.config is not None:
        if args.plugin:
            raise UsageError(f"give either a plugin type ({args.plugin!r}) or --config, not both")
        if args.id is None:
            raise UsageError("with --config, give the plugin's ID, e.g. --id basic_clock-5c1e0a7b")
        if args.set or args.size or args.mode:
            raise UsageError("with --config, settings, size and mode come from the config file")
        job = _job_from_config(args)
    else:
        if args.id is not None:
            raise UsageError("--id only works together with --config")
        if not args.plugin:
            raise UsageError("which plugin? e.g. paperpi render basic_clock")
        job = _job_from_options(args)
    layout = job.layout if args.layout is None else args.layout
    if layout not in job.plugin.layouts:
        known = ", ".join(job.plugin.layouts)
        raise UsageError(f"unknown layout {layout!r}; choose from: {known}")
    missing = job.plugin.missing(job.settings)
    if args.live and missing:
        sets = " ".join(f"--set {k}=..." for k in missing)
        raise UsageError(f"{job.plugin.type} needs these required settings: {sets}")
    time_limit = job.time_limit if args.time_limit is None else args.time_limit
    if not 0 < time_limit <= limits.PLUGIN_UPDATE_MAX:
        raise UsageError(f"--time-limit must be above 0 and at most {limits.PLUGIN_UPDATE_MAX:g}")

    plugin_type = job.plugin.type
    # Each render gets a new, empty storage folder, deleted afterwards.
    with tempfile.TemporaryDirectory(prefix="paperpi-render-") as storage:
        context = Context(job.settings, job.width, job.height, job.mode, Path(storage), layout)
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
    output = args.output or job.output
    try:
        result.image.save(output, format="PNG")
    except OSError as error:
        raise UsageError(f"can't write {output}: {error}") from None
    alert = " (alert)" if result.state is State.ALERT else ""
    print(
        f"saved {output}: {job.width}x{job.height} {config.mode_name(job.mode)}, "
        f"{layout}{alert}, {result.seconds:.2f} s"
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    book = logbook.start(args.state_dir, verbose=args.verbose)
    log.info("PaperPi %s starts, process id %d", __version__, os.getpid(), extra=logbook.KEEP)
    status = 1
    try:
        status = _keep_running(args, book)
    except Exception:
        log.critical("PaperPi crashed", exc_info=True)
    finally:
        log.info("PaperPi stops (exit status %d)", status, extra=logbook.KEEP)
        logbook.stop(book)
    return status


def _keep_running(args: argparse.Namespace, book: logbook.Logbook) -> int:
    # A reload signal during start-up would otherwise end the program.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    web = None

    def load() -> config.Config:
        loaded = config.load(args.config, state_dir=args.state_dir)
        if web is not None and not loaded.from_last_good:
            web.use(loaded)
        return loaded

    try:
        loaded = load()
    except config.ConfigError as error:
        print(f"paperpi: the config file can't be used:\n{error}", file=sys.stderr)
        return 1
    display = loaded.display
    out = args.out or args.state_dir / "screen"
    if display.type == "virtual":
        # The numbers start again at 0001 at every start, so files of an earlier run go.
        for old in [*out.glob("[0-9][0-9][0-9][0-9].png"), out / "latest.png"]:
            old.unlink(missing_ok=True)
    storage.clean_all(loaded.plugins, args.state_dir)
    # The driver is made and used in the screen helper process (paperpi.screen).
    screen = Screen(
        driver_for(display, out),
        color=display.screen_mode.kind in ("palette", "rgb"),
        stuck_file=args.state_dir / "screen-stuck",
    )
    # Taken out of the environment, so plugin processes can't send "still running" for a
    # stuck loop.
    notify_socket = os.environ.pop("NOTIFY_SOCKET", None)
    reports = health.Health(args.health_file, disk=args.state_dir, notify_socket=notify_socket)
    scheduler = Scheduler(
        loaded,
        screen,
        state_dir=args.state_dir,
        reload=load,
        health=reports.report,
        reloaded=reports.reloaded,
        new_driver=lambda changed: driver_for(changed, out),
    )
    signal.signal(signal.SIGTERM, lambda *_: scheduler.stop())
    signal.signal(signal.SIGINT, lambda *_: scheduler.stop())
    signal.signal(signal.SIGHUP, lambda *_: scheduler.reload())
    if loaded.web.enabled and not args.no_web:
        # Imported here: the web packages take a moment to load, and no other command needs them.
        from .web import server

        web = server.start(
            args.config,
            loaded.web,
            reload=scheduler.reload,
            text=None if loaded.from_last_good else loaded.text,
            state_dir=args.state_dir,
            display=display,
            controls=scheduler,
            logbook=book,
        )
        if web is not None:
            print(f"web interface on port {web.port}")
    try:
        with screen:
            count = sum(1 for p in loaded.plugins if p.shown and p.plugin.type != "default")
            where = f"images in {out}" if display.type == "virtual" else f"screen {display.type}"
            print(
                f"showing {count} plugin{'' if count == 1 else 's'}; {where}; "
                f"process id {os.getpid()} (paperpi reload or kill -HUP {os.getpid()} applies "
                "config changes)"
            )
            scheduler.run()
            reports.stopping()
            if web is not None:
                web.stop_previews()  # before the clear below, which can take 30 s
            # Only after a stop that was asked for (Ctrl+C, systemctl stop, shutdown or
            # reboot): after an error, the restart draws the picture again anyway. A second
            # stop signal ends the clear at once. A restart keeps the picture.
            if scheduler.display.on_exit == "clear" and not scheduler.restart_asked:
                signal.signal(signal.SIGTERM, lambda *_: screen.abort())
                signal.signal(signal.SIGINT, lambda *_: screen.abort())
                screen.clear_before_exit()
    except ScreenStuck as error:
        print(f"paperpi: {error}; exiting, so PaperPi is started again", file=sys.stderr)
        reports.stopping()
        logging.shutdown()
        sys.stdout.flush()
        sys.stderr.flush()
        # A normal exit would wait, without a time limit, for the stuck helper process.
        os._exit(1)
    except OSError as error:
        print(f"paperpi: {error}", file=sys.stderr)
        return 1
    finally:
        reports.stopping()
        if web is not None:
            web.stop()
    if scheduler.restart_asked:
        log.info("PaperPi starts again, as asked in the web interface", extra=logbook.KEEP)
        return RESTART_STATUS
    return 0


def _reset_password(args: argparse.Namespace) -> int:
    try:
        removed = save_password_hash(args.config, None)
    except PasswordError as error:
        hint = "; run it with sudo" if "Permission denied" in str(error) else ""
        print(f"paperpi: {error}{hint}", file=sys.stderr)
        return 1
    if not removed:
        print(f"no web password is set in {args.config}")
        return 0
    print(
        f"removed the web password from {args.config}.\n"
        "Next: restart PaperPi, or run paperpi reload (sudo paperpi reload once it runs as "
        "a service).\n"
        "Then open the web interface and set a new password. Until then, anyone on your "
        "home network can set it."
    )
    return 0


def _web_defaults(args: argparse.Namespace) -> int:
    # The kept old address goes first (else the next start would put the defaults on trial
    # and go back to it), so nothing changes when it can't be removed.
    try:
        (args.state_dir / keep.PREVIOUS_FILE).unlink(missing_ok=True)
    except OSError as error:
        hint = "; run it with sudo" if isinstance(error, PermissionError) else ""
        print(f"paperpi: can't remove the kept old web address: {error}{hint}", file=sys.stderr)
        return 1
    every = config.WebSettings()
    try:
        path, text = config_file.read(args.config)
        defaults = {"address": every.address, "port": every.port}
        new = config_file.set_web(text, dict.fromkeys(defaults), defaults)
        if new != text:
            config_file.write(path, new)
    except config_file.EditError as error:
        hint = "; run it with sudo" if "Permission denied" in str(error) else ""
        print(f"paperpi: {error}{hint}", file=sys.stderr)
        return 1
    where = f"port {every.port}, for every device on your home network"
    if new == text:
        print(f"the web interface already uses the defaults in {args.config}: {where}")
        return 0
    print(
        f"the web interface is back on {where} in {args.config}.\n"
        "Next: restart PaperPi (sudo systemctl restart paperpi when it runs as a service), "
        f"then open http://<the Pi's address>:{every.port}"
    )
    return 0


def _list(args: argparse.Namespace) -> int:
    try:
        loaded = config.load(args.config, state_dir=None)
    except config.ConfigError as error:
        print(f"paperpi: the config file can't be used:\n{error}", file=sys.stderr)
        return 1
    rows = [("id", "name", "type", "on", "level", "display", "refresh", "layout", "storage")]
    for row in config.plugin_rows(loaded):
        rows.append(
            (
                row.id,
                row.name,
                row.type,
                _on_column(row),
                row.level,
                f"{row.display_time:g} s",
                f"{row.refresh:g} s",
                row.layout,
                f"{row.storage_mb} MB, "
                + (f"{row.storage_days} d" if row.storage_days else "no age limit"),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for row in rows:
        print(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        )
    if len(rows) == 1:
        print("(no plugins)")
    if loaded.problems:
        count = len(loaded.problems)
        print(f"{count} problem{'' if count == 1 else 's'} in the file, shown above")
    return 0


def _on_column(row: config.PluginRow) -> str:
    """The "on" column of ``paperpi list``."""
    if not row.enabled:
        return "no"
    return f"needs {', '.join(row.missing)}" if row.missing else "yes"


def _example_config(args: argparse.Namespace) -> int:
    display = {"type": args.display, "model": args.model, "vcom": args.vcom}
    make = example.setup_config if args.setup else example.example_config
    try:
        text = make(display, fresh=not args.fixed_ids)
        config.parse(text)  # e.g. an it8951 screen without its vcom
    except (ValidationError, config.ConfigError) as error:
        raise UsageError(f"the [display] settings can't be used:\n{error}") from None
    if args.output is None:
        print(text, end="")
        return 0
    if args.output.exists() and not args.force:
        raise UsageError(f"{args.output} is already there; add --force to replace it")
    try:
        # Only the owner may read it: once filled in, a config holds email addresses and keys.
        write_atomic(args.output, text.encode())
    except OSError as error:
        print(f"paperpi: {error}", file=sys.stderr)
        return 1
    print(f"saved {args.output}")
    return 0


def _new_plugin(args: argparse.Namespace) -> int:
    try:
        folder = newplugin.new_plugin(args.type, title=args.title)
    except newplugin.NewPluginError as error:
        raise UsageError(str(error)) from None
    print(f"made {folder}")
    print(f"try it: uv run paperpi render {args.type}")
    return 0


def _reload(args: argparse.Namespace) -> int:
    status, lines = reload.run(args.config, args.state_dir, args.health_file, check_only=args.check)
    print("\n".join(lines), file=sys.stdout if status == reload.OK else sys.stderr)
    return status


def _health(args: argparse.Namespace) -> int:
    healthy, message = health.check(args.health_file)
    print(message)
    return 0 if healthy else 1


def _job_from_options(args: argparse.Namespace) -> _Job:
    try:
        plugin = plugins.load(args.plugin)
    except KeyError:
        raise UsageError(
            f"unknown plugin {args.plugin!r}; known: {', '.join(plugins.available())}"
        ) from None
    except Exception as error:  # noqa: BLE001 - a bug in the plugin, not in the command
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
    return _Job(
        plugin=plugin,
        settings=settings,
        layout=plugin.default_layout,
        width=width,
        height=height,
        mode=config.MODES[args.mode or config.VIRTUAL_MODE],
        time_limit=limits.PLUGIN_UPDATE,
        output=Path(f"{plugin.type}.png"),
    )


def _job_from_config(args: argparse.Namespace) -> _Job:
    try:
        loaded = config.load(args.config, state_dir=None)
    except config.ConfigError as error:
        raise UsageError(f"the config file can't be used:\n{error}") from None
    try:
        found = loaded.plugin(args.id)
    except KeyError:
        ids = ", ".join(repr(p.entry.id) for p in loaded.plugins) or "none"
        raise UsageError(
            f"no usable plugin with ID {args.id!r} in {args.config} (problems are shown "
            f"above); plugins without errors: {ids}"
        ) from None
    width, height = loaded.display.layout_size
    return _Job(
        plugin=found.plugin,
        settings=found.settings,
        layout=found.layout,
        width=width,
        height=height,
        mode=loaded.display.screen_mode,
        time_limit=found.entry.time_limit,
        output=Path(f"{found.folder_name}.png"),
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
