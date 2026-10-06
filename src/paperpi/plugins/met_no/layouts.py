"""Layouts for met_no. The first one is the default.

Block names with a number (``hour_0`` ... ``hour_11``) are filled per hour by the plugin.
Rows have no gaps, so the 6 icons (one per 2 hours) line up with the 12 hour columns.
"""

PAD = 0.008
HOURS = 12


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
            {
                "row": [
                    _text("place", "Rio de Janeiro", size=1, align="left", shrink=True),
                    _text("updated", "Updated 88:88 · Data: MET Norway", size=1.4, align="right"),
                ],
                "gap": 0,
                "size": 0.6,
            },
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


LAYOUTS = {"hours_12": hours_12}
