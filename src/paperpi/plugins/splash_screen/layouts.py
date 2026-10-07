"""Layouts for splash_screen. The first one is the default.

As in v1, the name is in Anton and the rest in Dosis SemiBold. Below the name and version:
the web interface's address (by IP address) next to a QR code with the same address, and
PaperPi's GitHub address at the bottom.
"""

from ... import fonts

PADDING = 0.01

#: The text blocks that hold an address; ``draw`` breaks these after a "/" when needed.
ADDRESS_BLOCKS = ("ip", "github")

# The longest web address: the longest IP address and port.
WEB_SAMPLE = "http://255.255.255.255:65535"


def _text(name: str, size: float, font: str, sample: str, max_lines: int = 1) -> dict:
    return {
        "name": name,
        "type": "text",
        "size": size,
        "font": font,
        "sample": sample,
        "max_lines": max_lines,
        "shrink": True,
        "align": "center",
        "padding": PADDING,
    }


LAYOUTS = {
    "splash": {
        "column": [
            _text("name", 4, fonts.ANTON, "PaperPi"),
            _text("version", 1, fonts.DOSIS_SEMIBOLD, "88.88.88.dev88"),
            {
                "row": [
                    _text("ip", 3, fonts.DOSIS_SEMIBOLD, WEB_SAMPLE, 2),
                    # Drawn at its exact size in draw(), so it is never scaled again.
                    {"name": "qr", "type": "image", "size": 1, "fit": "none"},
                ],
                "size": 4,
                "gap": 0,
            },
            _text("github", 1, fonts.DOSIS_SEMIBOLD, "https://github.com/txoof/PaperPi", 2),
        ],
        "gap": 0,
        "padding": PADDING,
    },
}
