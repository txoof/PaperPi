"""Layouts for dec_binary_clock. The first one is the default."""

from ... import fonts

FONT = fonts.ANTON
PADDING = 0.01

#: The picture of the dots. ``draw`` makes the picture exactly the size of the block's
#: drawing area, so epdlib doesn't scale it.
DOTS = {"name": "dots", "type": "image", "size": 8, "fit": "contain", "padding": 0}

LAYOUTS = {
    # As in v1: the dots take 8/9 of the height, the time in digits is underneath and moves
    # left and right at every update.
    "dots_time": {
        "column": [
            DOTS,
            {
                "name": "time",
                "type": "text",
                "size": 1,
                "font": FONT,
                "sample": "88:88",
                "align": "random",
                "padding": PADDING,
            },
        ],
        "gap": 0,
        "padding": PADDING,
    },
}
