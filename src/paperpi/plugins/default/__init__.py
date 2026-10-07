"""default: shown when nothing else can be: plugins are failing, or none are switched on
and the splash screen fails.

The scheduler tells it how many plugins are failing (``context.status``). The QR code that
opens the web interface is added with the web interface (M5).
"""

from ...plugin import Context, Plugin, PluginSettings, PluginsStatus, ready

HELP = "See the web interface for more information."


class Settings(PluginSettings):
    pass


def fetch(context: Context):
    return ready(context.status or PluginsStatus(0, 0))


def message(status: PluginsStatus) -> str:
    if status.total == 0:
        return "No plugins are switched on."
    noun = "plugin is" if status.total == 1 else "plugins are"
    return f"{status.failing} of {status.total} {noun} not working."


def draw(status: PluginsStatus, context: Context) -> dict:
    return {"message": message(status), "help": HELP}


LAYOUTS = {
    "message": {
        "column": [
            {
                "name": "message",
                "type": "text",
                "size": 1,
                "sample": "88 of 88 plugins are not working.",
                "align": "center",
                "valign": "bottom",
                "padding": 0.05,
            },
            {
                "name": "help",
                "type": "text",
                "size": 1,
                "sample": HELP,
                "align": "center",
                "valign": "top",
                "padding": 0.05,
            },
        ]
    }
}

PLUGIN = Plugin(
    type="default",
    description="Says how many plugins are not working, when nothing else can be shown.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=PluginsStatus(3, 4),
    refresh=3600,
)
