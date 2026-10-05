"""A plugin that hangs while it is being imported."""

import time

from paperpi.plugin import Plugin, PluginSettings, ready

time.sleep(3600)

PLUGIN = Plugin(
    type="slow_import",
    description="Never finishes loading.",
    settings=PluginSettings,
    layouts={"one": {"column": [{"name": "text", "type": "text"}]}},
    fetch=lambda context: ready("x"),
    draw=lambda data, context: {"text": data},
    sample="x",
    refresh=30,
)
