"""Wind barbs, drawn in the look of PaperPi v1.

A barb is a line with an arrowhead that points where the wind is going. Feathers at the
other end (the tail) give the speed in knots, rounded to steps of 5:

- a short feather is 5 knots, a long feather 10, a triangle 50;
- under 1 knot (calm) the barb is a circle;
- above 105 knots it is a warning triangle with "!".

Drawn as shapes at any angle, at four times the size and then scaled down, so the edges
stay smooth.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

SIZE = 250  # the barb is designed on a 250 x 250 square, like v1's pictures
CALM = 1.0
STORM = 105.0
_SCALE = 4


def steps(knots: float) -> tuple[int, int, int]:
    """Triangles (50), long feathers (10) and short feathers (5) for a speed in knots."""
    value = int(knots / 5 + 0.5) * 5
    return value // 50, value % 50 // 10, value % 10 // 5


def barb(knots: float, wind_from: float, size: int = SIZE, color: str = "black") -> Image.Image:
    """A ``size`` x ``size`` picture of a barb for wind of ``knots`` coming from the
    direction ``wind_from`` (degrees: 0 = from the north, 90 = from the east)."""
    big = size * _SCALE
    image = Image.new("L", (big, big), 255)
    draw = ImageDraw.Draw(image)
    unit = big / SIZE  # one unit of the 250-unit design, in pixels of the big picture
    ink = 0 if color == "black" else 255
    width = round(8 * unit)  # v1 used 6; a little thicker reads better on small screens
    if knots < CALM:
        r = 95 * unit
        c = big / 2
        draw.ellipse((c - r, c - r, c + r, c + r), outline=ink, width=width)
    elif knots > STORM:
        _warning(draw, unit, ink, width)
    else:
        _barb(draw, knots, (wind_from + 180) % 360, unit, ink, width)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _barb(draw, knots, toward, unit, ink, width):
    """Drawn as if pointing north, with (0, 0) in the middle; turned by ``toward``."""
    angle = math.radians(toward)
    centre = SIZE / 2

    def at(x, y):
        # Turn clockwise by ``angle`` (compass direction), then move to the picture.
        tx = x * math.cos(angle) - y * math.sin(angle)
        ty = x * math.sin(angle) + y * math.cos(angle)
        return ((centre + tx) * unit, (centre + ty) * unit)

    tip, tail = -103, 80  # the arrow's point and the line's other end (y grows downwards)
    draw.line([at(0, tip + 25), at(0, tail)], fill=ink, width=width)
    draw.polygon([at(0, tip), at(-14, tip + 30), at(14, tip + 30)], fill=ink)
    triangles, longs, shorts = steps(knots)
    y = tail
    for _ in range(triangles):
        draw.polygon([at(0, y), at(0, y - 36), at(-64, y - 16)], fill=ink)
        y -= 40
    for _ in range(longs):
        draw.line([at(0, y), at(-70, y + 22)], fill=ink, width=width)
        y -= 16
    for _ in range(shorts):
        if y == tail:
            y -= 8  # a lone short feather sits a little up the line, as in v1
        draw.line([at(0, y), at(-35, y + 11)], fill=ink, width=width)
        y -= 16


def _warning(draw, unit, ink, width):
    def p(x, y):
        return (x * unit, y * unit)

    draw.polygon([p(125, 22), p(20, 205), p(230, 205)], outline=ink, width=width)
    draw.rounded_rectangle([p(117, 70), p(133, 150)], radius=6 * unit, fill=ink)
    draw.ellipse([p(115, 165), p(135, 185)], fill=ink)
