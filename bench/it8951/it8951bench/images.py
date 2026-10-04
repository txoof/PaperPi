"""Test images for the IT8951 test round. All images are grayscale ("L" mode).

Pixel values are multiples of 17 (0, 17, ... 255), so each one maps exactly to one
of the 16 gray levels the IT8951 can show.
"""

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

# Size of the small area used for partial and fast updates (like a clock on screen).
CLOCK_SIZE = (480, 160)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default(size)


def gray_steps(width: int, height: int) -> Image.Image:
    """16 vertical bars from black to white, each labelled with its level (0-15)."""
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    bar = width / 16
    font = _font(max(12, height // 30), bold=True)
    for level in range(16):
        x0 = round(level * bar)
        x1 = round((level + 1) * bar)
        draw.rectangle([x0, 0, x1, height], fill=level * 17)
        label_fill = 255 if level < 8 else 0
        draw.text((x0 + bar / 2, height / 2), str(level), fill=label_fill, font=font, anchor="mm")
    return img


def fine_text(width: int, height: int, title: str = "Fine text") -> Image.Image:
    """Black text from large to very small, plus thin lines, to judge sharpness."""
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    sample = "The quick brown fox jumps over the lazy dog 0123456789"
    y = 10
    draw.text((10, y), title, fill=0, font=_font(48, bold=True))
    y += 70
    for size in (40, 32, 24, 18, 14, 11, 9):
        draw.text((10, y), f"{size}px  {sample}", fill=0, font=_font(size))
        y += int(size * 1.6)
    # One-pixel and two-pixel lines, horizontal and diagonal.
    y += 20
    for i, w in enumerate((1, 1, 2, 2)):
        draw.line([(10, y + i * 12), (width - 10, y + i * 12)], fill=0, width=w)
    y += 60
    for i in range(20):
        draw.line([(10 + i * 30, y), (10 + i * 30 + 200, min(height - 10, y + 200))], fill=0)
    return img


def gradient(width: int, height: int) -> Image.Image:
    """A smooth left-to-right gradient with circles, to show banding and dithering.

    Used instead of a photo so the image is the same on every run and has no
    licence questions.
    """
    img = Image.linear_gradient("L").rotate(90).resize((width, height))
    draw = ImageDraw.Draw(img)
    for i, r in enumerate(range(min(width, height) // 3, 20, -40)):
        draw.ellipse(
            [width / 2 - r, height / 2 - r, width / 2 + r, height / 2 + r],
            outline=0 if i % 2 else 255,
            width=4,
        )
    return img


def clock(now: datetime | None = None, size: tuple[int, int] = CLOCK_SIZE) -> Image.Image:
    """A small black-and-white clock area for partial and fast updates."""
    now = now or datetime.now()
    img = Image.new("L", size, 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0] - 1, size[1] - 1], outline=0, width=3)
    draw.text(
        (size[0] / 2, size[1] / 2),
        now.strftime("%H:%M:%S"),
        fill=0,
        font=_font(int(size[1] * 0.6), bold=True),
        anchor="mm",
    )
    return img


def blank(width: int, height: int, value: int = 255) -> Image.Image:
    return Image.new("L", (width, height), value)


def to_black_white(img: Image.Image) -> Image.Image:
    """Force an image to pure black and white, as fast modes (DU, A2) need."""
    return img.point(lambda p: 255 if p >= 128 else 0)
