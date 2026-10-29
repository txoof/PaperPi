"""``paperpi new-plugin``: start a new plugin from the template in ``plugin_template/``.

The template is a small working plugin (a greeting and today's date). Its files end in
``.tmpl``; ``$type`` and ``$title`` in them are replaced by the new plugin's type and title.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template

from . import plugins

TEMPLATE = Path(__file__).parent / "plugin_template"
#: The folder of the plugins that come with PaperPi.
PLUGINS = Path(plugins.__file__).parent
#: The same rule as for ``Plugin.type``.
TYPE_NAME = re.compile(r"[a-z][a-z0-9_]*")


class NewPluginError(Exception):
    """The plugin can't be made; the message says why."""


def title_of(plugin_type: str) -> str:
    """A plain name made from the type: ``bus_times`` gives "Bus times"."""
    return plugin_type.replace("_", " ").strip().capitalize()


def new_plugin(plugin_type: str, folder: Path = PLUGINS, title: str | None = None) -> Path:
    """Make the folder ``folder/plugin_type`` from the template and return it."""
    if not TYPE_NAME.fullmatch(plugin_type):
        raise NewPluginError(
            f"{plugin_type!r} can't be a plugin type: use lowercase letters, digits and _, "
            "starting with a letter (e.g. bus_times)"
        )
    target = folder / plugin_type
    if target.exists():
        raise NewPluginError(f"{target} is already there")
    title = title or title_of(plugin_type)
    if len(title) > 40 or not title.strip():
        raise NewPluginError("the title must be 1 to 40 characters")
    # The title goes between "..." in the new __init__.py.
    if '"' in title or "\\" in title:
        raise NewPluginError("the title can't contain \" or \\")
    values = {"type": plugin_type, "title": title}
    target.mkdir(parents=True)
    for source in sorted(TEMPLATE.glob("*.tmpl")):
        text = Template(source.read_text("utf-8")).substitute(values)
        (target / source.name.removesuffix(".tmpl")).write_text(text, "utf-8")
    return target
