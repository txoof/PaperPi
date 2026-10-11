"""Layouts for lms_client. The first one is the default. The same as librespot_client's.

Blocks: ``cover`` (the album cover), ``title``, ``artist`` and ``album``. The sizes follow
v1's layouts. Titles are in Oswald and the artist and album in Montserrat SemiBold, as in
v1. The text samples are long names, so the font size stays the same for most songs;
longer texts get smaller (``shrink``).
"""

from ... import fonts

PAD = 0.008
TITLE = "The Longest Song Title on the Whole Album"
ARTIST = "The Sample Band featuring A Guest"
ALBUM = "An Album With a Rather Long Name"


def _cover(size: float = 1) -> dict:
    return {"name": "cover", "type": "image", "size": size, "fit": "contain", "rgb_support": True}


def _text(
    name: str, sample: str, size: float, max_lines: int, font: str, align: str = "center"
) -> dict:
    return {
        "name": name,
        "type": "text",
        "font": font,
        "size": size,
        "sample": sample,
        "max_lines": max_lines,
        "shrink": True,
        "align": align,
        "padding": PAD,
    }


LAYOUTS = {
    # The cover with the artist and album next to it, the title below (v1's default).
    "two_column_three_row": {
        "column": [
            {
                "row": [
                    _cover(4),
                    {
                        "column": [
                            _text("artist", ARTIST, 4, 3, fonts.MONTSERRAT_SEMIBOLD, "left"),
                            _text("album", ALBUM, 1, 2, fonts.MONTSERRAT_SEMIBOLD, "left"),
                        ],
                        "gap": 0,
                        "size": 6,
                    },
                ],
                "gap": 0,
                "size": 5,
            },
            _text("title", TITLE, 5, 2, fonts.OSWALD_MEDIUM, "left"),
        ],
        "gap": 0,
    },
    # A large cover with the title below it.
    "album_art_title": {
        "column": [_cover(8), _text("title", TITLE, 2, 2, fonts.OSWALD_REGULAR)],
        "gap": 0,
    },
    # Only the cover.
    "cover_art_only": {"column": [_cover()], "gap": 0},
    # The title and the artist, no cover.
    "two_rows_text_only": {
        "column": [
            _text("title", TITLE, 8, 2, fonts.OSWALD_REGULAR),
            _text("artist", ARTIST, 2, 2, fonts.MONTSERRAT_SEMIBOLD),
        ],
        "gap": 0,
    },
    # The title, the artist and the album, no cover.
    "three_rows_text_only": {
        "column": [
            _text("title", TITLE, 7.5, 2, fonts.OSWALD_MEDIUM, "left"),
            _text("artist", ARTIST, 1.8, 2, fonts.MONTSERRAT_SEMIBOLD),
            _text("album", ALBUM, 0.7, 1, fonts.MONTSERRAT_SEMIBOLD),
        ],
        "gap": 0,
    },
}
