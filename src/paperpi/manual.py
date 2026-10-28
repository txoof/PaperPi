"""Pages of the manual website that are made from the code, so they are always up to date.

``mkdocs_hooks.py`` (next to ``mkdocs.yml``) adds them while MkDocs builds the site:

- :func:`settings_page`: every setting of ``[display]``, ``[web]`` and ``[[plugin]]``, with
  its default and help text, from the same descriptions as ``paperpi example-config``.
- :func:`plugin_page`: one page per plugin: its README, with links made to work on the site,
  and a table of its settings. :func:`plugins_page` lists them with a picture each.
- :func:`screens_page`: every screen epdlib can drive.

Pictures in the READMEs are the image tests' reference images (``tests/images/``), which CI
checks against the plugins' drawing, so they always show what the plugin draws now.
:func:`site_links` turns full addresses of manual pages into links between pages, so the
site's link check (``mkdocs build --strict``) covers them too.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from epdlib import ScreenMode
from epdlib.drivers import it8951, waveshare
from pydantic.fields import FieldInfo

from . import links, plugins
from .config import MODES, DisplaySettings, WebSettings
from .example import _DISPLAY_SHOWN, help_text, suggested, toml_value
from .plugin import Plugin, PluginEntry, is_required

#: The manual's address; links to it are written as links between pages (see site_links).
SITE = "https://txoof.github.io/PaperPi/"
REPO = "https://github.com/txoof/PaperPi/"
#: Plugins the web interface's Plugin Library leaves out (PaperPi's own); they get a page,
#: but are not in the menu or the list of plugins.
OWN = ("default", "debugging")
#: Where pictures from the repository go on the site: ``files/<path in the repository>``.
FILES = "files/"
_PICTURE = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
#: The target of a Markdown link or picture: ``](target)``.
_TARGET = re.compile(r"\]\(([^)\s]+)\)")
#: Help text written for the config file (where the suggestion is a comment below the
#: setting), as it reads on the site.
_WORDING = {
    " (shown below)": "",
    ' (see "Layouts" above)': " (see the plugin's page)",
}
#: Shared settings whose default is the plugin's suggestion (see example.suggested).
_SUGGESTED = ("refresh", "level", "layout", "storage_mb", "storage_days")
_NETWORK = {
    "internet": "the internet",
    "home": "a device on your home network",
    None: "nothing: no network",
}


class Words(str):
    """A default shown as words in a settings table, e.g. "the plugin's suggestion"."""


def listed(types: Iterable[str]) -> list[str]:
    """The plugin types of the Plugin Library (not :data:`OWN`), sorted by the name the web
    interface shows: the order of the menu and of the list of plugins."""
    shown = [t for t in types if t not in OWN]
    return sorted(shown, key=lambda t: plugins.load(t).shown_title.lower())


def settings_table(fields: Mapping[str, FieldInfo], shown: Mapping[str, Any] | None = None) -> str:
    """A Markdown table of ``fields``: name, default (or ``shown``) and help text."""
    shown = shown or {}
    rows = ["| Setting | Default | What it does |", "|---|---|---|"]
    for key, info in fields.items():
        if info.is_required() or is_required(info):
            default = "required"
        else:
            value = shown.get(key, info.get_default(call_default_factory=True))
            if isinstance(value, Words):
                default = value
            elif hasattr(value, "get_secret_value") or value in (None, ""):
                default = "not set"  # never show a secret, even a default one
            else:
                default = f"`{toml_value(value)}`"
        text = links.LINK.sub(_readme_as_text, help_text(key, info))
        for config_file, site in _WORDING.items():
            text = text.replace(config_file, site)
        rows.append(f"| `{key}` | {default} | {_cell(text)} |")
    return "\n".join(rows) + "\n"


def settings_page() -> str:
    """The settings reference: every part of the config file."""
    entry = PluginEntry.model_fields
    common = {k: v for k, v in entry.items() if k not in ("id", "type")}
    suggestion = {key: Words("the plugin's suggestion") for key in _SUGGESTED}
    return f"""\
# Settings reference

PaperPi's settings are in one file, `/etc/paperpi/paperpi.toml` (TOML: `name = value` lines
under headings in square brackets). The web interface changes it for you; this page lists
every setting, for reading or for editing the file by hand. A file only needs the settings
that differ from the default. After editing it, run `sudo paperpi reload` to use the
changes without a restart.

`paperpi example-config` prints a complete example with every setting as a comment.

The first line of the file is `config_version = 1`.

## The screen: `[display]` {{ #display }}

`type`, `model`, `width`, `height` and `mode` apply at the next start of PaperPi; the others
at once. The screens and their `model` names are in [Supported screens](screens.md).

{settings_table(DisplaySettings.model_fields, _DISPLAY_SHOWN)}
The defaults of `width`, `height` and `mode` are those of the 9.7" screen. `model` and
`vcom` show examples: they have no default.

