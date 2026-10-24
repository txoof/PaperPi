"""Layouts for nl_openbaar_vervoer. The first one is the default.

``sections``: a heading per stop (``head_<s>``), then its departures, one row each, with the
blocks ``time_<s>_<i>``, ``delay_<s>_<i>``, ``line_<s>_<i>``, ``dest_<s>_<i>`` and
``note_<s>_<i>`` ("leave in 3 min", "left", ...). The screen is shared by the stops shown
today, so the number of rows per stop depends on the settings and the day. ``footer`` says
when the departures were fetched.
"""

from ... import fonts

PAD = 0.008
TEXT = 0.045
#: Heading and departure lines on the screen, shared by the stops.
LINES = 12
STOPS = 4
ROUTES = 2


def _text(name, sample, size, align="left", font=None, **more) -> dict:
    block = {
        "name": name,
        "type": "text",
        "size": size,
        "sample": sample,
        "font_size": TEXT,
        "align": align,
        "padding": PAD,
    }
    if font:
        block["font"] = font
    return block | more


def rows_per_stop(stops: int) -> int:
    """Departure rows for each of ``stops`` stops (1 to 4): 11, 5, 3 or 2."""
    return (LINES - stops) // stops


def _row(s: int, i: int) -> dict:
    return {
        "row": [
            _text(f"time_{s}_{i}", "88:88", 1.3, font=fonts.LATO_BOLD),
            _text(f"delay_{s}_{i}", "+88", 0.9),
            _text(f"line_{s}_{i}", "888", 0.9, align="center", font=fonts.LATO_BOLD),
            _text(f"dest_{s}_{i}", "Carnisselande", 3.2),
            _text(f"note_{s}_{i}", "leave in 88 min", 3.0, align="right"),
        ],
        "gap": 0,
    }


def sections(settings) -> dict:
    """One section per stop shown today (at least one). The layout is made again at each
    update, so it follows the days."""
    from . import _now, today_routes, today_stops  # here: the plugin's module imports this one

    now = _now()
    count = max(1, len(today_stops(settings, now)) + len(today_routes(settings, now)))
    rows = rows_per_stop(count)
    column = []
    for s in range(count):
        column.append(
            _text(f"head_{s}", "Rotterdam Centraal · 8 min walk", 1, font=fonts.LATO_BOLD)
        )
        column += [_row(s, i) for i in range(rows)]
    column.append({"name": "line", "type": "shape", "shape": "hline", "pixels": 2})
    column.append(
        {
            "row": [
                # Long notices are made smaller to fit.
                _text(
                    "notice",
                    "Disruption: Rotterdam - Den Haag",
                    4,
                    font=fonts.LATO_BOLD,
                    shrink=True,
                ),
                _text("footer", "Not updated since 88:88", 1.6, align="right"),
            ],
            "gap": 0,
            "size": 0.8,
        }
    )
    return {"column": column, "gap": 0}


LAYOUTS = {"sections": sections}
