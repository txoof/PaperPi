"""dec_binary_clock: the time as binary dots, one column of 4 dots for each digit."""

from datetime import datetime

from ...plugin import Context, Drawn, Plugin, PluginSettings, ready
from .layouts import LAYOUTS


class Settings(PluginSettings):
    pass


def fetch(context: Context):
    return ready(datetime.now())


def draw(now: datetime, context: Context) -> Drawn:
    from . import dots

    # Draw the dots at the exact size of their block, so epdlib doesn't scale them; a test
    # checks that the screen shows the picture unscaled.
    layout = PLUGIN.layout(context.layout, context.settings)
    prepared = layout.prepare(context.width, context.height, context.mode)
    width, height = prepared.content_size("dots")
    values = {"dots": dots.picture(now.hour, now.minute, width, height)}
    if "time" in prepared.boxes:
        values["time"] = f"{now:%H:%M}"
    # The time text moves at every update; the same minute gives the same place.
    return Drawn(values, seed=int(f"{now:%Y%m%d%H%M}"))


PLUGIN = Plugin(
    type="dec_binary_clock",
    description="The time as binary dots: one column of 4 dots for each digit.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=datetime(2026, 10, 5, 14, 49),
    refresh=60,
    refresh_on_minute=True,
)
