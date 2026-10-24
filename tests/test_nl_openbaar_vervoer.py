"""The nl_openbaar_vervoer plugin: reading OVapi's answers, choosing departures, the saved
departures and drawing."""

from datetime import datetime, timedelta

import pytest
from epdlib import ScreenMode
from pydantic import ValidationError

import paperpi.plugins.nl_openbaar_vervoer as plugin_module
from paperpi import webrequest
from paperpi.plugin import NOTHING, Context, State
from paperpi.plugins.nl_openbaar_vervoer import (
    OLDEST,
    PLUGIN,
    SAVED,
    Board,
    Section,
    Settings,
    draw,
    fetch,
    lines_of,
    note,
    today_stops,
)
from paperpi.plugins.nl_openbaar_vervoer.departures import (
    ZONE,
    AnswerError,
    Departure,
    Stop,
    load,
    read,
    save,
    shown,
)

NOW = datetime(2026, 10, 24, 8, 10, tzinfo=ZONE)  # a Saturday


def passing(line, destination, planned, expected=None, status="PLANNED") -> dict:
    """One pass as OVapi sends it (the fields the plugin reads, copied from a real answer
    for Rotterdam Centraal, 24 October 2026)."""
    return {
        "LinePublicNumber": line,
        "DestinationName50": destination,
        "TransportType": "TRAM",
        "OperatorCode": "RET",
        "TargetDepartureTime": planned,
        "ExpectedDepartureTime": expected or planned,
        "TripStopStatus": status,
    }


def answer(**stops) -> dict:
    """An OVapi ``/tpc/`` answer: stop code -> (name, passes)."""
    return {
        code: {
            "Stop": {"TimingPointName": name, "TimingPointCode": code},
            "Passes": {str(i): p for i, p in enumerate(passes)},
            "GeneralMessages": {},
        }
        for code, (name, passes) in stops.items()
    }


PERRON_A = answer(
    s31001118=(
        "Rotterdam Centraal perron A",
        [
            passing("18", "Spangen", "2026-10-24T08:07:00", "2026-10-24T08:12:22", "DRIVING"),
            passing("14", "Heemraadsplein", "2026-10-24T08:02:00", "2026-10-24T08:02:50", "PASSED"),
            passing("14", "Heemraadsplein", "2026-10-24T08:22:00", "2026-10-24T08:23:38"),
            passing("18", "Spangen", "2026-10-24T09:37:00", status="CANCEL"),
        ],
    )
)["s31001118"]


def at(minutes, line="9", delay=0, **more) -> Departure:
    planned = NOW + timedelta(minutes=minutes)
    return Departure(line, "Vrederust", planned, planned + timedelta(minutes=delay), **more)


# --- Reading OVapi's answers -----------------------------------------------------------------


def test_read_sorts_by_expected_time_and_marks_left_and_cancelled():
    stop = read({"31001118": PERRON_A})["31001118"]
    assert stop.name == "Rotterdam Centraal perron A"
    assert [(d.line, f"{d.expected:%H:%M}") for d in stop.departures] == [
        ("14", "08:02"),
        ("18", "08:12"),
        ("14", "08:23"),
        ("18", "09:37"),
    ]
    first, late = stop.departures[0], stop.departures[1]
    assert first.left and not first.cancelled
    assert late.delay == 5 and late.expected.tzinfo is ZONE
    assert stop.departures[3].cancelled


def test_read_uses_the_planned_time_without_an_expected_one():
    item = passing("5", "Carnisselande", "2026-10-24T08:14:00")
    del item["ExpectedDepartureTime"]
    stop = read(answer(a=("A", [item])))["a"]
    assert stop.departures[0].expected == stop.departures[0].planned


@pytest.mark.parametrize("bad", [[], {"x": {"Passes": {"1": {"LinePublicNumber": "9"}}}}])
def test_read_refuses_an_answer_it_cant_read(bad):
    with pytest.raises(AnswerError):
        read(bad)


def test_shown_keeps_the_lines_and_the_time_window():
    stop = Stop("x", "X", (at(-6), at(-5), at(10, line="12"), at(10, line="9A"), at(60), at(61)))
    assert shown(stop, (), NOW, 60) == list(stop.departures[1:5])
    assert shown(stop, ("9a", "12"), NOW, 60) == [stop.departures[2], stop.departures[3]]


def test_saved_departures_come_back(tmp_path):
    stops = read({"31001118": PERRON_A})
    path = tmp_path / SAVED
    path.write_bytes(save(stops, NOW))
    assert load(path) == (stops, NOW)
    path.write_text("not json")
    assert load(path) is None
    assert load(tmp_path / "missing.json") is None


# --- Settings --------------------------------------------------------------------------------


def test_codes_and_lines_may_be_written_as_numbers():
    settings = Settings(stop_1=31001118, lines_1=9)
    assert (settings.stop_1, settings.lines_1) == ("31001118", "9")


def test_a_code_is_only_letters_and_digits():
    with pytest.raises(ValidationError):
        Settings(stop_1="3100/../x")


