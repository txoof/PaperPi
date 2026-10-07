"""Layouts for newyorker. The first one is the default.

Blocks: ``comic`` (the picture), ``caption``, ``credit`` ("Cartoon by ...") and ``date``
(the day the cartoon came out). The shares of the height are v1's: 75% picture, 20%
caption, 5% for the small line at the bottom. The caption is in Libre Caslon Text, as in
v1; its sample is a long caption, so the font size stays the same for most cartoons, and
longer ones get smaller (``shrink``). The date is in Anton (v1's font for the time), the
credit in Lato Italic.
"""

from ... import fonts

PAD = 0.006  # about v1's 5 pixels on a 1200x825 screen
CAPTION = (
    "“Finally, a place where the news arrives only once a week, and the weather is "
    "always the same as yesterday.”"
)


def _text(name: str, font: str, sample: str, align: str, size: float = 1, **more) -> dict:
    return {
        "name": name,
        "type": "text",
        "size": size,
        "font": font,
        "sample": sample,
        "shrink": True,
        "align": align,
        "padding": PAD,
    } | more


COMIC = {"name": "comic", "type": "image", "size": 15, "fit": "contain", "padding": PAD}
CAPTION_BLOCK = _text("caption", fonts.LIBRE_CASLON_TEXT, CAPTION, "center", 4, max_lines=3)
CREDIT = _text("credit", fonts.LATO_ITALIC, "Cartoon by Firstname Longername", "right")
DATE = _text("date", fonts.ANTON, "Wednesday, September 30", "left")

LAYOUTS = {
    # The cartoon, its caption on up to 3 lines, and below them the date (left) and the
    # cartoonist (right). v1's only layout, with the date in place of the time.
    "comic_caption_date": {
        "column": [COMIC, CAPTION_BLOCK, {"row": [DATE, CREDIT], "size": 1}],
        "gap": 0,
    },
    # The cartoon, its caption and the cartoonist.
    "comic_caption": {"column": [COMIC, CAPTION_BLOCK, CREDIT], "gap": 0},
    # Only the cartoon.
    "comic_only": {"column": [COMIC | {"size": 1}], "gap": 0},
}
