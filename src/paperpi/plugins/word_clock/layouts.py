"""Layouts for word_clock. The first one is the default.

The text blocks use ``random`` alignment, so the text moves around the screen at every
update. Their sample is the sentence that needs the smallest text, so every sentence fits
and the font size never changes.
Tight lines: Anton leaves much room above its letters, and 3 lines of it are what limits
the size (148 px instead of 191 px on the 9.7" with normal lines).
"""

from ... import fonts

FONT = fonts.ANTON
PADDING = 0.03

#: The sentence that needs the smallest text in 3 lines. Not simply the widest one: where
#: the lines break matters too. Written out, because working it out from all 2268 sentences
#: would take a noticeable time at every update; a test checks that every sentence fits.
HARDEST = "It's more or less Thirty After Go To Bed"


def _words(size: float) -> dict:
    return {
        "name": "words",
        "type": "text",
        "size": size,
        "font": FONT,
        "sample": HARDEST,
        "max_lines": 3,
        "line_spacing": "tight",
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
