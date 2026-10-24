"""Finding stops and stations by name, for the search boxes on the settings page (setting
helpers, see ``docs/decisions/setting-helpers.md``).

People type a name, with typos if need be ("Rotterdam Centraal", "utrcht cs"), and pick from
a list; nobody needs to know a code.

- **Stops:** OVapi's list of stop areas (``/stopareacode``, about 4,500 areas with town and
  name) is matched against the text. The best areas are then asked for their stops
  (``/stopareacode/<code>,<code>``): each stop is one side of the street, so each is its own
  choice, shown with the lines and destinations that leave from it.
- **Stations:** the NS station list (``/v2/stations``, needs the NS key) is matched against
  the text, with each station's long, middle and short names and its other names.

Both lists are downloaded for each search: a search happens once, when the plugin is set up.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from ... import webrequest
from ...helper import Helper, HelperProblem, Query
from . import ns

# Only http: OVapi's https certificate is not valid (see OVAPI in __init__).
OVAPI = "http://v0.ovapi.nl"
#: Longest one request of a search may take, with its retry: a search makes two requests,
#: which must fit in the helper's 30 seconds (``limits.HELPER_SEARCH``).
REQUEST = 12.0
CONNECT = 5.0
#: Most choices shown (the settings page shows at most 10).
MOST = 10
#: Stop areas asked for their stops in one search.
AREAS = 4
#: Matches scoring lower than this are left out (1.0: every typed word found).
LOWEST = 0.6
#: Matches scoring this much lower than the best one are left out too, so "Rotterdam
#: Centraal" doesn't list every stop in Rotterdam.
BEHIND = 0.2
#: OVapi gives some stops a made-up position far outside the Netherlands; no map link then.
NETHERLANDS = ((50.6, 53.7), (3.2, 7.3))
STOP_SOURCE = "Search by OVapi, the stops of all Dutch buses and trams"
STOP_SOURCE_LINK = "https://github.com/koch-t/KV78Turbo-OVAPI/wiki"
STATION_SOURCE = "Search by the NS API (uses your NS API key)"
STATION_SOURCE_LINK = "https://apiportal.ns.nl"
#: NS country codes of the stations outside the Netherlands, as shown with a choice.
COUNTRIES = {
    "D": "Germany",
    "B": "Belgium",
    "A": "Austria",
    "F": "France",
    "CH": "Switzerland",
    "PL": "Poland",
    "I": "Italy",
    "DK": "Denmark",
    "CZ": "Czechia",
    "GB": "United Kingdom",
    "H": "Hungary",
    "L": "Luxembourg",
}


def plain(text: str) -> str:
    """``text`` in lowercase without accents and punctuation, for comparing names."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def score(typed: str, name: str) -> float:
    """How well ``name`` matches what was typed, from 0 to about 1. Each typed word is
    compared with the name's words (a word the name starts with counts fully, so "cs" and
    "rotter" work), and the whole text with the whole name (so "niueweduinweg" finds
    "Nieuwe Duinweg"). Longer names score a little lower, so "Utrecht Centraal" wins over
    "Utrecht Centraal Jaarbeurszijde" when both match."""
    words, target = plain(typed).split(), plain(name).split()
    if not words or not target:
        return 0.0
    per_word = sum(_word(word, target) for word in words) / len(words)
    whole = SequenceMatcher(None, "".join(words), "".join(target)).ratio()
    return max(per_word, whole) - 0.001 * len(target)


def _word(word: str, target: list[str]) -> float:
    best = 0.0
    for other in target:
        if other.startswith(word):
            return 1.0
        matcher = SequenceMatcher(None, word, other)
        if matcher.real_quick_ratio() > best and matcher.quick_ratio() > best:
            best = max(best, matcher.ratio())
    return best