def test_lines_of_takes_commas_or_spaces():
    assert lines_of(" 9, 12 17,") == ("9", "12", "17")
    assert lines_of("") == ()


def test_today_stops_keeps_the_days():
    settings = Settings(stop_1="a", stop_2="b", days_2=("mon", "fri"), stop_4="d")
    assert today_stops(settings, NOW) == [1, 4]
    assert today_stops(settings, NOW + timedelta(days=2)) == [1, 2, 4]  # Monday


# --- Fetching --------------------------------------------------------------------------------


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)

    def make(**settings):
        return Context(Settings(**settings), 1200, 825, ScreenMode.gray(16), tmp_path, "sections")

    return make


def fake_get(monkeypatch, body=None, error=None) -> list:
    asked = []

    def get(url, **options):
        asked.append(url)
        if error:
            raise error
        return webrequest.Answer(200, body, {}, url)

    monkeypatch.setattr(webrequest, "get", get)
    return asked


def test_fetch_asks_for_all_stops_at_once(context, monkeypatch):
    import json

    body = json.dumps({"31001118": PERRON_A}).encode()
    asked = fake_get(monkeypatch, body)
    fetched = fetch(context(stop_1="31001118", lines_1="18", walk_1=4, stop_2="31001039"))
    assert asked == ["http://v0.ovapi.nl/tpc/31001039,31001118"]
    assert fetched.state is State.READY
    first, second = fetched.data.sections
    assert first.title == "Rotterdam Centraal perron A" and first.walk == 4
    assert [d.line for d in first.departures] == ["18"]  # 09:37 is more than 60 min ahead
    assert second == Section("31001039", 0, (), missing=True)
    assert (context().storage / SAVED).is_file()


def test_fetch_has_nothing_on_a_day_without_stops(context, monkeypatch):
    asked = fake_get(monkeypatch, b"{}")
    assert fetch(context(stop_1="a", days_1=("mon",))) is NOTHING
    assert asked == []


def test_fetch_shows_saved_departures_when_ovapi_cant_be_reached(context, monkeypatch):
    stops = read({"31001118": PERRON_A})
    saved = context().storage / SAVED
    saved.write_bytes(save(stops, NOW - OLDEST + timedelta(minutes=1)))
    fake_get(monkeypatch, error=webrequest.WebError("v0.ovapi.nl can't be reached"))
    board = fetch(context(stop_1="31001118", name_1="Tram")).data
    assert board.fetched == NOW - OLDEST + timedelta(minutes=1)
    assert board.sections[0].title == "Tram"

    saved.write_bytes(save(stops, NOW - OLDEST - timedelta(minutes=1)))
    with pytest.raises(webrequest.WebError):
        fetch(context(stop_1="31001118"))


def test_fetch_fails_on_an_answer_it_cant_read_without_saved_departures(context, monkeypatch):
    fake_get(monkeypatch, b"[]")
    with pytest.raises(AnswerError):
        fetch(context(stop_1="31001118"))


# --- Drawing ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("departure", "walk", "text"),
    [
        (at(10, cancelled=True), 4, "cancelled"),
        (at(10, left=True), 4, "left"),
        (at(-1), 0, "left"),  # its time has passed, though OVapi didn't say so yet
        (at(10), 0, ""),
        (at(10), 4, "leave in 6 min"),
        (at(4, delay=1), 4, "leave in 1 min"),
        (at(4), 4, "leave now"),
        (at(3), 4, "too late"),
    ],
)
def test_note(departure, walk, text):
    assert note(departure, walk, NOW) == text


def test_draw_fills_each_stop_and_says_when_it_was_updated(context):
    board = Board(
        (
            Section("Tram 9", 4, (at(2, delay=2), at(10))),
            Section("Bus", 0, ()),
            Section("Gone", 0, (), missing=True),
        ),
        NOW,
        NOW - timedelta(minutes=6),
    )
    values = draw(board, context(stop_1="a", stop_2="b", stop_3="c"))
    assert values["head_0"] == "Tram 9 · 4 min walk"
    assert [values[f"{b}_0_0"] for b in ("time", "delay", "line", "dest", "note")] == [
        "08:14",
        "+2",
        "9",
        "Vrederust",
        "leave now",
    ]
    assert values["note_0_1"] == "leave in 6 min"
    assert values["head_1"] == "Bus" and values["dest_1_0"] == "No departures in the next 60 min"
    assert values["dest_2_0"] == "Stop not found: check its code"
    assert values["footer"] == "Not updated since 08:04"


def test_draw_leaves_out_stops_the_layout_has_no_room_for(context):
    board = Board((Section("A", 0, (at(5),)), Section("B", 0, (at(6),))), NOW, NOW)
    values = draw(board, context(stop_1="a"))
    assert "head_1" not in values and values["footer"] == "Updated 08:10"


def test_layout_shares_the_rows_between_the_stops():
    blocks = PLUGIN.layout("sections", Settings(stop_1="a", stop_3="c")).blocks
    assert sorted(n for n in blocks if n.startswith("head_")) == ["head_0", "head_1"]
    assert sum(1 for n in blocks if n.startswith("dest_1_")) == 5

