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
                    _text("updated", "Updated 88:88", size=1, align="right"),
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


def _header() -> dict:
    return {
        "row": [
            _text("place", "Rio de Janeiro", size=1, align="left", shrink=True),
            _text("updated", "Updated 88:88", size=1, align="right"),
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
    """For tiny screens: a big icon for the next hour; the temperature now, then max, min
    and rain for the next 12 hours. No wind barb."""
    temperatures, rain = _samples(settings)
    return {
        "row": [
            _image("now_icon", size=2, rgb_support=True),
            {
                "column": [
                    _text("now_temp", f"-88°{settings.temperature}", size=1.4, align="left"),
                    _text("temperatures", temperatures, align="left"),
                    _text("rain", rain, align="left", shrink=True),
                ],
                "gap": 0,
                "size": 3,
            },
        ],
        "gap": 0,
    }


def _step(k: int, rain_unit: str) -> dict:
    return {
        "column": [
            _text(f"step_{k}", "88–88", size=1),
            _image(f"step_icon_{k}", size=2.2, rgb_support=True),
            _text(f"step_temp_{k}", "-88–-88°", size=1.2),
            _text(f"step_rain_{k}", f"88.8 {rain_unit}", size=0.9),
            _image(f"step_barb_{k}", size=2),
        ],
        "gap": 0,
    }


def steps_3h(settings) -> dict:
    """The next 12 hours in 4 steps of 3 hours: icon, lowest and highest temperature, rain
    and the wind at the middle hour of each step."""
    unit = "in" if settings.rain == "inch" else "mm"
    return {
        "column": [
            _header(),
            _text("summary", " · ".join(_samples(settings)), size=1, align="left"),
            {"row": [_step(k, unit) for k in range(HOURS // 3)], "gap": 0, "size": 7},
        ],
        "gap": 0,
    }


def now(settings) -> dict:
    """The next hour, large: icon, temperature and wind barb, with the summary below."""
    return {
        "column": [
            _header(),
            {
                "row": [
                    _image("now_icon", size=3, rgb_support=True),
                    {
                        "column": [
                            _text("now_temp", f"-88°{settings.temperature}", size=3),
                            _image("now_barb", size=2),
                        ],
                        "gap": 0,
                        "size": 2,
                    },
                ],
                "gap": 0,
                "size": 6,
            },
            _text("summary", " · ".join(_samples(settings)), size=1, align="left"),
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
    "small": small,
    "steps_3h": steps_3h,
    "now": now,
    "portrait_hours": portrait_hours,
    "portrait_now": portrait_now,
}
