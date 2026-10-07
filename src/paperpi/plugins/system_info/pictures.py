"""The pictures system_info draws itself: two icons and the bars.

They are drawn in the text colour (``ink``) on the background colour (``paper``), at the
exact size of their block (``content_size``), so the layout never resizes them: resizing
blurs the edges, and blurred edges show as dots on black-and-white screens.
"""

from PIL import Image, ImageDraw

ICON = 240  # the grid the icons are designed on; they are drawn at any size from it


def _canvas(width: int, height: int, paper: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), paper)
    return image, ImageDraw.Draw(image)


def _icon(side: int, paper: str):
    """A square canvas, and a function that turns grid units (0-240) into its pixels."""
    image, draw = _canvas(side, side, paper)

    def px(*units: float) -> list[int]:
        return [round(u * side / ICON) for u in units]

    return image, draw, px


def disk_icon(side: int, color: str, paper: str) -> Image.Image:
    """A disk drive seen from the front: a rounded box with two lights."""
    image, draw, px = _icon(side, paper)
    draw.rounded_rectangle(px(20, 70, 220, 190), radius=px(24)[0], fill=color)
    draw.rectangle(px(20, 70, 220, 120), fill=color)
    gap = max(1, px(8)[0])  # gap between top and front
    draw.line(px(20, 125, 220, 125), fill=paper, width=gap)
    for x in (150, 185):
        draw.rectangle(px(x, 148, x + 20, 166), fill=paper)
    return image


def chip_icon(side: int, color: str, paper: str) -> Image.Image:
    """A processor chip: a square with pins on every side."""
    image, draw, px = _icon(side, paper)
    draw.rectangle(px(50, 50, 190, 190), outline=color, width=max(1, px(18)[0]))
    draw.rectangle(px(92, 92, 148, 148), fill=color)
    for p in (78, 120, 162):
        draw.rectangle(px(p - 8, 14, p + 8, 50), fill=color)
        draw.rectangle(px(p - 8, 190, p + 8, 226), fill=color)
        draw.rectangle(px(14, p - 8, 50, p + 8), fill=color)
        draw.rectangle(px(190, p - 8, 226, p + 8), fill=color)
    return image


def bar(
    share: float | None, width: int, height: int, color: str, paper: str, *, upright: bool
) -> Image.Image:
    """A ``width`` x ``height`` bar filled to ``share`` (0-1): an outline, filled from the
    bottom (upright) or from the left. ``None`` (number not known) gives an empty outline.
    """
    share = 0.0 if share is None else max(0.0, min(1.0, share))
    image, draw = _canvas(width, height, paper)
    line = max(1, round(min(width, height) * 0.04))
    draw.rectangle((0, 0, width - 1, height - 1), outline=color, width=line)
    filled = round((height if upright else width) * share)
    if filled and upright:
        draw.rectangle((0, height - filled, width - 1, height - 1), fill=color)
    elif filled:
        draw.rectangle((0, 0, filled - 1, height - 1), fill=color)
    return image