def best[T](typed: str, items: Iterable[T], names: Callable[[T], Iterable[str]], most: int):
    """The ``most`` items whose names best match ``typed``, best first, each scoring at least
    :data:`LOWEST` and at most :data:`BEHIND` below the best."""
    scored = []
    for item in items:
        top = max((score(typed, name) for name in names(item)), default=0.0)
        if top >= LOWEST:
            scored.append((top, item))
    scored.sort(key=lambda pair: -pair[0])  # stable: equal scores keep the list's order
    return [item for top, item in scored[:most] if top >= scored[0][0] - BEHIND]


def _get(url: str, **options) -> object:
    return webrequest.get(url, total=REQUEST, connect_timeout=CONNECT, **options).json()


def _map(lat: object, lon: object) -> dict[str, str]:
    (south, north), (west, east) = NETHERLANDS
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in (lat, lon)):
        return {}
    if not (south <= lat <= north and west <= lon <= east):
        return {}
    lat, lon = round(lat, 5), round(lon, 5)
    return {
        "See on map": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
    }


@dataclass(frozen=True)
class FoundStop:
    code: str
    name: str
    town: str
    lines: tuple[tuple[str, str], ...]
    """Line and destination of the vehicles leaving soon, sorted."""
    lat: object = None
    lon: object = None


def find_stops(text: str) -> tuple[list[FoundStop], bool]:
    """The stops whose area best matches ``text``, and whether more were found than
    :data:`MOST`. Raises ``webrequest.WebError`` when OVapi can't be reached, and
    :class:`HelperProblem` when its answer can't be read."""
    areas = _get(f"{OVAPI}/stopareacode")
    if not isinstance(areas, dict):
        raise HelperProblem("OVapi's list of stops can't be read")

    def names(item):
        area = item[1] if isinstance(item[1], dict) else {}
        name, town = str(area.get("TimingPointName", "")), str(area.get("TimingPointTown", ""))
        return (name, f"{town} {name}")

    chosen = [code for code, _ in best(text, areas.items(), names, AREAS)]
    if not chosen:
        return [], False
    answer = _get(f"{OVAPI}/stopareacode/{','.join(chosen)}")
    if not isinstance(answer, dict):
        raise HelperProblem("OVapi's answer about the stops can't be read")
    found = []
    for code in chosen:  # best area first
        platforms = answer.get(code)
        for stop in platforms.values() if isinstance(platforms, dict) else ():
            if isinstance(stop, dict) and (read := _stop(stop)):
                found.append(read)
    return found[:MOST], len(found) > MOST


def _stop(item: dict) -> FoundStop | None:
    stop, passes = item.get("Stop"), item.get("Passes")
    if not isinstance(stop, dict) or not stop.get("TimingPointCode"):
        return None
    lines = set()
    for vehicle in passes.values() if isinstance(passes, dict) else ():
        if isinstance(vehicle, dict) and vehicle.get("LinePublicNumber"):
            lines.add((str(vehicle["LinePublicNumber"]), str(vehicle.get("DestinationName50", ""))))
    return FoundStop(
        str(stop["TimingPointCode"]),
        str(stop.get("TimingPointName", "")),
        str(stop.get("TimingPointTown", "")),
        tuple(sorted(lines, key=lambda pair: (_line_order(pair[0]), pair[1]))),
        stop.get("Latitude"),
        stop.get("Longitude"),
    )


def _line_order(line: str) -> tuple[int, str]:
    digits = re.match(r"\d+", line)
    return (int(digits.group()) if digits else 10**6, line)


def describe_lines(lines: tuple[tuple[str, str], ...]) -> str:
    """ "14 → Heemraadsplein, Rotterdam Centraal; 18 → Spangen" """
    if not lines:
        return "No departures in the next hour or so"
    grouped: dict[str, list[str]] = {}
    for line, destination in lines:
        grouped.setdefault(line, []).append(destination)
    return "; ".join(f"{line} → {', '.join(d for d in to if d)}" for line, to in grouped.items())


