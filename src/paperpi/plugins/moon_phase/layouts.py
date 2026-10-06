"""Layouts for moon_phase. The first one is the default.

Blocks: ``moon`` (the picture), ``moonrise`` and ``moonset`` ("Moonrise: 01:38"), ``phase``
("Waning Crescent") and ``credit`` ("Data: MET Norway · Image: NASA SVS"). White on black,
like the night sky.
"""

from pathlib import Path

FONT = str(Path(__file__).parent / "fonts" / "Anton-Regular.ttf")
PAD = 0.01
NIGHT = {"fill": "white", "background": "black"}


def _text(name: str, sample: str, size: float, align: str = "center", pad=PAD) -> dict:
    return {
        "name": name,
        "type": "text",
        "size": size,
        "font": FONT,
        "sample": sample,
        "align": align,
        "padding": pad,
        **NIGHT,
    }


def _moon(size: float = 1) -> dict:
    return {"name": "moon", "type": "image", "size": size, "padding": PAD, **NIGHT}


def moon_data(settings) -> dict:
    """Moonrise and moonset on top, the moon, then the name of the phase."""
    return {
        "column": [
            {
                "row": [
                    _text("moonrise", "Moonrise: 88:88", 1, "left"),
                    _text("moonset", "Moonset: 88:88", 1, "left"),
                ],
                "gap": 0,
                "size": 0.7,
            },
            _moon(8.4),
            _text("phase", "Waxing Crescent", 1),
            _text("credit", "Data: MET Norway · Image: NASA SVS", 0.4, "right", pad=PAD / 4),
        ],
        "gap": 0,
    }


def moon_only(settings) -> dict:
    """The moon only, as large as fits."""
    return {"column": [_moon()], "gap": 0}


LAYOUTS = {"moon_data": moon_data, "moon_only": moon_only}
