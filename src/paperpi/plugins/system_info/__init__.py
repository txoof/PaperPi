"""system_info: hostname, network address, disk, processor and memory use of this Pi."""

import random
from datetime import datetime

from pydantic import Field

from ... import __version__
from ...colors import ColorName, screen_colors
from ...plugin import Context, Drawn, Plugin, PluginSettings, ready
from . import pictures, readers
from .layouts import LAYOUTS
from .readers import Info

#: Temperature at the top of the bar: the Pi slows itself down from about 85 °C.
HOT = 85.0
UNKNOWN = "?"


class Settings(PluginSettings):
    text_color: ColorName = Field(
        "black", description="Colour of the text on colour screens, or random"
    )
    background_color: ColorName = Field(
        "white", description="Colour of the background on colour screens, or random"
    )


def fetch(context: Context):
    used, total = readers.disk()
    return ready(
        Info(
            hostname=readers.hostname(),
            ip=readers.ip_address(),
            wifi=readers.wifi(),
            disk_used=used,
            disk_total=total,
            temperature=readers.temperature(),
            load=readers.load(),
            memory=readers.memory(),
            uptime=readers.uptime(),
            version=__version__,
            time=f"{datetime.now():%H:%M}",
        )
    )


def disk_text(used: int | None, total: int | None) -> str:
    """ "12 of 31 GB used"; TB with one decimal from 1 TB on."""
    if used is None or not total:
        return f"disk {UNKNOWN}"
    if total >= 1e12:
        return f"{used / 1e12:.1f} of {total / 1e12:.1f} TB used"
    return f"{used / 1e9:.0f} of {total / 1e9:.0f} GB used"


def uptime_text(seconds: float | None) -> str:
    if seconds is None:
        return f"up {UNKNOWN}"
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"up {days} day{'s' if days != 1 else ''} {hours} h"
    if hours:
        return f"up {hours} h {minutes} min"
    return f"up {minutes} min"


def percent(value: float | None) -> str:
    return UNKNOWN if value is None else f"{value:.0f}%"


def degrees(value: float | None) -> str:
    return UNKNOWN if value is None else f"{value:.0f}°C"


def share(value: float | None, top: float = 100.0) -> float | None:
    return None if value is None else value / top


def draw(info: Info, context: Context) -> Drawn:
    settings = context.settings
    # Random colours stay the same for a day, so the screen isn't rewritten for them alone.
    rng = random.Random(int(f"{datetime.now():%Y%m%d}"))
    colors = screen_colors(settings.text_color, settings.background_color, context.mode, rng)
    ink, paper = colors
    hostname = info.hostname or UNKNOWN
    ip = info.ip or "no network"
    wifi = "" if info.wifi is None else f"Wi-Fi {info.wifi}%"
    disk_share = share(info.disk_used, info.disk_total or None) if info.disk_total else None
    load_now = info.load[0] if info.load else None
    if context.layout == "small":
        values = {"hostname": hostname, "ip": ip, "temp": degrees(info.temperature)}
    elif context.layout == "portrait":
        values = {
            "hostname": hostname,
            "network": " · ".join(filter(None, [ip, wifi])),
            "uptime": uptime_text(info.uptime),
            "about": f"PaperPi {info.version} · {info.time}",
        }
        gauges = {
            "disk": (disk_share, percent(None if disk_share is None else disk_share * 100)),
            "memory": (share(info.memory), percent(info.memory)),
            "load": (share(load_now), percent(load_now)),
            "temp": (share(info.temperature, HOT), degrees(info.temperature)),
        }
        for name, (part, text) in gauges.items():
            values[f"{name}_bar"] = pictures.bar(part, ink, paper, upright=True)
            values[f"{name}_label"] = name
            values[f"{name}_value"] = text
    else:
        load = " · ".join(percent(x) for x in info.load) if info.load else UNKNOWN
        values = {
            "hostname": hostname,
            "ip": ip,
            "wifi": wifi,
            "disk_icon": pictures.disk_icon(ink, paper),
            "disk": disk_text(info.disk_used, info.disk_total),
            "disk_bar": pictures.bar(disk_share, ink, paper, upright=False),
            "cpu_icon": pictures.chip_icon(ink, paper),
            "cpu": f"{degrees(info.temperature)} · memory {percent(info.memory)}",
            "load": f"load {load}",
            "about": f"{uptime_text(info.uptime)} · PaperPi {info.version}",
            "time": info.time,
        }
    return Drawn(values, colors=colors)


PLUGIN = Plugin(
    type="system_info",
    description="Hostname, network address, disk, processor and memory use of this Pi.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=Info(
        hostname="paperpi",
        ip="192.0.2.10",
        wifi=77,
        disk_used=12_400_000_000,
        disk_total=31_200_000_000,
        temperature=51.2,
        load=(12.0, 8.8, 7.5),
        memory=62.0,
        uptime=12 * 86400 + 4 * 3600 + 20 * 60,
        version="2.0.0",
        time="09:04",
    ),
    refresh=120,
    refresh_on_minute=True,
)
