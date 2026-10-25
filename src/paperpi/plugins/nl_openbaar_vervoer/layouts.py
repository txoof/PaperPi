"""Layouts for nl_openbaar_vervoer. The first one is the default.

``sections``: a heading per stop (a black bar with ``head_<s>``: the stop's name in bold, and
``walk_<s>``: "6 min walk" at the right), then its departures, one row each, with the
blocks ``time_<s>_<i>``, ``delay_<s>_<i>``, ``line_<s>_<i>``, ``dest_<s>_<i>`` and
``note_<s>_<i>`` ("leave in 3 min", "left", ...). The screen is shared by the stops shown
today, so the number of rows per stop depends on the settings and the day.

``by_time``: the departures of all stops in one list, the soonest first, each row with the
stop's heading in ``stop_<i>`` (rows ``time_<i>``, ``delay_<i>``, ``line_<i>``, ``dest_<i>``,
``note_<i>``).

``next``: the first stop only, with the same heading. The next departure that can still be
caught is large (``next_dest``: line and destination, ``next_note``: "Leave in 3 min",
``next_time``), the later ones are small rows below it (``time_0_<i>``, ...). Only the first
stop is fetched.

Every layout ends with ``notice`` (disruptions on the train routes) and ``footer`` (when the
departures were fetched).
"""

from ... import fonts

PAD = 0.008
TEXT = 0.045
#: Smaller text for the ``by_time`` rows: they have one more column.
LIST_TEXT = 0.037
#: Heading and departure lines on the screen, shared by the stops.
LINES = 12
#: Small rows under the large departure of the ``next`` layout.
LATER = 4
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
    """Departure rows for each of ``stops`` stops and routes (1 to 6): 11, 5, 3, 2, 1, 1."""
    return (LINES - stops) // stops


def _row(s: int, i: int, train: bool = False) -> dict:
    """One departure row. A train row has the platform in a box (``track_<s>_<i>``, as on
    NS's signs) before the station the train is signed with."""
    if train:
        # A picture: drawn by the plugin (see sign() in __init__), so a row without a
        # platform has no empty box. A text block's border is always drawn.
        box = {"name": f"track_{s}_{i}", "type": "image", "size": 0.6, "padding": PAD}
        # Station names are long ("Amsterdam Centraal"): the note column gives room.
        middle = [box, _text(f"dest_{s}_{i}", "Amsterdam Centraal", 3.2, shrink=True)]
        note = 2.4
    else:
        middle = [_text(f"dest_{s}_{i}", "Carnisselande", 3.2)]
        note = 3.0
    return {
        "row": [
            _text(f"time_{s}_{i}", "88:88", 1.3, font=fonts.LATO_BOLD),
            _text(f"delay_{s}_{i}", "+88", 0.9),
            _text(f"line_{s}_{i}", "888", 0.9, align="center", font=fonts.LATO_BOLD),
            *middle,
            _text(f"note_{s}_{i}", "leave in 88 min", note, align="right"),
        ],
        "gap": 0,
    }


def _heading(s: int) -> list:
    """The heading of stop ``s``: a black bar with white text, the stop's name in bold and
    the walking time at the right (two blocks: a text block has one font). The bar sets the
    sections apart, so the walking time can't be read as one more departure."""
    bar = {"background": "black", "fill": "white"}
    return [
        {
            "row": [
                # Long names (train routes) are made smaller to fit.
                _text(
                    f"head_{s}",
                    "Rotterdam Centraal",
                    3.6,
                    font=fonts.LATO_BOLD,
                    shrink=True,
                    **bar,
                ),
                _text(f"walk_{s}", "88 min walk", 1.4, align="right", **bar),
            ],
            "gap": 0,
        },
    ]


def sections(settings) -> dict:
    """One section per stop shown today (at least one). The layout is made again at each
    update, so it follows the days."""
    from . import _now, today_routes, today_stops  # here: the plugin's module imports this one

    now = _now()
    stops, routes = len(today_stops(settings, now)), len(today_routes(settings, now))
    count = max(1, stops + routes)
    rows = rows_per_stop(count)
    column = []
    for s in range(count):  # stops first, then train routes
        column += _heading(s)
        column += [_row(s, i, train=stops <= s < stops + routes) for i in range(rows)]
    return _with_footer(column)


def by_time(settings) -> dict:
    """One list of :data:`LINES` rows, with the stop on each row."""
    small = {"font_size": LIST_TEXT}
    bold = small | {"font": fonts.LATO_BOLD}
    column = []
    for i in range(LINES):
        column.append(
            {
                "row": [
                    _text(f"time_{i}", "88:88", 1.1, **bold),
                    _text(f"delay_{i}", "+88", 0.7, **small),
                    _text(f"line_{i}", "888", 0.8, align="center", **bold),
                    _text(f"dest_{i}", "Carnisselande", 2.6, **small),
                    # Long headings are made smaller to fit.
                    _text(f"stop_{i}", "Centraal perron A", 2.2, shrink=True, **small),
                    _text(f"note_{i}", "leave in 88 min", 2.4, align="right", **small),
                ],
                "gap": 0,
            }
        )
    return _with_footer(column)


def next_departure(settings) -> dict:
    """The next departure of the first stop (or train route), large, then :data:`LATER`
    small rows."""
    from . import _now, today_routes, today_stops  # here: the plugin's module imports this one

    now = _now()
    train = not today_stops(settings, now) and bool(today_routes(settings, now))
    column = [
        *_heading(0),
        # No font_size: the text is made as large as its block allows.
        _text("next_dest", "888 Heemraadsplein", 2.2, align="center", font_size=None, shrink=True),
        _text(
            "next_note",
            "Leave in 88 min",
            3,
            align="center",
            font=fonts.LATO_BOLD,
            font_size=None,
        ),
        _text("next_time", "88:88 (+88)", 1.4, align="center", font_size=None),
    ]
    column += [_row(0, i, train=train) for i in range(LATER)]
    return _with_footer(column)


def _with_footer(column: list) -> dict:
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


LAYOUTS = {"sections": sections, "by_time": by_time, "next": next_departure}
