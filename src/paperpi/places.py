"""Find places by name, for plugins that need a latitude and longitude (such as the weather).

The search is Open-Meteo's place search (chosen with txoof on 2026-10-10, see
``docs/specs/plugins.md``): no key, and it gives each place's altitude too. Its
place data comes from GeoNames; both ask for credit (CC BY 4.0), which
:func:`location_helper` shows under the choices.

:func:`location_helper` is a ready-made setting helper: the plugin names its settings for
latitude, longitude and, if it has them, altitude and the name shown on the screen.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from urllib.parse import urlencode

from . import limits, webrequest
from .helper import Helper, HelperProblem, Query

log = logging.getLogger(__name__)

URL = "https://geocoding-api.open-meteo.com/v1/search"
SOURCE = "Search by Open-Meteo, place data from GeoNames"
SOURCE_LINK = "https://open-meteo.com/en/docs/geocoding-api"


@dataclass(frozen=True)
class Place:
    id: int
    """Open-Meteo's number for the place (the same in every language)."""
    name: str
    region: str
    """The state or province, e.g. Colorado (may be empty)."""
    country: str
    lat: float
    lon: float
    altitude: int | None
    """Metres above sea level (``None``: not known)."""


def find_places(text: str, language: str = "en", count: int = 10) -> list[Place]:
    """The places whose name matches ``text`` (e.g. "Morrison, Colorado"), best first, with
    their names in ``language`` (or in English, for places found only in English).

    Open-Meteo finds a name only in the language it is asked in ("Den Haag" in Dutch, "The
    Hague" in English), so a ``language`` other than English is searched too, first; a
    place found in both is listed once. When one of the two searches fails, the other one's
    places are listed. Raises :class:`~paperpi.webrequest.WebError` when every search
    failed (Open-Meteo can't be reached)."""
    places: dict[int, Place] = {}
    failed: list[webrequest.WebError] = []
    languages = list(dict.fromkeys([language, "en"]))
    for spoken in languages:
        try:
            found = _search(text, spoken, count)
        except webrequest.WebError as error:
            failed.append(error)
            continue
        for place in found:
            places.setdefault(place.id, place)
    if len(failed) == len(languages):
        raise failed[-1]
    return list(places.values())[:count]


def _search(text: str, language: str, count: int) -> list[Place]:
    query = urlencode({"name": text, "count": count, "language": language, "format": "json"})
    found = webrequest.get(
        f"{URL}?{query}", total=limits.PLACE_REQUEST, connect_timeout=limits.PLACE_CONNECT
    ).json()
    results = found.get("results") if isinstance(found, dict) else None
    places = []
    for item in results if isinstance(results, list) else []:
        try:
            places.append(_place(item))
        except (KeyError, TypeError, ValueError) as error:
            log.info("left out a place Open-Meteo sent that can't be read: %r (%s)", item, error)
    return places


def _place(item: dict) -> Place:
    """One place of Open-Meteo's answer. Raises KeyError, TypeError or ValueError when it
    can't be used, so one odd place doesn't stop the others from being listed."""
    lat, lon = _number(item["latitude"]), _number(item["longitude"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("latitude or longitude out of range")
    try:
        altitude = round(_number(item.get("elevation")))
    except (TypeError, ValueError):
        altitude = None
    return Place(
        id=int(item["id"]),
        name=str(item.get("name") or ""),
        region=str(item.get("admin1") or ""),
        country=str(item.get("country") or ""),
        lat=round(lat, 4),
        lon=round(lon, 4),
        altitude=altitude,
    )


def _number(value: object) -> float:
    """A finite number from the answer (not true or false, which Python counts as numbers)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"not a number: {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"not a finite number: {value!r}")
    return float(value)


def location_helper(
    lat: str = "lat", lon: str = "lon", altitude: str | None = None, name: str | None = None
) -> Helper:
    """A setting helper that fills in latitude and longitude from a place name. ``lat`` and
    ``lon`` name the plugin's settings for them; ``altitude`` (metres; emptied when the place's
    altitude isn't known) and ``name`` (shown on the screen; always replaced, as choosing the
    place is the point) are optional."""

    def find(query: Query):
        try:
            places = find_places(query.text, query.language)
        except webrequest.WebError as error:
            raise HelperProblem(f"Open-Meteo could not be reached: {error}") from None
        choices = []
        for place in places:
            fill = {lat: place.lat, lon: place.lon}
            if altitude:
                # Empty when not known, so the altitude of an earlier choice is cleared.
                fill[altitude] = "" if place.altitude is None else place.altitude
            if name:
                fill[name] = place.name
            show = {"Place": place.name, "Region": place.region, "Country": place.country}
            show = {k: v for k, v in show.items() if v}
            if place.altitude is not None:
                show["Altitude"] = f"{place.altitude} m"
            show["Lat, lon"] = f"{place.lat}, {place.lon}"
            map_link = (
                "https://www.openstreetmap.org/"
                f"?mlat={place.lat}&mlon={place.lon}#map=12/{place.lat}/{place.lon}"
            )
            choices.append({"fill": fill, "show": show, "link": {"See on map": map_link}})
        return choices

    return Helper(
        find,
        prompt="Find the place by name, e.g. Addis Ababa or Morrison, Colorado",
        source=SOURCE,
        source_link=SOURCE_LINK,
    )
