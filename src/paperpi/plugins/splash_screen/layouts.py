"""Layouts for splash_screen. The first one is the default.

As in v1: the name takes 6/10 of the height, the version 1/10 and the web address 3/10
(on up to 2 lines). The name is in Anton, as in v1. v1 drew the version and address in
Dosis SemiBold, which PaperPi v2 doesn't have; they use the shared Lato Bold.
"""

from ... import fonts

PADDING = 0.01


def _text(name: str, size: float, font: str, sample: str, max_lines: int = 1) -> dict:
    return {
        "name": name,
        "type": "text",
        "size": size,
        "font": font,
        "sample": sample,
        "max_lines": max_lines,
        "shrink": True,
        "align": "center",
        "padding": PADDING,
    }


LAYOUTS = {
    "splash": {
        "column": [
            _text("name", 6, fonts.ANTON, "PaperPi"),
            _text("version", 1, fonts.LATO_BOLD, "88.88.88.dev88"),
            _text("url", 3, fonts.LATO_BOLD, "https://github.com/\ntxoof/PaperPi", 2),
        ],
        "gap": 0,
        "padding": PADDING,
    },
}
