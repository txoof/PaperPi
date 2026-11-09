"""Layouts for met_no. The first one is the default.

Block names with a number are filled per hour (``hour_0`` ... ``hour_11``: ``bar``, ``hbar``,
``mm``, ``hour``, ``temp``, ``barb``, ``hicon``), per 2 hours (``icon_0`` ... ``icon_5``) or
per 3-hour step (``step``, ``step_icon``, ``step_temp``, ``step_rain``, 0-3), per 2-hour
pair (``pair_hour``, ``pair_icon``, ``pair_temp``, ``pair_bar``, ``pair_mm``, 0-5) or for
now, +3 and +6 hours (``pick_time``, ``pick_name``, ``pick_icon``, ``pick_temp``,
``pick_rain``, ``pick_barb``, 0-2). The others: ``place``, ``updated``, ``summary`` (or
``temperatures`` and ``rain`` on two lines), ``high``, ``low``, ``rain_start``,
``now_temp``, ``now_degrees``, ``now_icon``, ``now_barb``, ``now_arrow``, ``now_wind``. Rows
have no gaps, so in ``hours_12`` the 6 icons line up with the 12 hour columns.

The layouts after ``hours_12`` are made to be read from across the room: few items, large
text in a narrow bold font, lines between the parts.
"""

from ... import fonts

PAD = 0.008
HOURS = 12
#: The hours shown by ``three_rows`` and ``three_columns``: now, +3 and +6 hours.
PICKS = (0, 3, 6)
#: The line between rows or columns.
LINE = {"pixels": 4}


def _text(name, sample, size=1.0, align="center", **more) -> dict:
    return {
        "name": name,
        "type": "text",
        "size": size,
        "sample": sample,
        "align": align,
        "padding": PAD,
        **more,
    }


def _image(name, size=1.0, fit="contain", **more) -> dict:
    return {"name": name, "type": "image", "size": size, "fit": fit, "padding": PAD, **more}


def _bold(name, sample, size=1.0, align="center", **more) -> dict:
    return _text(name, sample, size, align, font=fonts.ECONOMICA_BOLD, padding=0.01, **more)


def _line(name: str, upright: bool = False) -> dict:
    shape = "vline" if upright else "hline"
    return {
        "name": name,
        "type": "shape",
        "shape": shape,
        "size": 0.03 if upright else 0.06,
        "line_width": LINE,
        "fill": "black",
    }


def _rain_sample(settings) -> str:
    return "8.88 in" if settings.rain == "inch" else "8.8 mm"


def _with_lines(parts: list[dict], prefix: str, upright: bool) -> list[dict]:
    """The parts with a line between each two."""
    out = []
    for k, part in enumerate(parts):
        if k:
            out.append(_line(f"{prefix}_{k}", upright))
        out.append(part)
    return out


def _hour_column(i: int, rain_sample: str) -> dict:
    return {
        "column": [
            _image(f"bar_{i}", size=2.6, fit="stretch"),
            _text(f"mm_{i}", rain_sample, size=0.7),
            _text(f"hour_{i}", "88", size=0.9),
            _text(f"temp_{i}", "-88°", size=0.9),
            _image(f"barb_{i}", size=2.4),
        ],
        "gap": 0,
    }


