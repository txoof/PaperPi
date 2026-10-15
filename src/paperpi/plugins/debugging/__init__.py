"""debugging: misbehaves on request, to test the scheduler.

Every update adds 1 to a count kept in the file ``count`` in its storage folder. The count
says what the update does, so the same settings always give the same pattern:

- ``states``: the states it reports, one per update, then it starts over.
- ``crash_every``: every Nth update raises an error.
- ``hang_every``: every Nth update hangs until its time limit stops it.
- ``delay``: seconds each update takes, like a slow web request.

The image shows only ``text`` and the state, so updates with the same state give the same
image (the screen is then not written again).

``text`` has a setting helper, ``words`` (see :mod:`paperpi.helper`), to test the settings
page's search box: each typed word becomes a choice that fills in ``text``. Some words
misbehave instead: ``crash`` raises an error, ``hang`` hangs until the time limit,
``problem`` stops with a message for the user and ``many`` gives 12 choices.
"""

import time
from typing import Literal

from pydantic import Field

from ... import limits
from ...files import write_atomic
from ...plugin import (
    NOTHING,
    Context,
    Helper,
    HelperProblem,
    Plugin,
    PluginSettings,
    Query,
    alert,
    ready,
    setting,
)

COUNT_FILE = "count"


class Settings(PluginSettings):
    text: str = setting(
        "debugging", max_length=100, helper="words", description="Text shown above the state"
    )
    states: tuple[Literal["nothing", "ready", "alert"], ...] = Field(
        ("ready",),
        min_length=1,
        max_length=100,
        description="States to report, one per update, then from the start, e.g. "
        '["nothing", "nothing", "alert"]',
    )
    crash_every: int = Field(0, ge=0, description="Every Nth update raises an error; 0 = never")
    hang_every: int = Field(
        0, ge=0, description="Every Nth update hangs until its time limit; 0 = never"
    )
    delay: float = Field(
        0, ge=0, le=limits.PLUGIN_UPDATE_MAX, description="Seconds each update takes"
    )


def next_count(context: Context) -> int:
    """Add 1 to the count in the storage folder and return it. A missing file counts as 0."""
    path = context.storage / COUNT_FILE
    try:
        count = int(path.read_text()) + 1
    except (FileNotFoundError, ValueError):
        count = 1
    write_atomic(path, str(count).encode())
    return count


def fetch(context: Context):
    settings = context.settings
    count = next_count(context)
    if settings.crash_every and count % settings.crash_every == 0:
        raise RuntimeError(f"update {count}: crash, as set by crash_every")
    if settings.hang_every and count % settings.hang_every == 0:
        while True:  # until the time limit stops this process
            time.sleep(3600)
    if settings.delay:
        time.sleep(settings.delay)
    state = settings.states[(count - 1) % len(settings.states)]
    if state == "nothing":
        return NOTHING
    return alert(state) if state == "alert" else ready(state)


def draw(state: str, context: Context) -> dict:
    return {"text": context.settings.text, "state": state}


def find_words(query: Query):
    """The ``words`` helper (see the top)."""
    words = query.text.split()
    if "crash" in words:
        raise RuntimeError("crash, as asked")
    if "hang" in words:
        while True:  # until the time limit stops this process
            time.sleep(3600)
    if "problem" in words:
        raise HelperProblem("A problem, as asked.")
    if "many" in words:
        words = [f"word {n}" for n in range(1, 13)]
    choices = [
        {
            "fill": {"text": word},
            "show": {"Word": word, "Now": query.settings.text, "Language": query.language},
            "link": {"Example": "https://example.org/"},
        }
        for word in words
    ]
    return {"choices": choices, "note": f"{len(words)} words."}


BLOCK = {"type": "text", "align": "center", "padding": 0.05}

LAYOUTS = {
    "text_state": {
        "column": [
            {**BLOCK, "name": "text", "size": 1, "sample": "debugging"},
            {**BLOCK, "name": "state", "size": 2, "sample": "nothing"},
        ]
    }
}

PLUGIN = Plugin(
    type="debugging",
    title="Debugging",
    description="Misbehaves on request (crashes, hangs, changing states), to test PaperPi.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample="ready",
    refresh=30,
    helpers={
        "words": Helper(
            find_words,
            prompt="Some words; each one becomes a choice",
            source="The debugging plugin",
        )
    },
)
