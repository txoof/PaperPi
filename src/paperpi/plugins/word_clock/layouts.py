"""Layouts for word_clock. The first one is the default.

The text blocks use ``random`` alignment, so the text moves around the screen at every
update. Their sample is the widest sentence the clock can make, so every sentence fits
and the font size never changes.
"""

from pathlib import Path

FONT = str(Path(__file__).parent / "fonts" / "Anton-Regular.ttf")
PADDING = 0.03

#: The widest sentence in this font. Written out, because working it out from all 7140
#: sentences would take a noticeable time at every update; a test checks it stays right.
WIDEST = "The time is nearly Twenty Before Crack Of Dawn"


def _words(size: float) -> dict:
    return {
        "name": "words",
        "type": "text",
        "size": size,
        "font": FONT,
        "sample": WIDEST,
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
