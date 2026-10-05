"""A plugin whose PLUGIN.type doesn't match its folder."""

from paperpi.plugin import Plugin, PluginSettings, ready

PLUGIN = Plugin(
    type="other_name",
    description="Wrong type.",
    settings=PluginSettings,
    layouts={"one": {"column": [{"name": "text", "type": "text"}]}},
    fetch=lambda context: ready("x"),
    draw=lambda data, context: {"text": data},
    sample="x",
    refresh=30,
)
