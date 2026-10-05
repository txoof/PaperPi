"""basic_clock: the time, and optionally the date, in large text."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from ...plugin import Context, Plugin, PluginSettings, ready
from .layouts import LAYOUTS


class Settings(PluginSettings):
    hours: Literal[12, 24] = Field(24, description="12-hour (3:45 PM) or 24-hour (15:45) clock")


def fetch(context: Context):
    return ready(datetime.now())


def format_time(now: datetime, hours: int) -> str:
    if hours == 12:
        return f"{now.hour % 12 or 12}:{now:%M} {now:%p}"
    return f"{now:%H:%M}"


def format_date(now: datetime) -> str:
    # Python uses English day and month names unless a program changes its locale.
    return f"{now:%A} {now.day} {now:%B}"


def draw(now: datetime, context: Context) -> dict:
    values = {"time": format_time(now, context.settings.hours)}
    if context.layout == "time_date":
        values["date"] = format_date(now)
    return values


PLUGIN = Plugin(
    type="basic_clock",
    description="The time, and optionally the date, in large text.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=datetime(2026, 10, 5, 10, 42),
    refresh=60,
    refresh_on_minute=True,
)
