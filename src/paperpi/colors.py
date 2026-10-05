"""Text and background colours that a user picks in the config file.

Plugins that offer ``text_color`` and ``background_color`` settings use :data:`ColorName`
for them and :func:`screen_colors` to turn the user's choice into colours this screen can
show. A plugin passes the result as :attr:`paperpi.plugin.Drawn.colors`.
"""

from __future__ import annotations

import logging
import random
from typing import Literal

from epdlib import ScreenMode
from PIL import ImageColor

log = logging.getLogger(__name__)

#: The colours a user can pick. The common 7-colour screens can show all of them.
COLORS = ("red", "orange", "yellow", "green", "blue", "black", "white")

ColorName = Literal["red", "orange", "yellow", "green", "blue", "black", "white", "random"]

#: Used when the chosen text and background would look the same on this screen.
FALLBACK = ("white", "black")


def screen_colors(
    text: str, background: str, mode: ScreenMode, rng: random.Random
) -> tuple[str, str]:
    """The text and background colour to draw with on a screen with ``mode``.

    ``"random"`` picks one of :data:`COLORS` with ``rng``, always one that can be told
    apart from the other colour. On gray and black-and-white screens every colour becomes
    black or white, whichever is closer. If both end up the same, white on black is used
    and a warning is logged.
    """
    if background == "random":
        background = rng.choice([c for c in COLORS if text == "random" or _differ(c, text, mode)])
    if text == "random":
        text = rng.choice([c for c in COLORS if _differ(c, background, mode)])
    text, background = _shown(text, mode), _shown(background, mode)
    if text == background:
        log.warning("text and background colour look the same on this screen; using white on black")
        return FALLBACK
    return text, background


def _shown(color: str, mode: ScreenMode) -> str:
    """The colour as this screen shows it: itself on colour screens, else black or white."""
    if mode.has_color:
        return color
    return "black" if ImageColor.getcolor(color, "L") < 128 else "white"


def _differ(one: str, other: str, mode: ScreenMode) -> bool:
    return _shown(one, mode) != _shown(other, mode)
