"""Bus and tram departures from OVapi (``v0.ovapi.nl``): reading its answers, choosing the
departures to show, and saving the last answer.

OVapi answers ``/tpc/<code>,<code>`` with one entry per stop ("timing point": one side of
the street, so one direction), each with its ``Passes``: the vehicles that stop there in the
next 80 minutes or so, and the ones that left a few minutes ago. Times are local Dutch time
without a time zone.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Amsterdam")
#: Departures that left up to this long ago are still shown (as "left").
SHOWN_AFTER = timedelta(minutes=5)
#: TripStopStatus values for a vehicle that has left this stop.
LEFT = ("PASSED",)
CANCELLED = ("CANCEL",)


class AnswerError(ValueError):
    """OVapi's answer is not what the plugin expects."""


@dataclass(frozen=True)
class Departure:
    line: str
    destination: str
    planned: datetime
    expected: datetime
    left: bool = False
    cancelled: bool = False

    @property
    def delay(self) -> int:
        """Whole minutes late (negative: early)."""
        return round((self.expected - self.planned).total_seconds() / 60)


@dataclass(frozen=True)
class Stop:
    """One stop in OVapi's answer: its name and its departures, sorted by expected time."""

    code: str
    name: str
    departures: tuple[Departure, ...]


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ZONE)


def read(answer: object) -> dict[str, Stop]:
    """The stops in an OVapi ``/tpc/`` answer, by code. A stop OVapi doesn't know is
    missing from the answer."""
    if not isinstance(answer, dict):
        raise AnswerError("OVapi's answer is not a list of stops")
    stops = {}
    try:
        for code, entry in answer.items():
            passes = entry.get("Passes") or {}
            found = []
            for item in passes.values():
                status = item.get("TripStopStatus", "")
                found.append(
                    Departure(
                        line=str(item["LinePublicNumber"]),
                        destination=item.get("DestinationName50") or "",
                        planned=_time(item["TargetDepartureTime"]),
                        expected=_time(
                            item.get("ExpectedDepartureTime") or item["TargetDepartureTime"]
                        ),
                        left=status in LEFT,
                        cancelled=status in CANCELLED,
                    )
                )
            name = (entry.get("Stop") or {}).get("TimingPointName") or code
            found.sort(key=lambda d: (d.expected, d.line))
            stops[code] = Stop(code, name, tuple(found))
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise AnswerError(f"OVapi's answer can't be read: {error!r}") from None
    return stops


def shown(stop: Stop, lines: tuple[str, ...], now: datetime, ahead: int) -> list[Departure]:
    """The departures of ``stop`` to show: only ``lines`` (all when empty), from
    :data:`SHOWN_AFTER` ago to ``ahead`` minutes from now."""
    wanted = {line.casefold() for line in lines}
    first, last = now - SHOWN_AFTER, now + timedelta(minutes=ahead)
    return [
        d
        for d in stop.departures
        if (not wanted or d.line.casefold() in wanted) and first <= d.expected <= last
    ]


def save(stops: dict[str, Stop], fetched: datetime) -> bytes:
    """The stops and when they were fetched, as the file :func:`load` reads."""
    data = {"fetched": fetched.isoformat(), "stops": [asdict(s) for s in stops.values()]}
    return json.dumps(data, default=str).encode()


def load(path: Path) -> tuple[dict[str, Stop], datetime] | None:
    """Stops saved by :func:`save`, and when they were fetched; ``None`` when there are
    none or the file can't be read."""
    try:
        data = json.loads(path.read_bytes())
        stops = {}
        for s in data["stops"]:
            departures = tuple(
                Departure(
                    d["line"],
                    d["destination"],
                    datetime.fromisoformat(d["planned"]),
                    datetime.fromisoformat(d["expected"]),
                    d["left"],
                    d["cancelled"],
                )
                for d in s["departures"]
            )
            stops[s["code"]] = Stop(s["code"], s["name"], departures)
        return stops, datetime.fromisoformat(data["fetched"])
    except (OSError, KeyError, TypeError, ValueError):
        return None
