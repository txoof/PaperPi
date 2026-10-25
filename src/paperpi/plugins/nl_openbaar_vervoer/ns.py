"""NS trains from the NS API (``gateway.apiportal.ns.nl``): the trips between two stations
and the disruptions on the way.

The journey planner (``/v3/trips``) is used instead of the departure board: trains are
signed with their last station (Groningen, Enschede), so the board can't tell which trains
stop at the destination. Each trip is turned into a :class:`~.departures.Departure`, so
trains are drawn like trams.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode

from .departures import ZONE, AnswerError, Departure, Saved, Stop

BASE = "https://gateway.apiportal.ns.nl/reisinformatie-api/api"
#: Disruptions change slowly; asking less often keeps within the key's 5,000 requests a day.
DISRUPTIONS_EVERY = timedelta(minutes=10)
#: Train times are asked for at most this often, whatever the refresh: two routes of two
#: requests each then stay under about 3,500 requests a day.
TRIPS_EVERY = timedelta(seconds=110)
#: Disruption types that are not planned works; only these can make the plugin an alert.
REAL = ("DISRUPTION", "CALAMITY")


@dataclass(frozen=True)
class Notice:
    """A disruption or planned works on a route."""

    title: str
    kind: str  # DISRUPTION, CALAMITY or MAINTENANCE

    @property
    def real(self) -> bool:
        return self.kind in REAL


def headers(key: str) -> dict[str, str]:
    """The headers that send the NS key (only to NS: see ``webrequest.get``)."""
    return {"Ocp-Apim-Subscription-Key": key}


def trips_url(origin: str, destination: str, start: datetime) -> str:
    when = start.astimezone(ZONE).replace(second=0, microsecond=0).isoformat()
    query = {"fromStation": origin, "toStation": destination, "dateTime": when}
    return f"{BASE}/v3/trips?{urlencode(query)}"


def disruptions_url(station: str) -> str:
    return f"{BASE}/v3/disruptions/station/{quote(station)}"


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def read_trips(
    answer: object, origin: str, destination: str, changes: bool
) -> tuple[Stop, datetime | None]:
    """The trips in a ``/v3/trips`` answer as a :class:`Stop` whose code is
    ``<origin>-<destination>`` and whose name is the route ("Den Haag Centraal → Utrecht
    Centraal"), and the planned time of the last trip in the answer (``None``: no trips).
    Trips with a change of train are left out unless ``changes``."""
    try:
        trips = answer["trips"]
        found = []
        name = f"{origin} → {destination}"
        last = None
        for trip in trips:
            legs = trip["legs"]
            start, end = legs[0]["origin"], legs[-1]["destination"]
            if trip is trips[0]:
                name = f"{start['name']} → {end['name']}"
            planned = _time(start["plannedDateTime"])
            last = max(last or planned, planned)
            transfers = int(trip.get("transfers", 0))
            if transfers and not changes:
                continue
            expected = _time(start.get("actualDateTime") or start["plannedDateTime"])
            track = start.get("actualTrack") or start.get("plannedTrack") or "?"
            # The station the train is signed with (Groningen), as on the platform.
            where = legs[0].get("direction") or legs[0]["destination"]["name"]
            if start.get("plannedTrack") and track != start["plannedTrack"]:
                where += f" · was {start['plannedTrack']}"
            elif transfers:
                where += f" · {transfers} change" + ("s" if transfers > 1 else "")
            cancelled = trip.get("status") == "CANCELLED" or any(
                leg.get("cancelled") for leg in legs
            )
            category = legs[0].get("product", {}).get("shortCategoryName") or "?"
            found.append(
                Departure(category, where, planned, expected, cancelled=cancelled, track=track)
            )
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
        raise AnswerError(f"the NS answer can't be read: {error!r}") from None
    found.sort(key=lambda d: d.expected)
    return Stop(f"{origin}-{destination}", name, tuple(found)), last


def read_disruptions(answer: object, origin: str, destination: str) -> tuple[Notice, ...]:
    """The active disruptions in a ``/v3/disruptions/station/`` answer that name both
    stations of the route. (A disruption is listed for every station on its line, often
    far away from the route.)"""
    if not isinstance(answer, list):
        raise AnswerError("the NS disruptions answer is not a list")
    found = []
    try:
        for item in answer:
            if not item.get("isActive", True):
                continue
            stations = {
                station.get("stationCode")
                for part in item.get("publicationSections", [])
                for station in part.get("section", {}).get("stations", [])
            }
            if {origin, destination} <= stations:
                found.append(Notice(item.get("title", "").rstrip(". "), item.get("type", "")))
    except (AttributeError, TypeError) as error:
        raise AnswerError(f"the NS disruptions answer can't be read: {error!r}") from None
    return tuple(found)


def route_saved(stop: Stop, fetched: datetime) -> Saved:
    return Saved({stop.code: stop}, frozenset({stop.code}), fetched)


def save_notices(notices: tuple[Notice, ...], fetched: datetime) -> bytes:
    data = {"fetched": fetched.isoformat(), "notices": [asdict(n) for n in notices]}
    return json.dumps(data).encode()


def load_notices(path: Path) -> tuple[tuple[Notice, ...], datetime] | None:
    try:
        data = json.loads(path.read_bytes())
        notices = tuple(Notice(n["title"], n["kind"]) for n in data["notices"])
        return notices, datetime.fromisoformat(data["fetched"])
    except (OSError, KeyError, TypeError, ValueError):
        return None
