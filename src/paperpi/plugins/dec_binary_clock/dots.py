"""The picture of the clock: one column of 4 dots for each digit of the time.

Each column shows one digit (0-9) in binary: from top to bottom the dots are worth 8, 4, 2
and 1. A filled dot is "on", a ring is "off"; the digit is the sum of the filled dots. A
bar between the hour and the minute columns stands for the colon.

The sizes keep v1's proportions. They are counted in "units"; one unit is an eighth of the
radius of a dot, and the picture is scaled by choosing how many pixels a unit is.
"""

from PIL import Image, ImageDraw

BITS = (8, 4, 2, 1)  # the value of each dot, top to bottom
DOT = 16  # diameter of a dot, in units
RING = 1  # width of the ring of an "off" dot
GAP = 1  # space around each dot
BAR = 4  # width of the bar between hours and minutes
COLUMN = DOT + 2 * GAP
WIDE = 4 * COLUMN + BAR  # the whole picture, in units
HIGH = len(BITS) * DOT + (len(BITS) + 1) * GAP


def digit_bits(digit: int) -> tuple[bool, ...]:
    """Which dots of a column are on for ``digit``, top (8) to bottom (1)."""
    if not 0 <= digit <= 9:
        raise ValueError(f"a column shows one digit, 0-9, not {digit}")
    return tuple(bool(digit & value) for value in BITS)


def time_columns(hour: int, minute: int) -> list[tuple[bool, ...]]:
    """The four columns for a 24-hour time: tens and ones of the hour, then of the minute."""
    digits = (hour // 10, hour % 10, minute // 10, minute % 10)
    return [digit_bits(d) for d in digits]


def picture(hour: int, minute: int, width: int, height: int) -> Image.Image:
    """The clock as a black-on-white picture of exactly ``width`` x ``height`` pixels.

    It is drawn at the size it will be shown, so the layout never scales it: scaling would
    blur the edges, and blurred edges show as dots on black-and-white screens.
    """
    image = Image.new("L", (width, height), 255)
    unit = min(width / WIDE, height / HIGH)
    if DOT * unit < 2:
        return image  # too small for a dot: leave it white
    draw = ImageDraw.Draw(image)
    # Centre the picture in the space it has.
    left = (width - WIDE * unit) / 2
    top = (height - HIGH * unit) / 2
    ring = max(1, round(RING * unit))
    x = left
    for index, column in enumerate(time_columns(hour, minute)):
        if index == 2:
            # The bar is as high as the whole picture, as in v1.
            draw.rectangle(
                (round(x), round(top), round(x + BAR * unit) - 1, round(top + HIGH * unit) - 1),
                fill=0,
            )
            x += BAR * unit
        for row, on in enumerate(column):
            x0 = x + GAP * unit
            y0 = top + (GAP + row * (DOT + GAP)) * unit
            box = (round(x0), round(y0), round(x0 + DOT * unit) - 1, round(y0 + DOT * unit) - 1)
            if on:
                draw.ellipse(box, fill=0)
            else:
                draw.ellipse(box, outline=0, width=ring)
        x += COLUMN * unit
    return image
