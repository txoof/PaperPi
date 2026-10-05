"""Layouts for system_info. The first one is the default.

Every block has ``rgb_support``, so the user's text and background colours apply to all of
them. Text blocks have samples (the widest text they normally show), so font sizes don't
change between updates.
"""

PAD = 0.015


def _text(name, sample, size=1, align="left", **more) -> dict:
    return {
        "name": name,
        "type": "text",
        "size": size,
        "sample": sample,
        "align": align,
        "padding": PAD,
        "rgb_support": True,
        **more,
    }


def _image(name, size=1, fit="contain") -> dict:
    return {
        "name": name,
        "type": "image",
        "size": size,
        "fit": fit,
        "padding": PAD,
        "rgb_support": True,
    }


def _line(name) -> dict:
    return {"name": name, "type": "shape", "shape": "hline", "pixels": 4, "rgb_support": True}


HOSTNAME = "raspberrypi-88"
IP = "888.888.888.888"
WIFI = "Wi-Fi 100%"
DISK = "888 of 888 GB used"
CPU = "88°C · memory 100%"
LOAD = "load 100% · 100% · 100%"
UPTIME = "up 888 days 23 h"
VERSION = "PaperPi 8.8.8a8"


# Text sizes in the wide layout, as shares of the screen's shorter side, so blocks in a row
# use the same size. ``shrink`` makes an unusually long hostname smaller instead of cut off.
SMALL, LARGE = 0.055, 0.07


def full(settings) -> dict:
    """Everything, laid out like v1: network on top, a disk row and a processor row with
    icons, then uptime, version and the time."""
    return {
        "column": [
            {
                "row": [
                    _text("hostname", HOSTNAME, font_size=SMALL, shrink=True),
                    _text("ip", IP, align="center", font_size=SMALL),
                    _text("wifi", WIFI, align="right", font_size=SMALL),
                ],
                "gap": 0,
                "size": 1,
            },
            _line("line1"),
            {
                "row": [
                    _image("disk_icon"),
                    {
                        "column": [
                            _text("disk", DISK, font_size=LARGE),
                            _image("disk_bar", fit="stretch"),
                        ],
                        "gap": 0,
                        "size": 3,
                    },
                ],
                "gap": 0,
                "size": 2,
            },
            _line("line2"),
            {
                "row": [
                    _image("cpu_icon"),
                    {
                        "column": [
                            _text("cpu", CPU, font_size=LARGE),
                            _text("load", LOAD, font_size=LARGE),
                        ],
                        "gap": 0,
                        "size": 3,
                    },
                ],
                "gap": 0,
                "size": 2,
            },
            _line("line3"),
            {
                "row": [
                    _text("about", f"{UPTIME} · {VERSION}", size=3, font_size=SMALL),
                    _text("time", "88:88", align="right"),
                ],
                "gap": 0,
                "size": 1,
            },
        ],
        "gap": 0,
    }


def _gauge(name: str) -> dict:
    return {
        "column": [
            _image(f"{name}_bar", size=6, fit="stretch"),
            _text(f"{name}_label", "memory", align="center"),
            _text(f"{name}_value", "100%", align="center"),
        ],
        "gap": 0,
    }


def portrait(settings) -> dict:
    """For tall screens: network on top, four upright bars (disk, memory, load,
    temperature) with their numbers, then uptime, version and the time."""
    return {
        "column": [
            _text("hostname", HOSTNAME),
            _text("network", f"{IP} · {WIFI}"),
            _line("line1"),
            {"row": [_gauge(n) for n in ("disk", "memory", "load", "temp")], "gap": 0, "size": 7},
            _line("line2"),
            _text("uptime", UPTIME),
            _text("about", f"{VERSION} · 88:88"),
        ],
        "gap": 0,
    }


def small(settings) -> dict:
    """For tiny screens: what is this Pi's address, and is it too hot?"""
    return {
        "column": [_text("hostname", HOSTNAME), _text("ip", IP), _text("temp", "88°C")],
        "gap": 0,
    }


LAYOUTS = {"full": full, "portrait": portrait, "small": small}
