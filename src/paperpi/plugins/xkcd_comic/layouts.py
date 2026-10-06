"""Layouts for xkcd_comic. The first one is the default.

Blocks: ``comic`` (the picture), ``title`` and ``alt`` (the comic's hover text). The comic
block has no padding: the plugin needs its exact size to leave small comics at their own
size (see ``enlarge`` in ``__init__.py``). The text samples are a long title and a long
hover text, so the font size stays the same for most comics; longer texts get smaller
(``shrink``).
"""

PAD = 0.008
TITLE = "Extrapolating a Long Comic Title"
ALT = (
    "I've developed a more logical set of rules but the people on the chess community have "
    "a bunch of stupid emotional biases and won't reply to my posts."
)


def _comic(size: float) -> dict:
    return {"name": "comic", "type": "image", "size": size, "fit": "contain"}


def _text(name: str, sample: str, size: float, max_lines: int, align: str = "center") -> dict:
    return {
        "name": name,
        "type": "text",
        "size": size,
        "sample": sample,
        "max_lines": max_lines,
        "shrink": True,
        "align": align,
        "padding": PAD,
    }


LAYOUTS = {
    # The comic, its title on one line and the hover text on up to 3 lines,
    # lines starting at the left like v1 (v1's default layout).
    "comic_title_alttext": {
        "column": [_comic(7.5), _text("title", TITLE, 1, 1), _text("alt", ALT, 1.5, 3, "left")],
        "gap": 0,
    },
    # The comic and its title, on up to 2 lines.
    "comic_title": {"column": [_comic(8), _text("title", TITLE, 2, 2)], "gap": 0},
    # Only the comic.
    "comic_only": {"column": [_comic(1)], "gap": 0},
}
