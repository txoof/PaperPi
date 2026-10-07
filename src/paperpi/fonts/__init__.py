"""Fonts that any plugin may use in its layouts, as the ``font`` of a text block.

Each name here is the full path of a font file in this folder, for example::

    from paperpi import fonts

    {"name": "title", "type": "text", "font": fonts.LATO_BOLD}

Without a ``font``, epdlib uses its own DejaVu Sans. Licences: ``Anton-OFL.txt``,
``Dosis-OFL.txt``, ``Lato-OFL.txt``.
"""

from pathlib import Path

FOLDER = Path(__file__).parent

#: Anton by The Anton Project Authors, under the SIL Open Font License 1.1, from Google Fonts.
ANTON = str(FOLDER / "Anton-Regular.ttf")

#: Dosis SemiBold by Edgar Tolentino, Pablo Impallari and Igino Marini, under the SIL Open
#: Font License 1.1, from Google Fonts: the static SemiBold file that PaperPi v1 shipped.
DOSIS_SEMIBOLD = str(FOLDER / "Dosis-SemiBold.ttf")

#: Lato Bold and Lato Italic by Łukasz Dziedzic, under the SIL Open Font License 1.1, from
#: Google Fonts (github.com/google/fonts, folder ofl/lato).
LATO_BOLD = str(FOLDER / "Lato-Bold.ttf")
LATO_ITALIC = str(FOLDER / "Lato-Italic.ttf")
