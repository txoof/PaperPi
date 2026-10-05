"""The pictures system_info draws itself: two icons and the bars.

They are drawn in the text colour (``ink``) on the background colour (``paper``). Icons
are drawn large and scaled down by the layout; bars are stretched to their block.
"""

from PIL import Image, ImageDraw

ICON = 240  # pixels; the layout scales it to fit


def _canvas(width: int, height: int, paper: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), paper)
    return image, ImageDraw.Draw(image)


def disk_icon(color: str, paper: str) -> Image.Image:
    """A disk drive seen from the front: a rounded box with two lights."""
    image, draw = _canvas(ICON, ICON, paper)
    draw.rounded_rectangle((20, 70, 220, 190), radius=24, fill=color)
    draw.rectangle((20, 70, 220, 120), fill=color)
    draw.line((20, 125, 220, 125), fill=paper, width=8)  # gap between top and front
    for x in (150, 185):
        draw.rectangle((x, 148, x + 20, 166), fill=paper)
    return image


def chip_icon(color: str, paper: str) -> Image.Image:
    """A processor chip: a square with pins on every side."""
    image, draw = _canvas(ICON, ICON, paper)
    draw.rectangle((50, 50, 190, 190), outline=color, width=18)
    draw.rectangle((92, 92, 148, 148), fill=color)
    for p in (78, 120, 162):
        draw.rectangle((p - 8, 14, p + 8, 50), fill=color)
        draw.rectangle((p - 8, 190, p + 8, 226), fill=color)
        draw.rectangle((14, p - 8, 50, p + 8), fill=color)
        draw.rectangle((190, p - 8, 226, p + 8), fill=color)
    return image


def bar(share: float | None, color: str, paper: str, *, upright: bool) -> Image.Image:
    """A bar filled to ``share`` (0-1): an outline, filled from the bottom (upright) or
    from the left. ``None`` (number not known) gives an empty outline."""
    share = 0.0 if share is None else max(0.0, min(1.0, share))
    long, short = 400, 60
    # Stretched to its block, the short side grows most, so the lines along the long side
    # are drawn thinner, to look about as thick as the ends.
    thin, thick = 2, 4
    if upright:
        width, height, across, along = short, long, thin, thick
    else:
        width, height, across, along = long, short, thick, thin
    image, draw = _canvas(width, height, paper)
    draw.rectangle((0, 0, width - 1, along - 1), fill=color)  # top
    draw.rectangle((0, height - along, width - 1, height - 1), fill=color)  # bottom
    draw.rectangle((0, 0, across - 1, height - 1), fill=color)  # left
    draw.rectangle((width - across, 0, width - 1, height - 1), fill=color)  # right
    filled = round(long * share)
    if filled and upright:
        draw.rectangle((0, height - filled, width - 1, height - 1), fill=color)
    elif filled:
        draw.rectangle((0, 0, filled - 1, height - 1), fill=color)
    return image