def hours_12(settings) -> dict:
    """The next 12 hours: a summary line, an icon every 2 hours, rain bars with the mm per
    hour, the hours, temperatures and wind barbs."""
    unit, rain = ("in", "8.88") if settings.rain == "inch" else ("mm", "8.8")
    t = settings.temperature
    return {
        "column": [
            _header(),
            _text(
                "summary",
                f"Max -88°{t} · Min -88°{t} · Rain {rain} {unit}, 88–88, 88–88",
                size=1,
                align="left",
            ),
            {
                "row": [_image(f"icon_{i}", rgb_support=True) for i in range(HOURS // 2)],
                "gap": 0,
                "size": 1.6,
            },
            {"row": [_hour_column(i, rain) for i in range(HOURS)], "gap": 0, "size": 7},
        ],
        "gap": 0,
    }


def _header() -> dict:
    return {
        "row": [
            _text("place", "Rio de Janeiro", size=1, align="left", shrink=True),
            _text("updated", "Updated 88:88 · Data: MET Norway", size=1.4, align="right"),
        ],
        "gap": 0,
        "size": 0.6,
    }


def _samples(settings) -> tuple[str, str]:
    """The widest texts of the two summary lines."""
    t = settings.temperature
    unit, rain = ("in", "8.88") if settings.rain == "inch" else ("mm", "8.8")
    return f"Max -88°{t} · Min -88°{t}", f"Rain {rain} {unit}, 88–88, 88–88"


def small(settings) -> dict:
    """For tiny screens: a big icon for the current hour; the place, the temperature now,
    then max, min and rain for the next 12 hours. No wind barb."""
    temperatures, rain = _samples(settings)
    return {
        "row": [
            _image("now_icon", size=2, rgb_support=True),
            {
                "column": [
                    _text("place", "Rio de Janeiro", size=0.7, align="left", shrink=True),
                    _text("now_temp", f"-88°{settings.temperature}", size=1.4, align="left"),
                    _text("temperatures", temperatures, align="left"),
                    _text("rain", rain, align="left", shrink=True, max_lines=2),
                ],
                "gap": 0,
                "size": 3,
            },
        ],
        "gap": 0,
    }


def three_rows(settings) -> dict:
    """Now, +3 and +6 hours as rows, with lines between them: the time, icon,
    temperature, rain and wind barb."""
    rows = [
        {
            "row": [
                _bold(f"pick_time_{k}", "88:88", size=1.1, align="left"),
                _image(f"pick_icon_{k}", size=0.9, rgb_support=True),
                _bold(f"pick_temp_{k}", "-88°", size=1.1),
                _bold(f"pick_rain_{k}", _rain_sample(settings), size=1.1),
                _image(f"pick_barb_{k}", size=0.7),
            ],
            "gap": 0,
            "size": 3,
        }
        for k in range(len(PICKS))
    ]
    return {"column": [_header(), _line("line_0"), *_with_lines(rows, "line", False)], "gap": 0}


def three_columns(settings) -> dict:
    """Now, +3 and +6 hours as columns, with lines between them: the time, icon, a large
    temperature and the rain. No wind."""
    columns = [
        {
            "column": [
                _bold(f"pick_name_{k}", "88:88", size=1),
                _image(f"pick_icon_{k}", size=1.8, rgb_support=True),
                _bold(f"pick_temp_{k}", "-88°", size=2),
                _bold(f"pick_rain_{k}", _rain_sample(settings), size=0.9),
            ],
            "gap": 0,
        }
        for k in range(len(PICKS))
    ]
    row = {"row": _with_lines(columns, "line", True), "gap": 0, "size": 8}
    return {"column": [_header(), row], "gap": 0}


def now_and_today(settings) -> dict:
    """The icon and temperature now on the left; on the right the highest and lowest
    temperature of the next 12 hours and when the rain starts."""
    t = settings.temperature
    return {
        "column": [
            _header(),
            {
                "row": [
                    {
                        "column": [
                            _image("now_icon", size=1.4, rgb_support=True),
                            _bold("now_temp", f"-88°{t}", size=1.2),
                        ],
                        "gap": 0,
                    },
                    _line("line_1", upright=True),
                    {
                        "column": [
                            _bold("high", "Max -88°", align="left"),
                            _bold("low", "Min -88°", align="left"),
                            _bold("rain_start", "Rain from 88:00", align="left"),
                        ],
                        "gap": 0,
                    },
                ],
                "gap": 0,
                "size": 8,
            },
        ],
        "gap": 0,
    }


def six_hours(settings) -> dict:
    """The next 12 hours in 6 pairs of 2 hours: the first hour, its icon and temperature,
    and a bar with the rain of both hours."""
    rain = "8.88" if settings.rain == "inch" else "8.8"
    columns = [
        {
            "column": [
                _bold(f"pair_hour_{k}", "88", size=1),
                _image(f"pair_icon_{k}", size=1.3, rgb_support=True),
                _bold(f"pair_temp_{k}", "-88°", size=1.3),
                _image(f"pair_bar_{k}", size=1.6, fit="stretch"),
                _bold(f"pair_mm_{k}", rain, size=0.8),
            ],
            "gap": 0,
        }
        for k in range(HOURS // 2)
    ]
    return {"column": [_header(), {"row": columns, "gap": 0, "size": 8}], "gap": 0}


def steps_3h(settings) -> dict:
    """The next 12 hours in 4 steps of 3 hours, with lines between them: the icon, the
    highest temperature and the rain of each step. No wind."""
    columns = [
        {
            "column": [
                _bold(f"step_{k}", "88–88", size=1),
                _image(f"step_icon_{k}", size=1.8, rgb_support=True),
                _bold(f"step_temp_{k}", "-88°", size=1.8),
                _bold(f"step_rain_{k}", _rain_sample(settings), size=0.9),
            ],
            "gap": 0,
        }
        for k in range(HOURS // 3)
    ]
    row = {"row": _with_lines(columns, "line", True), "gap": 0, "size": 8}
    return {"column": [_header(), row], "gap": 0}


def now(settings) -> dict:
    """The current hour only, large: the icon, temperature, and the wind as a plain arrow
    with its speed."""
    return {
        "column": [
            _header(),
            {
                "row": [
                    _image("now_icon", rgb_support=True),
                    {
                        "column": [
                            _bold("now_degrees", "-88°", size=2.2),
                            {
                                "row": [
                                    _image("now_arrow", size=0.6),
                                    _bold("now_wind", "88 km/h", size=1.4, align="left"),
                                ],
                                "gap": 0,
                            },
                        ],
                        "gap": 0,
                    },
                ],
                "gap": 0,
                "size": 8,
            },
        ],
        "gap": 0,
    }


def _hour_row(i: int, rain_sample: str) -> dict:
    return {
        "row": [
            _text(f"hour_{i}", "88", size=1),
            _image(f"hicon_{i}", size=1, rgb_support=True),
            _text(f"temp_{i}", "-88°", size=1.3),
            _image(f"hbar_{i}", size=2, fit="stretch"),
            _text(f"mm_{i}", rain_sample, size=1),
            _image(f"barb_{i}", size=1.3),
        ],
        "gap": 0,
    }


def portrait_hours(settings) -> dict:
    """For tall screens: the summary on top, then one row per hour: the hour, icon,
    temperature, rain as a sideways bar with the mm, and the wind barb."""
    temperatures, rain = _samples(settings)
    rain_sample = "8.88" if settings.rain == "inch" else "8.8"
    return {
        "column": [
            _header(),
            _text("temperatures", temperatures, size=0.8, align="left"),
            _text("rain", rain, size=0.8, align="left", shrink=True),
            {"column": [_hour_row(i, rain_sample) for i in range(HOURS)], "gap": 0, "size": 12},
        ],
        "gap": 0,
    }


def portrait_now(settings) -> dict:
    """For tall screens: a large icon for the next hour, its temperature and wind barb,
    then the summary for the next 12 hours."""
    temperatures, rain = _samples(settings)
    return {
        "column": [
            _header(),
            _image("now_icon", size=5, rgb_support=True),
            {
                "row": [
                    _text("now_temp", f"-88°{settings.temperature}", size=2),
                    _image("now_barb", size=1),
                ],
                "gap": 0,
                "size": 2.5,
            },
            _text("temperatures", temperatures, size=1),
            _text("rain", rain, size=1, shrink=True),
        ],
        "gap": 0,
    }


LAYOUTS = {
    "hours_12": hours_12,
    "three_rows": three_rows,
    "three_columns": three_columns,
    "now_and_today": now_and_today,
    "six_hours": six_hours,
    "steps_3h": steps_3h,
    "now": now,
    "small": small,
    "portrait_hours": portrait_hours,
    "portrait_now": portrait_now,
}
