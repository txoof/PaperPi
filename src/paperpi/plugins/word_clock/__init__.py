"""word_clock: the time in words, such as "It's roughly Twenty After Eight"."""

import random
from datetime import datetime, timedelta

from pydantic import Field

from ...colors import ColorName, screen_colors
from ...plugin import Context, Drawn, Plugin, PluginSettings, ready
from . import words
from .layouts import LAYOUTS


class Settings(PluginSettings):
    text_color: ColorName = Field(
        "white", description="Colour of the text on colour screens, or random"
    )
    background_color: ColorName = Field(
        "black", description="Colour of the background on colour screens, or random"
    )


def fetch(context: Context):
    return ready(datetime.now())


def step_of(now: datetime) -> datetime:
    """The time rounded to the nearest 10 minutes (from :05 on, rounded up)."""
    start = now.replace(minute=0, second=0, microsecond=0)
    return start + timedelta(minutes=(now.minute + 5) // 10 * 10)


def openings(now: datetime) -> tuple[str, ...]:
    """The openings that are true for this time: "nearly" only before the step, "a bit
    after" only after it, exactly on the step only the ones that are always true."""
    minute = now.replace(second=0, microsecond=0)
    step = step_of(now)
    if minute < step:
        return words.ALWAYS + words.BEFORE
    if minute > step:
        return words.ALWAYS + words.AFTER
    return words.ALWAYS


def time_words(step: datetime, minute_words: str, hour_words: str) -> str:
    if step.minute == 0:
        return f"{hour_words} {minute_words}".title()
    return f"{minute_words} {hour_words}".title()


def sentence(now: datetime, rng: random.Random) -> str:
    step = step_of(now)
    hour = step.hour + 1 if step.minute >= 40 else step.hour
    minute_words = rng.choice(words.MINUTES[step.minute])
    hour_words = rng.choice(words.HOURS[hour % 24])
    return f"{rng.choice(openings(now))} {time_words(step, minute_words, hour_words)}"


def all_sentences() -> set[str]:
    """Every sentence the clock can show, at any time (for the layouts' samples and tests)."""
    found = set()
    day = datetime(2026, 1, 1)
    for minutes in range(24 * 60):
        now = day + timedelta(minutes=minutes)
        step = step_of(now)
        hour = (step.hour + 1 if step.minute >= 40 else step.hour) % 24
        for opening in openings(now):
            for minute_words in words.MINUTES[step.minute]:
                for hour_words in words.HOURS[hour]:
                    found.add(f"{opening} {time_words(step, minute_words, hour_words)}")
    return found


def draw(now: datetime, context: Context) -> Drawn:
    # The words and colours change with the step, so they stay the same for 10 minutes.
    # The place of the text changes at every update (every minute it can), as in v1.
    rng = random.Random(int(f"{step_of(now):%Y%m%d%H%M}"))
    text = sentence(now, rng)
    settings = context.settings
    colors = screen_colors(settings.text_color, settings.background_color, context.mode, rng)
    values = {"words": text}
    if context.layout == "words_time":
        values["time"] = f"{now:%H:%M}"
    return Drawn(values, seed=int(f"{now:%Y%m%d%H%M}"), colors=colors)


PLUGIN = Plugin(
    type="word_clock",
    description='The time in words, such as "It\'s roughly Twenty After Eight".',
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=datetime(2026, 10, 5, 20, 21),
    refresh=120,
    refresh_on_minute=True,
)
