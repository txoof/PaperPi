"""splash_screen: PaperPi's name, version and web address, in large text.

In v1 this was shown once when PaperPi started (``splash = True``). In v2 it is a plugin
like any other: add a ``[[plugin]]`` block to show it. Showing it only at start is not
part of this plugin (it would need the scheduler).
"""

from dataclasses import dataclass

from ... import __version__
from ...plugin import Context, Plugin, PluginSettings, ready
from .layouts import LAYOUTS

NAME = "PaperPi"
URL = "https://github.com/txoof/PaperPi"


@dataclass(frozen=True)
class About:
    """What the splash screen shows."""

    name: str
    version: str
    url: str


class Settings(PluginSettings):
    pass


def fetch(context: Context):
    return ready(About(NAME, __version__, URL))


def split_url(url: str) -> str:
    """Put a line break after the server name, so a long address can use two lines.

    "https://github.com/txoof/PaperPi" becomes "https://github.com/" and "txoof/PaperPi",
    the same break v1 made (v1 wrote a space there).
    """
    scheme, found, rest = url.partition("://")
    if not found:
        scheme, rest = "", url
    host, slash, path = rest.partition("/")
    if not slash or not path:
        return url
    return f"{scheme}{found}{host}/\n{path}"


def draw(about: About, context: Context) -> dict:
    return {"name": about.name, "version": about.version, "url": split_url(about.url)}


PLUGIN = Plugin(
    type="splash_screen",
    description="PaperPi's name, version and web address, in large text.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    # A fixed version, so the sample images don't change with every release.
    sample=About(NAME, "2.0.0", URL),
    # Nothing changes while PaperPi runs; the version only changes with a new PaperPi.
    refresh=3600,
)
