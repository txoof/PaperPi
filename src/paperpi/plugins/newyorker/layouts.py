"""Layouts for newyorker.

Blocks: ``comic`` (the picture), ``caption`` and ``time`` (when the cartoon was fetched).
The shares of the height are v1's: 75% picture, 20% caption, 5% time. The caption's sample
is a long caption, so the font size stays the same for most cartoons; longer ones get
smaller (``shrink``). v1's caption font, Libre Caslon Text, is not one of PaperPi's shared
fonts, so the caption is in Lato Italic; the time is in Anton, as in v1.
"""

from ... import fonts

PAD = 0.006  # about v1's 5 pixels on a 1200x825 screen
CAPTION = (
    "A drawing that riffs on the latest news and happenings, with a caption long enough "
    "to take three lines."
)

LAYOUTS = {
    # The cartoon, its caption on up to 3 lines and the time at the bottom left (v1's
    # only layout).
    "comic_caption_time": {
        "column": [
            {"name": "comic", "type": "image", "size": 15, "fit": "contain", "padding": PAD},
            {
                "name": "caption",
                "type": "text",
                "size": 4,
                "font": fonts.LATO_ITALIC,
                "sample": CAPTION,
                "max_lines": 3,
                "shrink": True,
                "align": "center",
                "padding": PAD,
            },
            {
                "name": "time",
                "type": "text",
                "size": 1,
                "font": fonts.ANTON,
                "sample": "88:88",
                "valign": "top",
                "padding": PAD,
            },
        ],
        "gap": 0,
    },
}
