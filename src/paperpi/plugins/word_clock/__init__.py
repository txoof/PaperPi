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
        "white", description="Colour of the text, or random (gray screens: black or white)"
    )
    background_color: ColorName = Field(
        "black", description="Colour of the background, or random (gray screens: black or white)"
    )


def fetch(context: Context):
    return ready(datetime.now())


def step_of(now: datetime) -> datetime:
    """The time rounded to the nearest 10 minutes (from :05 on, rounded up)."""
    start = now.replace(minute=0, second=0, microsecond=0)
    return start + timedelta(minutes=(now.minute + 5) // 10 * 10)


def side_of_step(now: datetime) -> int:
    """-1 when the time is a little before its step, 1 a little after, 0 exactly on it."""
    minute = now.replace(second=0, microsecond=0)
    step = step_of(now)
    return (minute > step) - (minute < step)


def openings(now: datetime) -> tuple[str, ...]:
    """The openings that are true for this time: "nearly" only before the step, "a bit
    after" only after it, exactly on the step only the ones that are always true."""
    side = side_of_step(now)
    return words.ALWAYS + (words.BEFORE if side < 0 else words.AFTER if side > 0 else ())


def hour_of(step: datetime) -> int:
    """The hour the sentence names: from :40 on (so from :35) it counts to the next hour."""
    return (step.hour + 1 if step.minute >= 40 else step.hour) % 24


def time_words(step: datetime, minute_words: str, hour_words: str) -> str:
    if step.minute == 0:
        return f"{hour_words} {minute_words}".title()
    return f"{minute_words} {hour_words}".title()


def step_rng(now: datetime, purpose: str) -> random.Random:
    """A random number generator that gives the same picks for the whole 10-minute step.
    A separate one per ``purpose``, so the words and the colours don't affect each other."""
    return random.Random(f"{step_of(now):%Y%m%d%H%M}-{purpose}")


def sentence(now: datetime) -> str:
    """The sentence for ``now``. The same draws are made at every minute of a step, so the
    words only change where the truth does: an opening like "nearly" is used before the
    step, and the step's plain opening from the minute the step is reached."""
    step = step_of(now)
    rng = step_rng(now, "words")
    plain = rng.choice(words.ALWAYS)
    before, after = rng.choice(words.BEFORE), rng.choice(words.AFTER)
    use_special = rng.random() < 0.5
    minute_words = rng.choice(words.MINUTES[step.minute])
    hour_words = rng.choice(words.HOURS[hour_of(step)])
    side = side_of_step(now)
    opening = plain
    if use_special and side:
        opening = before if side < 0 else after
    return f"{opening} {time_words(step, minute_words, hour_words)}"


def all_sentences() -> set[str]:
    """Every sentence the clock can show, at any time (for the layouts' samples and tests)."""
    found = set()
    day = datetime(2026, 1, 1)
    for minutes in range(24 * 60):
        now = day + timedelta(minutes=minutes)
        step = step_of(now)
        hour = hour_of(step)
        for opening in openings(now):
            for minute_words in words.MINUTES[step.minute]:
                for hour_words in words.HOURS[hour]:
                    found.add(f"{opening} {time_words(step, minute_words, hour_words)}")
    return found


def draw(now: datetime, context: Context) -> Drawn:
    # The words and colours are picked per step, so they stay the same for 10 minutes.
    # The place of the text changes at every update (every minute it can), as in v1.
    text = sentence(now)
    settings = context.settings
    colors = screen_colors(
        settings.text_color, settings.background_color, context.mode, step_rng(now, "colors")
    )
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