## The web interface: `[web]` {{ #web }}

`enabled`, `address` and `port` apply at the next start; the others at once.

{settings_table(WebSettings.model_fields)}
## Settings every plugin has {{ #settings-every-plugin-has }}

Each plugin on the screen is one `[[plugin]]` block. Every block has an `id` (made by the
web interface: the plugin type and 8 letters and digits) and a `type` (which plugin), and
can have the settings below. Its own settings are on [the plugin's page](plugins/index.md).
"The plugin's suggestion" is on that page too.

{settings_table({"id": entry["id"], "type": entry["type"]} | common, suggestion)}"""


def plugin_page(plugin_type: str, types: Iterable[str], root: Path) -> tuple[str, set[str]]:
    """The page of one plugin (``plugins/<type>.md``) and the repository files it shows."""
    plugin = plugins.load(plugin_type)
    readme = plugins.readme(plugin_type) or f"# {plugin_type}\n\n{plugin.description}\n"
    here = f"src/paperpi/plugins/{plugin_type}/"
    used: set[str] = set()
    text = _TARGET.sub(lambda m: f"]({_site_target(m[1], here, set(types), root, used)})", readme)
    first, _, rest = text.partition("\n")
    title = f"# {plugin.shown_title}" if first.startswith("# ") else first
    facts = f"Type `{plugin.type}` · needs {_NETWORK[plugin.network]}"
    if plugin.setup:
        facts += f" · set up first: {plugin.setup}"
    table = _plugin_settings(plugin)
    head, sample, tail = rest.partition("\n## Sample images")
    body = f"{head.rstrip()}\n\n{table}\n## Sample images{tail}" if sample else f"{rest}\n{table}"
    return f"{title}\n\n{facts}.\n{body.rstrip()}\n", used


def plugins_page(types: Iterable[str], root: Path) -> tuple[str, set[str]]:
    """The list of plugins (``plugins/index.md``), with a sample picture each."""
    rows = ["| | Plugin | What it shows | Needs |", "|---|---|---|---|"]
    used: set[str] = set()
    for plugin_type in listed(types):
        plugin = plugins.load(plugin_type)
        picture = f"tests/images/{plugin_type}-{plugin.default_layout}-9in7.png"
        cell = ""
        if (root / picture).is_file():
            used.add(picture)
            cell = f"[![{plugin.shown_title}]({FILES}{picture}){{ width=200 }}]({plugin_type}.md)"
        name = f"[{plugin.shown_title}]({plugin_type}.md)"
        needs = _NETWORK[plugin.network]
        rows.append(f"| {cell} | {name} | {_cell(plugin.description)} | {needs} |")
    own = ", ".join(f"[`{t}`]({t}.md)" for t in OWN)
    return (
        "# Plugins\n\nEach plugin shows one kind of information. Add them in the web "
        "interface's **Plugin Library**; the same plugin can be added more than once, for "
        "example the weather for two places. The pictures are drawn from each plugin's "
        'sample data on the 9.7" screen.\n\n'
        + "\n".join(rows)
        + f"\n\nPaperPi also has its own plugins, which are not in the Plugin Library: {own}.\n",
        used,
    )


def screens_page() -> str:
    """Every screen epdlib can drive, made from epdlib's lists of models."""
    it_rows = [
        "| `model =` | Size (pixels) | Shows | Fast writes | Tested |",
        "|---|---|---|---|---|",
    ]
    for name, info in it8951.MODELS.items():
        it_rows.append(
            f'| `"{name}"` | {info.width} × {info.height} | {_shows(info.mode)} '
            f"| {_yes(info.fast_refresh)} | {_yes(info.tested)} |"
        )
    ws_rows = [
        "| Name | `model =` | Size (pixels) | Shows | Fast writes | Tested |",
        "|---|---|---|---|---|---|",
    ]
    for name, info in waveshare_models():
        shows = _shows(info.mode)
        if _three_colour(name):
            shows += " (3-colour screen, see above)"
        ws_rows.append(
            f"| {name.removeprefix('epd')} | `{name}` | {info.width} × {info.height} | {shows} "
            f"| {_yes(info.fast_refresh)} | {_yes(info.tested)} |"
        )
    virtual = ", ".join(f"`{m}`" for m in MODES)
    return f"""\
# Supported screens

PaperPi draws for three kinds of screen, set with `type` in `[display]` (see the
[settings reference](settings.md#display)). The web interface's **Screen & system** page
and the installer offer the same list. This page is made from epdlib's lists of models, so
it always matches the installed version.

## IT8951 screens {{ #it8951 }}

`type = "it8951"`: Waveshare's larger screens with the IT8951 board. `model` is the size
in inches. `vcom` is required too: the voltage printed on the screen's ribbon cable.

{chr(10).join(it_rows)}

## Waveshare's small screens {{ #waveshare }}

`type = "waveshare"`: the screens on Waveshare's e-Paper HAT, without an IT8951 board. How
to set them up, and what to know about each kind: [Waveshare screens](waveshare-screens.md).
Three-colour screens (with "B" or "C" in the name) show only black and white for now.

Tested ones first, then by size. The name is Waveshare's: `7in5_V2` is the 7.5 inch screen,
version 2. The config file uses the whole name of Waveshare's file (`model =`).
{_not_working()}
{chr(10).join(ws_rows)}

## Virtual screen {{ #virtual }}

`type = "virtual"`: no screen; every picture is saved as a PNG file. Any `width` and
`height`, and a `mode`: {virtual}. Without them it is like the 9.7" IT8951 screen.
"""


def waveshare_models() -> list[tuple[str, Any]]:
    """epdlib's Waveshare models: tested ones first, then by size in inches, then name."""

    def order(item: tuple[str, Any]) -> tuple:
        name, info = item
        inches = re.match(r"epd(\d+)in(\d+)", name)
        size = float(f"{inches[1]}.{inches[2]}") if inches else 0.0
        return (not info.tested, size, name)

    return sorted(waveshare.MODELS.items(), key=order)


def site_links(markdown: str, page: str, pages: Iterable[str]) -> str:
    """``markdown`` of the page ``page`` (``plugins/met_no.md``) with full addresses of
    manual pages (``https://txoof.github.io/PaperPi/settings/#web``) made into links
    between pages (``../settings.md#web``). ``pages`` are the site's pages."""
    known = set(pages)

    def local(match: re.Match[str]) -> str:
        path, hash_, anchor = match[1].partition("#")
        path = path.strip("/")
        target = next(
            (p for p in (f"{path}.md", f"{path}/index.md".lstrip("/")) if p in known),
            f"{path or 'index'}.md",  # missing: the link check reports it
        )
        relative = posixpath.relpath(target, posixpath.dirname(page) or ".")
        return f"]({relative}{hash_}{anchor})"

    return re.sub(rf"\]\({re.escape(SITE)}([^)\s]*)\)", local, markdown)


def _site_target(target: str, here: str, types: set[str], root: Path, used: set[str]) -> str:
    """A link target from a plugin's README (in the folder ``here`` of the repository),
    as a target from its page on the site (``plugins/<type>.md``)."""
    if re.match(r"[a-z]+:|#", target):
        return target  # a web address, email or a place on the same page
    path, hash_, anchor = target.partition("#")
    resolved = posixpath.normpath(posixpath.join(here, path))
    other = re.fullmatch(r"src/paperpi/plugins/(\w+)/README\.md", resolved)
    if other and other[1] in types:
        return f"{other[1]}.md{hash_}{anchor}"
    if resolved == "README.md":
        return f"../index.md{hash_}{anchor}"
    if resolved.startswith("docs/"):
        return f"../{resolved.removeprefix('docs/')}{hash_}{anchor}"
    if resolved.lower().endswith(_PICTURE) and (root / resolved).is_file():
        used.add(resolved)
        return f"{FILES}{resolved}"
    kind = "tree" if (root / resolved).is_dir() else "blob"
    return f"{REPO}{kind}/main/{resolved}{hash_}{anchor}"


def _plugin_settings(plugin: Plugin) -> str:
    own = plugin.settings.model_fields
    entry = PluginEntry.model_fields
    shown = suggested(plugin)
    mine = settings_table(own) if own else "None of its own.\n"
    return f"""\
## All settings

Made from the plugin's code, so always up to date.

{mine}
Its suggestions for [settings every plugin has](../settings.md#settings-every-plugin-has)
(a block that sets one of them uses that value instead):

{settings_table({k: entry[k] for k in shown}, shown)}"""


def _readme_as_text(match: re.Match[str]) -> str:
    # The plugin's page *is* its README, so "see the [README](readme)" stays plain text.
    return match[1] if match[2] == links.README else match[0]


def _cell(text: str) -> str:
    """``text`` made safe for one cell of a Markdown table."""
    return " ".join(text.split()).replace("|", "\\|")


def _shows(mode: ScreenMode) -> str:
    if mode.kind == "bw":
        return "black and white"
    if mode.kind == "gray":
        return f"{mode.levels} grays"
    return f"{len(mode.colors)} colours"


def _three_colour(name: str) -> bool:
    """A black, white and red (or yellow) screen: "b", "c" or "bc" after the size."""
    return bool(re.search(r"in\d+(b|c|bc)(_\w+)?$", name))


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _not_working() -> str:
    broken = sorted(waveshare.NOT_WORKING)
    if not broken:
        return ""
    names = ", ".join(f"`{n}`" for n in broken)
    return f"\nNot working, so PaperPi refuses them: {names}.\n"