def stop_helper(n: int) -> Helper:
    """The search for stop ``n``: fills in its code, and empties its heading and lines, which
    belonged to the stop chosen before (an empty heading shows the stop's own name)."""

    def find(query: Query):
        try:
            stops, more = find_stops(query.text)
        except webrequest.WebError as error:
            raise HelperProblem(f"OVapi could not be reached: {error}") from None
        choices = []
        for stop in stops:
            show = {"Stop": stop.name or stop.code, "Town": stop.town}
            show["Lines"] = describe_lines(stop.lines)
            show["Code"] = stop.code
            choices.append(
                {
                    "fill": {f"stop_{n}": stop.code, f"name_{n}": "", f"lines_{n}": ""},
                    "show": {k: v for k, v in show.items() if v},
                    "link": _map(stop.lat, stop.lon),
                }
            )
        note = (
            "Only the first 10 stops are shown; add the town or more of the name to narrow it down"
            if more
            else "Each stop is one side of the street: pick the one whose lines go your way"
        )
        return {"choices": choices, "note": note} if choices else []

    return Helper(
        find,
        prompt=f"Find stop {n} by name, e.g. Rotterdam Centraal or Amsterdam Dam",
        source=STOP_SOURCE,
        source_link=STOP_SOURCE_LINK,
    )


@dataclass(frozen=True)
class Station:
    code: str
    name: str
    country: str
    other: tuple[str, ...]
    """Other names: the middle and short names and NS's synonyms."""
    lat: object = None
    lon: object = None


def find_stations(text: str, key: str) -> list[Station]:
    """The NS stations whose names best match ``text``. Raises :class:`HelperProblem` when
    NS doesn't accept the key or can't be reached."""
    try:
        answer = _get(f"{ns.BASE}/v2/stations", headers=ns.headers(key))
    except webrequest.WebError as error:
        # webrequest's messages name the answer, e.g. "... answered 401 Unauthorized".
        if " 401 " in str(error) or " 403 " in str(error):
            raise HelperProblem("The NS API key was not accepted; check it") from None
        raise HelperProblem(f"NS could not be reached: {error}") from None
    payload = answer.get("payload") if isinstance(answer, dict) else None
    if not isinstance(payload, list):
        raise HelperProblem("NS's list of stations can't be read")
    stations = [s for item in payload if isinstance(item, dict) and (s := _station(item))]
    return best(text, stations, lambda s: (s.name, *s.other), MOST)


def _station(item: dict) -> Station | None:
    names = item.get("namen") if isinstance(item.get("namen"), dict) else {}
    code, name = item.get("code"), names.get("lang")
    if not (isinstance(code, str) and code and isinstance(name, str) and name):
        return None
    other = [names.get("middel"), names.get("kort")]
    if isinstance(item.get("synoniemen"), list):
        other += item["synoniemen"]
    other = tuple(dict.fromkeys(str(o) for o in other if o and o != name))
    return Station(code, name, str(item.get("land", "")), other, item.get("lat"), item.get("lng"))


def station_helper(n: int, end: str) -> Helper:
    """The search for the station train route ``n`` goes ``end`` ("from" or "to")."""
    key = f"train_{end}_{n}"

    def find(query: Query):
        stations = find_stations(query.text, query.settings.ns_key.get_secret_value())
        choices = []
        for station in stations:
            show = {"Station": station.name, "Code": station.code}
            if station.country and station.country != "NL":
                show["Country"] = COUNTRIES.get(station.country, station.country)
            if station.other:
                show["Also called"] = ", ".join(station.other)
            choices.append(
                {"fill": {key: station.code}, "show": show, "link": _map(station.lat, station.lon)}
            )
        return choices

    return Helper(
        find,
        prompt=f"Find the station train route {n} goes {end}, e.g. Rotterdam or Den Haag Centraal",
        source=STATION_SOURCE,
        source_link=STATION_SOURCE_LINK,
        needs=("ns_key",),
    )
