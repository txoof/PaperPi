"""The stop and station search of nl_openbaar_vervoer (search boxes on the settings page),
with a fake OVapi and NS."""

import json

import pytest

from paperpi import webrequest
from paperpi.helper import HelperProblem, Query, clean
from paperpi.plugins.nl_openbaar_vervoer import PLUGIN, Settings, search

AREAS = {
    "4862": {"TimingPointTown": "Rotterdam", "TimingPointName": "Rotterdam Centraal perron B"},
    "4867": {
        "TimingPointTown": "Rotterdam",
        "TimingPointName": "Rotterdam Centraal Blijdorpzijde",
    },
    "05055": {"TimingPointTown": "Amsterdam", "TimingPointName": "Amsterdam, Dam"},
    "rtblk": {"TimingPointTown": "Rotterdam", "TimingPointName": "Blaak"},
}


def vehicle(line, destination):
    return {"LinePublicNumber": line, "DestinationName50": destination}


def stop(code, name, *vehicles, lat=51.9234, lon=4.4707):
    passes = {str(i): v for i, v in enumerate(vehicles)}
    info = {"TimingPointCode": code, "TimingPointName": name, "TimingPointTown": "Rotterdam"}
    return {"Stop": info | {"Latitude": lat, "Longitude": lon}, "Passes": passes}


PLATFORMS = {
    "4862": {
        "31001118": stop(
            "31001118",
            "Rotterdam Centraal perron A",
            vehicle("18", "Spangen"),
            vehicle("14", "Heemraadsplein"),
            vehicle("14", "Heemraadsplein"),
            vehicle("14", "Rotterdam Centraal"),
        ),
        "31001039": stop("31001039", "Rotterdam Centraal perron B", vehicle("5", "Carnisselande")),
    },
    "4867": {
        # A made-up position (OVapi has some): no map link.
        "31001228": stop("31001228", "Rotterdam Centraal Blijdorpzijde", lat=47.97, lon=3.31),
    },
}

STATIONS = {
    "payload": [
        {
            "code": "RTD",
            "land": "NL",
            "lat": 51.925,
            "lng": 4.46889,
            "namen": {
                "lang": "Rotterdam Centraal",
                "middel": "Rotterdam C.",
                "kort": "Rotterdam C",
            },
            "synoniemen": ["Rotterdam CS"],
        },
        {
            "code": "GVC",
            "land": "NL",
            "namen": {"lang": "Den Haag Centraal", "middel": "Den Haag C.", "kort": "Den Haag C"},
            "synoniemen": ["Den Haag CS", "'s-Gravenhage"],
        },
        {
            "code": "LEDN",
            "land": "NL",
            "namen": {"lang": "Leiden Centraal", "middel": "Leiden C.", "kort": "Leiden C"},
        },
        {"code": "ABG", "land": "D", "namen": {"lang": "Hamburg-Bergedorf"}},
        {"code": "", "namen": {"lang": "No code"}},
        "not a station",
    ]
}


class Fake:
    """Stands in for webrequest.get: answers by address, and records the calls."""

    def __init__(self, monkeypatch, **answers):
        self.answers = answers  # address part after the base -> answer or error
        self.calls = []
        monkeypatch.setattr(search.webrequest, "get", self)

    def __call__(self, url, **options):
        self.calls.append((url, options))
        if "/stopareacode/" in url and "areas" in self.answers:
            codes = url.rsplit("/", 1)[1].split(",")
            found = {c: self.answers["areas"][c] for c in codes if c in self.answers["areas"]}
            return webrequest.Answer(200, json.dumps(found).encode(), {}, url)
        for end, answer in self.answers.items():
            if url.endswith(end):
                if isinstance(answer, Exception):
                    raise answer
                return webrequest.Answer(200, json.dumps(answer).encode(), {}, url)
        raise webrequest.WebError(f"{url} answered 404 Not Found")


@pytest.fixture
def ovapi(monkeypatch):
    return Fake(monkeypatch, stopareacode=AREAS, areas=PLATFORMS)


def find(key, text, **settings):
    return PLUGIN.helper(key).find(Query(text, Settings(**settings)))


def test_each_stop_field_and_station_field_has_a_search():
    # A wrong helper name would already have stopped the import (Plugin checks itself).
    for n in range(1, 5):
        assert PLUGIN.helper(f"stop_{n}").prompt.startswith(f"Find stop {n} by name")
    for key in ("train_from_1", "train_to_1", "train_from_2", "train_to_2"):
        assert PLUGIN.helper(key).needs == ("ns_key",)
    assert PLUGIN.helper("name_1") is None


def test_stops_are_found_by_name_with_their_lines(ovapi):
    result = find("stop_2", "rotterdam centraal")
    found = clean(result, list(Settings.model_fields))
    assert [c.fill for c in found.choices] == [
        # The area with the shorter name first; each side of the street is its own choice.
        {"stop_2": "31001228", "name_2": "", "lines_2": ""},
        {"stop_2": "31001118", "name_2": "", "lines_2": ""},
        {"stop_2": "31001039", "name_2": "", "lines_2": ""},
    ]
    a = found.choices[1]
    assert dict(a.show) == {
        "Stop": "Rotterdam Centraal perron A",
        "Town": "Rotterdam",
        "Lines": "14 → Heemraadsplein, Rotterdam Centraal; 18 → Spangen",
        "Code": "31001118",
    }
    assert dict(a.links)["See on map"].startswith("https://www.openstreetmap.org/?mlat=51.9234")
    assert dict(found.choices[0].show)["Lines"] == "No departures in the next hour or so"
    assert found.choices[0].links == ()
    assert "one side of the street" in found.note
    # Two requests: the list, then only the best areas (Blaak and the Dam don't match).
    assert [url for url, _ in ovapi.calls] == [
        f"{search.OVAPI}/stopareacode",
        f"{search.OVAPI}/stopareacode/4867,4862",
    ]
    assert all(
        o == {"total": search.REQUEST, "connect_timeout": search.CONNECT} for _, o in ovapi.calls
    )
    # Both fit in one helper search.
    from paperpi import limits

    assert 2 * search.REQUEST < limits.HELPER_SEARCH


