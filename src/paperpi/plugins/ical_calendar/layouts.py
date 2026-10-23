"""Layouts for ical_calendar. The first one is the default.

One row per event, with the blocks ``day_<i>``, ``time_<i>`` and ``title_<i>`` (``small``:
``when_<i>`` and ``title_<i>``); the number of rows is the number of ``title_`` blocks. The
list layout also has a header: ``today`` (the date) and ``updated``. Text sizes are shares
of the screen's shorter side, so every row uses the same size; ``shrink`` makes a long text
smaller (and may wrap it onto a second line) before it is cut.
"""

from ... import fonts

PAD = 0.01
DAY = "Tomorrow"
TIME = "until Sun 25"
TITLE = "Dentist appointment with Anne"


def _text(name, sample, size, font_size, font=None, align="left", **more) -> dict:
    block = {
        "name": name,
        "type": "text",
        "size": size,
        "sample": sample,
        "font_size": font_size,
        "shrink": True,
        "align": align,
        "padding": PAD,
        "rgb_support": True,
        **more,
    }
    if font:
        block["font"] = font
    return block


def _rows(count: int, font_size: float) -> list[dict]:
    return [
        {
            "row": [
                _text(f"day_{i}", DAY, 2, font_size, fonts.LATO_BOLD),
                _text(f"time_{i}", TIME, 2, font_size),
                _text(f"title_{i}", TITLE, 6, font_size),
            ],
            "gap": 0,
        }
        for i in range(count)
    ]


def _short_rows(count: int, font_size: float) -> list[dict]:
    """Rows with the day and time in one block, ``when_<i>``. Without ``shrink``, so a long
    title is cut ("…") instead of wrapped onto a second line."""
    return [
        {
            "row": [
                _text(f"when_{i}", "Thu 18:45", 2, font_size, fonts.LATO_BOLD, shrink=False),
                _text(f"title_{i}", "Running club", 5, font_size, shrink=False),
            ],
            "gap": 0,
        }
        for i in range(count)
    ]


def _line(name) -> dict:
    return {"name": name, "type": "shape", "shape": "hline", "pixels": 3, "rgb_support": True}


LAYOUTS = {
    # The date on top, then the next 8 events.
    "list": {
        "column": [
            {
                "row": [
                    _text("today", "Wednesday 30 September", 3, 0.07, fonts.LATO_BOLD),
                    _text("updated", "Saved 88:88", 1, 0.035, align="right"),
                ],
                "gap": 0,
                "size": 1.3,
            },
            _line("line"),
            *_rows(8, 0.055),
        ],
        "gap": 0,
    },
    # For tiny screens (2" to 3"): the next 3 events, no header.
    "small": {"column": _short_rows(3, 0.17), "gap": 0},
}
