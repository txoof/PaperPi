"""Layouts for ical_calendar. The first one is the default.

One row per event, with the blocks ``day_<i>``, ``time_<i>``, ``mark_<i>`` and ``title_<i>``
(``small``: ``when_<i>``, ``mark_<i>`` and ``title_<i>``); the number of rows is the number of
``title_`` blocks. The list layout also has a header: ``today`` (the date), then
``key_mark_<k>`` and ``key_name_<k>`` for each calendar (filled from the right, so they end at
the screen's edge).

Every text in a layout has one size, a share of the screen's shorter side, and never shrinks:
a title that is too long is cut ("…"). The marks are pictures drawn at their block's size,
so they are all the same size (the ● and ○ letters of a font are not).
"""

from ... import fonts

PAD = 0.01
TEXT = 0.045
KEY = 0.035


def _text(name, sample, size, font_size, font=None, align="left") -> dict:
    block = {
        "name": name,
        "type": "text",
        "size": size,
        "sample": sample,
        "font_size": font_size,
        "align": align,
        "padding": PAD,
    }
    if font:
        block["font"] = font
    return block


def _mark(name, size) -> dict:
    return {"name": name, "type": "image", "size": size, "fit": "contain", "padding": PAD}


def _rows(count: int) -> list[dict]:
    return [
        {
            "row": [
                _text(f"day_{i}", "Wed 28 Oct", 2.5, TEXT, fonts.LATO_BOLD),
                _text(f"time_{i}", "until Wed 28", 2.8, TEXT),
                _mark(f"mark_{i}", 0.5),
                _text(f"title_{i}", "Dentist appointment", 6, TEXT),
            ],
            "gap": 0,
        }
        for i in range(count)
    ]


def _key(k: int) -> list[dict]:
    """The mark and name of one calendar, in the header."""
    return [
        _mark(f"key_mark_{k}", 0.4),
        _text(f"key_name_{k}", "Personal", 1.4, KEY),
    ]


LAYOUTS = {
    # The date and the calendars on top, then the next 8 events.
    "list": {
        "column": [
            {
                "row": [
                    _text("today", "Wednesday 30 September", 5.2, 0.05, fonts.LATO_BOLD),
                    *_key(0),
                    *_key(1),
                    *_key(2),
                ],
                "gap": 0,
                "size": 1.3,
            },
            {"name": "line", "type": "shape", "shape": "hline", "pixels": 3},
            *_rows(8),
        ],
        "gap": 0,
    },
    # For tiny screens (2" to 3"): the next 3 events, no header; day and time in one block.
    "small": {
        "column": [
            {
                "row": [
                    _text(f"when_{i}", "Thu 18:45", 3.8, 0.12, fonts.LATO_BOLD),
                    _mark(f"mark_{i}", 0.5),
                    _text(f"title_{i}", "Running club", 4, 0.12),
                ],
                "gap": 0,
            }
            for i in range(3)
        ],
        "gap": 0,
    },
}