@pytest.mark.parametrize("typed", ["Roterdam Centrall", "rotterdam blijdorp", "ROTTERDAM C"])
def test_typos_and_short_words_still_find_the_stop(ovapi, typed):
    assert find("stop_1", typed)["choices"]


def test_nothing_found_asks_nothing_more(ovapi):
    assert find("stop_1", "Zzyzx") == []
    assert len(ovapi.calls) == 1


def test_more_than_ten_stops_says_so(monkeypatch):
    many = {"4862": {str(i): stop(str(i), f"Perron {i}") for i in range(12)}}
    Fake(monkeypatch, stopareacode={"4862": AREAS["4862"]}, areas=many)
    result = find("stop_1", "Rotterdam Centraal")
    assert len(result["choices"]) == search.MOST
    assert "Only the first 10" in result["note"]


def test_ovapi_out_of_reach_or_odd_says_so(monkeypatch):
    Fake(monkeypatch, stopareacode=webrequest.WebError("v0.ovapi.nl answered 503"))
    with pytest.raises(HelperProblem, match="OVapi could not be reached"):
        find("stop_1", "Rotterdam")
    Fake(monkeypatch, stopareacode=["not", "areas"])
    with pytest.raises(HelperProblem, match="can't be read"):
        find("stop_1", "Rotterdam")


def test_odd_stops_in_the_answer_are_left_out(monkeypatch):
    odd = {"4862": {"x": "not a stop", "y": {"Stop": {}}, "z": stop("31001039", "B")}}
    Fake(monkeypatch, stopareacode={"4862": AREAS["4862"]}, areas=odd)
    assert [c["fill"]["stop_1"] for c in find("stop_1", "Rotterdam Centraal")["choices"]] == [
        "31001039"
    ]


def test_stations_are_found_with_their_other_names(monkeypatch):
    fake = Fake(monkeypatch, stations=STATIONS)
    choices = find("train_to_2", "DH Centraal", ns_key="secret")
    found = clean(choices, list(Settings.model_fields))
    assert found.choices[0].fill == {"train_to_2": "GVC"}
    assert dict(found.choices[0].show) == {
        "Station": "Den Haag Centraal",
        "Code": "GVC",
        "Also called": "Den Haag C., Den Haag C, Den Haag CS, 's-Gravenhage",
    }
    assert found.choices[0].links == ()  # no position in the answer
    url, options = fake.calls[0]
    assert url == f"{search.ns.BASE}/v2/stations"
    assert options["headers"] == {"Ocp-Apim-Subscription-Key": "secret"}


def test_a_station_abroad_names_its_country(monkeypatch):
    Fake(monkeypatch, stations=STATIONS)
    choice = find("train_from_1", "Hamburg Bergedorf", ns_key="k")[0]
    assert choice["fill"] == {"train_from_1": "ABG"}
    assert choice["show"]["Country"] == "Germany"


def test_a_typo_finds_the_station(monkeypatch):
    Fake(monkeypatch, stations=STATIONS)
    assert find("train_from_1", "roterdm", ns_key="k")[0]["fill"] == {"train_from_1": "RTD"}


@pytest.mark.parametrize(
    "error, message",
    [
        ("gateway.apiportal.ns.nl answered 401 Unauthorized", "key was not accepted"),
        ("gateway.apiportal.ns.nl answered 403 Forbidden", "key was not accepted"),
        ("no connection to gateway.apiportal.ns.nl", "NS could not be reached"),
    ],
)
def test_ns_problems_say_what_to_do(monkeypatch, error, message):
    Fake(monkeypatch, stations=webrequest.WebError(error))
    with pytest.raises(HelperProblem, match=message):
        find("train_from_1", "Rotterdam", ns_key="k")


def test_an_odd_station_list_says_so(monkeypatch):
    Fake(monkeypatch, stations={"payload": "nothing"})
    with pytest.raises(HelperProblem, match="can't be read"):
        find("train_from_1", "Rotterdam", ns_key="k")


def test_much_weaker_matches_are_left_out():
    names = ["Rotterdam Centraal", "Rotterdam Blaak", "Den Haag Centraal"]
    assert search.best("rotterdam centraal", names, lambda n: [n], 10) == ["Rotterdam Centraal"]
    # Without a full match, close ones stay.
    assert search.best("roterdam", names, lambda n: [n], 10) == names[:2]


def test_names_are_compared_without_case_accents_or_punctuation():
    assert search.plain("  's-Gravenhage, Café  ") == "s gravenhage cafe"
    assert search.score("utrcht cs", "Utrecht CS") > 0.9
    assert search.score("", "Utrecht") == 0
    # A shorter name wins when both match fully.
    assert search.score("Utrecht", "Utrecht Centraal") > search.score(
        "Utrecht", "Utrecht Centraal Jaarbeurszijde"
    )
