"""moon_phase: today's moon, with the times it rises and sets, from met.no."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from pydantic import Field

from ... import webrequest
from ...files import write_atomic
from ...plugin import Context, Plugin, PluginSettings, ready
from .layouts import LAYOUTS

log = logging.getLogger(__name__)

URL = "https://api.met.no/weatherapi/sunrise/3.0/moon"
SAVED = "moon.json"
#: met.no's data licence (CC BY 4.0) asks for credit; it is shown on the screen.
CREDIT = "Data: MET Norway"
#: The new moon, quarters and full moon are moments; their name is shown for this many
#: degrees on each side (the moon moves about 12° a day, so about a day in all).
MOMENT = 6.0
NAMES = (
    "New Moon",
    "Waxing Crescent",
    "First Quarter",
    "Waxing Gibbous",
    "Full Moon",
    "Waning Gibbous",
    "Last Quarter",
    "Waning Crescent",
)
#: Gray levels of the drawn moon: the sunlit part, and the dark part (lit faintly by the
#: earth, as in a photo), on a black sky.
LIT, DARK = 255, 45


class Settings(PluginSettings):
    lat: float | None = Field(
        None, ge=-90, le=90, description="Latitude of the place, e.g. 52.52 (required)"
    )
    lon: float | None = Field(
        None, ge=-180, le=180, description="Longitude of the place, e.g. 13.40 (required)"
    )
    email: str = Field(
        "",
        max_length=200,
        pattern=r"^$|^[^@\s]+@[^@\s]+$",
        description="Your email address, sent only to met.no (required: met.no asks for it)",
    )


@dataclass(frozen=True)
class Moon:
    """The moon on one day at one place, as met.no gives it.

    ``phase`` is in degrees: 0 new moon, 90 first quarter, 180 full moon, 270 last quarter.
    ``rise`` and ``set`` are ``None`` on days the moon doesn't rise or set. ``zone`` is the
    time zone to show the times in (``None``: this computer's own; set for the sample).
    """

    day: str  # "2026-10-06"
    place: str  # the rounded coordinates, "52.5200,13.4000"
    phase: float
    rise: datetime | None
    set: datetime | None
    zone: str | None = None


class SettingsMissing(ValueError):
    pass


class MoonError(ValueError):
    """met.no's answer (or the saved file) can't be read."""


def fetch(context: Context):
    settings = context.settings
    if settings.lat is None or settings.lon is None or not settings.email:
        raise SettingsMissing(
            "moon_phase needs the settings lat, lon and email (met.no asks every program "
            "for contact details)"
        )
    today = datetime.now().astimezone()
    place = f"{settings.lat:.4f},{settings.lon:.4f}"  # met.no asks for at most 4 decimals
    path = context.storage / SAVED
    saved = load(path)
    if saved and saved.day == today.date().isoformat() and saved.place == place:
        return ready(saved)  # met.no gives one answer per day: no need to ask again
    moon = download(settings, place, today)
    try:
        write_atomic(path, save(moon))
    except OSError as error:
        log.warning("can't save the moon data, showing it anyway: %s", error)
    return ready(moon)


def download(settings: Settings, place: str, today: datetime) -> Moon:
    lat, lon = place.split(",")
    offset = today.strftime("%z")  # "+0200"; met.no wants "+02:00"
    answer = webrequest.get(
        f"{URL}?lat={lat}&lon={lon}&date={today.date().isoformat()}"
        f"&offset={offset[:3]}:{offset[3:]}",
        contact=settings.email,
    )
    return parse(answer.json(), today.date(), place)


def parse(answer: dict, day: date, place: str) -> Moon:
    try:
        properties = answer["properties"]
        phase = float(properties["moonphase"])
        rise, set_ = (_time(properties.get(key)) for key in ("moonrise", "moonset"))
    except (KeyError, TypeError, ValueError) as error:
        raise MoonError(f"met.no's moon answer can't be read: {error!r}") from None
    if not 0 <= phase <= 360:
        raise MoonError(f"met.no's moon phase is out of range: {phase}")
    return Moon(day.isoformat(), place, phase, rise, set_)


def _time(event: dict | None) -> datetime | None:
    """The time of a moonrise or moonset; met.no leaves it out, or gives no time, on days
    without one."""
    if not event or event.get("time") is None:
        return None
    return datetime.fromisoformat(event["time"])


def save(moon: Moon) -> bytes:
    times = {k: t.isoformat() if t else None for k, t in (("rise", moon.rise), ("set", moon.set))}
    return json.dumps({"day": moon.day, "place": moon.place, "phase": moon.phase} | times).encode()


def load(path) -> Moon | None:
    """The saved moon data, or ``None`` when it is missing or can't be read."""
    try:
        data = json.loads(path.read_bytes())
        rise, set_ = (datetime.fromisoformat(t) if t else None for t in (data["rise"], data["set"]))
        return Moon(str(data["day"]), str(data["place"]), float(data["phase"]), rise, set_)
    except (OSError, ValueError, KeyError, TypeError):
        return None


# --- Drawing ---------------------------------------------------------------------------------


def phase_name(phase: float) -> str:
    """ "Waxing Crescent", "Full Moon", ...: the name of the phase in degrees."""
    for i, moment in enumerate((0, 90, 180, 270, 360)):
        if abs(phase - moment) <= MOMENT:
            return NAMES[2 * i % len(NAMES)]
    return NAMES[2 * int(phase // 90) + 1]


def moon_picture(phase: float, size: int = 1000) -> Image.Image:
    """The moon as seen from the northern half of the earth: lit from the right while it
    waxes, from the left while it wanes. Drawn larger than it will be shown, so the layout
    only ever shrinks it."""
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    r = size / 2 - 1
    c = size / 2
    draw.ellipse((c - r, c - r, c + r, c + r), fill=DARK)
    # The line between day and night is half an ellipse, as wide as the disc times
    # cos(phase). Each row of the disc is lit from ``start`` to ``end`` (as a share of the
    # row's half width, -1 left edge to 1 right edge).
    k = math.cos(math.radians(phase))
    start, end = (k, 1.0) if phase <= 180 else (-1.0, -k)
    steps = 180
    rows = [r * math.sin(math.pi * (i / steps - 0.5)) for i in range(steps + 1)]
    left = [(c + start * math.sqrt(max(r * r - y * y, 0)), c + y) for y in rows]
    right = [(c + end * math.sqrt(max(r * r - y * y, 0)), c + y) for y in reversed(rows)]
    if end - start > 1e-3:
        draw.polygon(left + right, fill=LIT)
    return image


def time_text(label: str, t: datetime | None, zone) -> str:
    """ "Moonrise: 01:38", or "Moonrise: none" on a day without one."""
    if t is None:
        return f"{label}: none"
    return f"{label}: {t.astimezone(zone):%H:%M}"


def draw(moon: Moon, context: Context) -> dict:
    zone = ZoneInfo(moon.zone) if moon.zone else None
    values = {
        "moonrise": time_text("Moonrise", moon.rise, zone),
        "moonset": time_text("Moonset", moon.set, zone),
        "phase": phase_name(moon.phase),
        "moon": moon_picture(moon.phase),
        "credit": CREDIT,
    }
    wanted = PLUGIN.layout(context.layout, context.settings).blocks
    return {name: value for name, value in values.items() if name in wanted}


#: met.no's real answer for Berlin on 6 October 2026: a waning crescent.
SAMPLE = Moon(
    day="2026-10-06",
    place="52.5200,13.4000",
    phase=301.33,
    rise=datetime.fromisoformat("2026-10-06T01:38+02:00"),
    set=datetime.fromisoformat("2026-10-06T17:04+02:00"),
    zone="Europe/Berlin",
)

PLUGIN = Plugin(
    type="moon_phase",
    description="Today's moon: its phase, and the times it rises and sets, from met.no.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=SAMPLE,
    refresh=20 * 60,
)
