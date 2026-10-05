"""Layouts for basic_clock. The first one is the default.

Each layout is a function of the settings, because a 12-hour time ("10:42 AM") needs a
wider sample than a 24-hour time ("88:88"). The samples are the widest texts each block
shows, so the font size never changes from one minute to the next.
"""

PADDING = 0.03
DATE_SAMPLE = "Wednesday 30 September"


def time_sample(settings) -> str:
    return "88:88 AM" if settings.hours == 12 else "88:88"


def time(settings) -> dict:
    """The time only, as large as fits."""
    return {
        "column": [
            {
                "name": "time",
                "type": "text",
                "sample": time_sample(settings),
                "align": "center",
                "padding": PADDING,
            }
        ]
    }


def time_date(settings) -> dict:
    """A large time with the date below it."""
    return {
        "column": [
            {
                "name": "time",
                "type": "text",
                "size": 3,
                "sample": time_sample(settings),
                "align": "center",
                "valign": "bottom",
                "padding": PADDING,
            },
            {
                "name": "date",
                "type": "text",
                "size": 1,
                "sample": DATE_SAMPLE,
                "align": "center",
                "valign": "top",
                "padding": PADDING,
            },
        ]
    }


LAYOUTS = {"time": time, "time_date": time_date}
