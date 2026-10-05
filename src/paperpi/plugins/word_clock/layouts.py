"""Layouts for word_clock. The first one is the default.

The text blocks use ``random`` alignment, so the text moves around the screen at every
update. Their sample is the longest sentence the clock can make, so every sentence fits
and the font size never changes.
"""

from functools import cache
from pathlib import Path

FONT = str(Path(__file__).parent / "fonts" / "Anton-Regular.ttf")
PADDING = 0.03


@cache
def _longest() -> str:
    from . import all_sentences  # here, because the plugin module imports this one

    return max(sorted(all_sentences()), key=len)  # sorted: the same one every run


def _words(size: float) -> dict:
    return {
        "name": "words",
        "type": "text",
        "size": size,
        "font": FONT,
        "sample": _longest(),
        "max_lines": 3,
        "align": "random",
        "valign": "random",
        "padding": PADDING,
        "rgb_support": True,
        "fill": "white",
        "background": "black",
    }


def words_time(settings) -> dict:
    """The sentence, large, with the time small underneath."""
    time = {
        "name": "time",
        "type": "text",
        "size": 1,
        "font": FONT,
        "sample": "88:88",
        "align": "random",
        "padding": PADDING / 3,
        "rgb_support": True,
        "fill": "white",
        "background": "black",
    }
    return {"column": [_words(6), time], "gap": 0}


def words(settings) -> dict:
    """The sentence only, filling the screen."""
    return {"column": [_words(1)], "gap": 0}


LAYOUTS = {"words_time": words_time, "words": words}
