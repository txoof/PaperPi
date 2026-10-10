"""The place search (paperpi.places) and its ready-made location helper, with a fake Open-Meteo."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from paperpi import limits, places, webrequest
from paperpi.helper import HelperProblem, Query, clean
from paperpi.plugin import PluginSettings

ADDIS = {
    "id": 344979,
    "name": "Addis Ababa",
    "latitude": 9.02497,
    "longitude": 38.74689,
    "elevation": 2404.6,
    "country": "Ethiopia",
    "admin1": "Addis Ababa",
}
THE_HAGUE = {
    "id": 2747373,
    "name": "The Hague",
    "latitude": 52.07667,
    "longitude": 4.29861,
    "elevation": 1.0,
    "country": "Netherlands",
    "admin1": "South Holland",
}


class FakeOpenMeteo:
    """Stands in for webrequest.get: answers per language, and records the calls."""

    def __init__(self, monkeypatch, **answers):
        self.answers = answers  # language -> list of results, or an error to raise
        self.calls = []
        monkeypatch.setattr(places.webrequest, "get", self)

    def __call__(self, url, **options):
        query = {key: value[0] for key, value in parse_qs(urlsplit(url).query).items()}
        self.calls.append((query, options))
        found = self.answers.get(query["language"], [])
        if isinstance(found, Exception):
            raise found
        # Open-Meteo leaves "results" out when it finds nothing.
        body = {"results": found} if found else {"generationtime_ms": 0.5}
        return webrequest.Answer(200, json.dumps(body).encode(), {}, url)


def test_a_place_is_read_from_the_answer(monkeypatch):
    fake = FakeOpenMeteo(monkeypatch, en=[ADDIS])
    assert places.find_places("Addis Ababa") == [
        places.Place(344979, "Addis Ababa", "Addis Ababa", "Ethiopia", 9.025, 38.7469, 2405)
    ]
    query, options = fake.calls[0]
    assert query == {"name": "Addis Ababa", "count": "10", "language": "en", "format": "json"}
    # Two requests must fit in one helper search.
    assert options == {"total": limits.PLACE_REQUEST, "connect_timeout": limits.PLACE_CONNECT}
    assert 2 * limits.PLACE_REQUEST < limits.HELPER_SEARCH


def test_missing_region_and_altitude(monkeypatch):
    bare = {key: ADDIS[key] for key in ("id", "name", "latitude", "longitude", "country")}
    FakeOpenMeteo(monkeypatch, en=[bare])
    (place,) = places.find_places("Addis Ababa")
    assert (place.region, place.altitude) == ("", None)


@pytest.mark.parametrize(
    "odd",
    [
        {"id": None},
        {"latitude": None},
        {"longitude": "38.7"},
        {"latitude": float("inf")},
        {"latitude": 91.0},
        {"longitude": True},
        "Addis Ababa",
    ],
)
def test_a_place_that_cant_be_read_is_left_out(monkeypatch, odd):
    item = ADDIS | odd if isinstance(odd, dict) else odd
    FakeOpenMeteo(monkeypatch, en=[item, THE_HAGUE])
    assert [p.name for p in places.find_places("A")] == ["The Hague"]


@pytest.mark.parametrize("elevation", [None, float("nan"), float("inf"), "high", False])
def test_an_odd_altitude_is_not_known(monkeypatch, elevation):
    FakeOpenMeteo(monkeypatch, en=[ADDIS | {"elevation": elevation, "admin1": None}])
    (place,) = places.find_places("Addis Ababa")
    assert (place.altitude, place.region) == (None, "")


@pytest.mark.parametrize("body", [b"[]", b'{"results": {"id": 1}}', b'{"results": null}'])
def test_an_odd_answer_finds_nothing(monkeypatch, body):
    monkeypatch.setattr(
        places.webrequest, "get", lambda url, **options: webrequest.Answer(200, body, {}, url)
    )
    assert places.find_places("Addis Ababa") == []


def test_nothing_found(monkeypatch):
    FakeOpenMeteo(monkeypatch)
    assert places.find_places("Nowhere at all") == []


def test_the_browsers_language_first_then_english_each_place_once(monkeypatch):
    den_haag = THE_HAGUE | {"name": "Den Haag", "admin1": "Zuid-Holland"}
    fake = FakeOpenMeteo(monkeypatch, nl=[den_haag], en=[THE_HAGUE, ADDIS])
    found = places.find_places("Den Haag", "nl")
    assert [p.name for p in found] == ["Den Haag", "Addis Ababa"]  # the Dutch name is kept
    assert [query["language"] for query, _ in fake.calls] == ["nl", "en"]


def test_english_is_searched_once_and_the_list_is_cut(monkeypatch):
    many = [ADDIS | {"id": n} for n in range(10)]
    fake = FakeOpenMeteo(monkeypatch, de=many, en=[ADDIS | {"id": 99}])
    # The English-only place (99) is the one left out.
    assert [p.id for p in places.find_places("Addis", "de")] == list(range(10))
    places.find_places("Addis", "en")
    assert [query["language"] for query, _ in fake.calls] == ["de", "en", "en"]


# --- The ready-made location helper ----------------------------------------------------------


def search(helper, text="Addis Ababa", language="en"):
    return helper.find(Query(text, PluginSettings(), language))


def test_the_helper_fills_lat_and_lon_and_shows_the_place(monkeypatch):
    FakeOpenMeteo(monkeypatch, en=[ADDIS])
    (choice,) = search(places.location_helper())
    assert choice == {
        "fill": {"lat": 9.025, "lon": 38.7469},
        "show": {
            "Place": "Addis Ababa",
            "Region": "Addis Ababa",
            "Country": "Ethiopia",
            "Altitude": "2405 m",
            "Lat, lon": "9.025, 38.7469",
        },
        "link": {
            "See on map": "https://www.openstreetmap.org/?mlat=9.025&mlon=38.7469"
            "#map=12/9.025/38.7469"
        },
    }
    # It keeps PaperPi's rules for results.
    assert clean([choice], ["lat", "lon"]).choices[0].heading == "Addis Ababa"


def test_the_helper_fills_the_plugins_own_settings(monkeypatch):
    FakeOpenMeteo(monkeypatch, en=[ADDIS])
    helper = places.location_helper("latitude", "longitude", altitude="height", name="place")
    (choice,) = search(helper)
    assert choice["fill"] == {
        "latitude": 9.025,
        "longitude": 38.7469,
        "height": 2405,
        "place": "Addis Ababa",
    }
    assert isinstance(choice["fill"]["height"], int)  # rounded: 2404.6 m
    assert helper.source == places.SOURCE and helper.source_link == places.SOURCE_LINK


def test_an_unknown_altitude_empties_the_field(monkeypatch):
    # Else the altitude of an earlier choice would stay, and be sent for the new place.
    FakeOpenMeteo(monkeypatch, en=[{k: v for k, v in ADDIS.items() if k != "elevation"}])
    (choice,) = search(places.location_helper(altitude="altitude"))
    assert choice["fill"]["altitude"] == "" and "Altitude" not in choice["show"]


def test_when_one_language_fails_the_other_ones_places_are_listed(monkeypatch):
    FakeOpenMeteo(monkeypatch, nl=webrequest.WebError("timed out"), en=[ADDIS])
    assert [p.name for p in places.find_places("Addis Ababa", "nl")] == ["Addis Ababa"]
    FakeOpenMeteo(monkeypatch, nl=[THE_HAGUE], en=webrequest.WebError("timed out"))
    assert [p.name for p in places.find_places("Den Haag", "nl")] == ["The Hague"]
    FakeOpenMeteo(monkeypatch, nl=webrequest.WebError("first"), en=webrequest.WebError("last"))
    with pytest.raises(webrequest.WebError, match="last"):
        places.find_places("Den Haag", "nl")


def test_the_helper_says_when_open_meteo_fails(monkeypatch):
    FakeOpenMeteo(monkeypatch, en=webrequest.WebError("could not connect"))
    with pytest.raises(HelperProblem, match="Open-Meteo could not be reached: could not connect"):
        search(places.location_helper())
