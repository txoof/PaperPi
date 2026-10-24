"""The nl_openbaar_vervoer plugin: reading OVapi's answers, choosing departures, the saved
departures and drawing."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from epdlib import ScreenMode
from pydantic import ValidationError

import paperpi.plugins.nl_openbaar_vervoer as plugin_module
from paperpi import webrequest
from paperpi.plugin import NOTHING, Context, State
from paperpi.plugins.nl_openbaar_vervoer import (
    OLDEST,
    PLUGIN,
    QUICKEST,
    SAVED,
    Board,
    Section,
    Settings,
    SettingsMissing,
    draw,
    fetch,
    lines_of,
    note,
    ns,
    today_routes,
    today_stops,
)
from paperpi.plugins.nl_openbaar_vervoer.departures import (
    ZONE,
    AnswerError,
    Departure,
    Saved,
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
    assert [(d.line, f"{d.expected.astimezone(ZONE):%H:%M}") for d in stop.departures] == [
        ("14", "08:02"),
        ("18", "08:12"),
        ("14", "08:23"),
        ("18", "09:37"),
    ]
    first, late = stop.departures[0], stop.departures[1]
    assert first.left and not first.cancelled
    assert late.delay == 5 and late.expected.tzinfo is UTC
    assert stop.departures[3].cancelled


def test_delay_counts_the_minutes_shown():
    planned = datetime(2026, 10, 24, 8, 7, tzinfo=ZONE)
    late = Departure("9", "X", planned, planned + timedelta(minutes=2, seconds=40))
    assert late.delay == 2  # shown as 08:09, so +2, not +3


def test_times_in_the_hour_that_happens_twice_are_in_order():
    # 25 October 2026: the clocks go back from 03:00 to 02:00. OVapi's times have no time
    # zone; read as UTC they stay comparable with the time now.
    stop = read(answer(a=("A", [passing("9", "X", "2026-10-25T02:30:00")])))["a"]
    now = datetime(2026, 10, 25, 0, 20, tzinfo=UTC)  # 02:20 summer time
    assert shown(stop, (), now, 60)[0].expected - now == timedelta(minutes=10)


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


def saved(fetched, codes=("31001118",)) -> bytes:
    return save(Saved(read({"31001118": PERRON_A}), frozenset(codes), fetched))


def test_saved_departures_come_back(tmp_path):
    latest = Saved(read({"31001118": PERRON_A}), frozenset({"31001118", "x"}), NOW)
    path = tmp_path / SAVED
    path.write_bytes(save(latest))
    assert load(path) == latest
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
    assert today_stops(Settings(stop_1="a", days_1=()), NOW) == []  # no days: never shown


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
    body = json.dumps({"31001118": PERRON_A}).encode()
    asked = fake_get(monkeypatch, body)
    fetched = fetch(context(stop_1="31001118", lines_1="18", walk_1=4, stop_2="31001039"))
    assert asked == ["http://v0.ovapi.nl/tpc/31001039,31001118"]
    assert fetched.state is State.READY
    first, second = fetched.data.sections
    assert first.title == "Rotterdam Centraal perron A" and first.walk == 4
    assert [d.line for d in first.departures] == ["18"]  # 09:37 is more than 60 min ahead
    assert second == Section("31001039", 0, (), "Stop not found: check its code")
    assert load(context().storage / SAVED).asked == {"31001039", "31001118"}


def test_fetch_asks_at_most_once_a_minute(context, monkeypatch):
    path = context().storage / SAVED
    path.write_bytes(saved(NOW - QUICKEST + timedelta(seconds=1)))
    asked = fake_get(monkeypatch, b"{}")
    assert fetch(context(stop_1="31001118")).data.sections[0].departures
    assert asked == []
    fetch(context(stop_1="31001118", stop_2="31001039"))  # a stop that was not asked for
    path.write_bytes(saved(NOW - QUICKEST))
    fetch(context(stop_1="31001118"))
    assert len(asked) == 2


def test_fetch_doesnt_save_a_new_file_when_the_disk_is_almost_full(context, monkeypatch):
    fake_get(monkeypatch, json.dumps({"31001118": PERRON_A}).encode())
    ctx = context(stop_1="31001118")
    assert fetch(replace(ctx, low_disk=True)).state is State.READY
    assert not (ctx.storage / SAVED).exists()


def test_fetch_has_nothing_on_a_day_without_stops(context, monkeypatch):
    asked = fake_get(monkeypatch, b"{}")
    assert fetch(context(stop_1="a", days_1=("mon",))) is NOTHING
    assert asked == []


@pytest.mark.parametrize(
    "failure",
    [{"error": webrequest.WebError("v0.ovapi.nl can't be reached")}, {"body": b"[]"}],
    ids=["unreachable", "unreadable"],
)
def test_fetch_shows_saved_departures_when_ovapi_fails(context, monkeypatch, failure):
    path = context().storage / SAVED
    path.write_bytes(saved(NOW - OLDEST + timedelta(minutes=1)))
    fake_get(monkeypatch, **failure)
    board = fetch(context(stop_1="31001118", name_1="Tram", stop_2="31001039")).data
    assert board.fetched == NOW - OLDEST + timedelta(minutes=1)
    assert board.sections[0].title == "Tram" and board.sections[0].departures
    # Added since the last answer: not known to be wrong.
    assert board.sections[1].problem == "No saved times yet"

    path.write_bytes(saved(NOW - OLDEST - timedelta(minutes=1)))
    with pytest.raises((webrequest.WebError, AnswerError)):
        fetch(context(stop_1="31001118"))
    path.unlink()
    with pytest.raises((webrequest.WebError, AnswerError)):
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
            Section("Gone", 0, (), "Stop not found: check its code"),
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


@pytest.mark.parametrize(("stops", "rows"), [(0, 11), (1, 11), (2, 5), (3, 3), (4, 2)])
def test_layout_shares_the_rows_between_the_stops(stops, rows, monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)
    settings = Settings(**{f"stop_{n}": "a" for n in range(1, stops + 1)})
    blocks = PLUGIN.layout("sections", settings).blocks
    heads = max(stops, 1)
    assert sorted(n for n in blocks if n.startswith("head_")) == [f"head_{s}" for s in range(heads)]
    assert all(sum(1 for n in blocks if n.startswith(f"dest_{s}_")) == rows for s in range(heads))


def test_layout_leaves_out_stops_not_shown_today(monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)  # a Saturday
    settings = Settings(stop_1="a", days_1=("mon",), stop_2="b")
    blocks = PLUGIN.layout("sections", settings).blocks
    assert "head_1" not in blocks and sum(1 for n in blocks if n.startswith("dest_0_")) == 11


# --- NS trains -------------------------------------------------------------------------------


def trip(planned, actual=None, track="7", new_track=None, arrival="09:17", transfers=0, **more):
    """One trip as the NS journey planner sends it (the fields the plugin reads, copied from a
    real answer for Den Haag Centraal → Utrecht Centraal, 24 October 2026)."""
    day = "2026-10-24T"
    start = {"name": "Den Haag Centraal", "plannedDateTime": f"{day}{planned}:00+0200"}
    start["plannedTrack"] = track
    if actual:
        start["actualDateTime"] = f"{day}{actual}:00+0200"
    if new_track:
        start["actualTrack"] = new_track
    end = {"name": "Utrecht Centraal", "plannedDateTime": f"{day}{arrival}:00+0200"}
    legs = [{"origin": start, "destination": end, "product": {"shortCategoryName": "IC"}}]
    legs += [{"origin": {}, "destination": end, "product": {}} for _ in range(transfers)]
    if transfers:
        legs[0]["destination"] = {"name": "Leiden Centraal"}
    return {"status": "NORMAL", "transfers": transfers, "legs": legs} | more


def trips(*items) -> dict:
    return {"source": "HARP", "trips": list(items)}


def disruption(title, kind, *stations, active=True) -> dict:
    section = {"stations": [{"stationCode": code} for code in stations]}
    return {
        "title": title,
        "type": kind,
        "isActive": active,
        "publicationSections": [{"section": section}],
    }


def test_read_trips_keeps_direct_trains_and_marks_platform_changes():
    answer = trips(
        trip("08:40", "08:42", track="7", new_track="2"),
        trip("08:58", transfers=1),
        trip("08:55", arrival="09:32", track="8"),
        trip("09:10", status="CANCELLED"),
    )
    route, last = ns.read_trips(answer, "GVC", "UT", changes=False)
    assert f"{last.astimezone(ZONE):%H:%M}" == "09:10"
    assert (route.code, route.name) == ("GVC-UT", "Den Haag Centraal → Utrecht Centraal")
    assert [d.destination for d in route.departures] == [
        "spoor 2 (was 7)",
        "spoor 8 → 09:32",
        "spoor 7 → 09:17",
    ]
    assert route.departures[0].delay == 2 and route.departures[0].line == "IC"
    assert route.departures[2].cancelled
    with_changes, _ = ns.read_trips(answer, "GVC", "UT", changes=True)
    assert with_changes.departures[2].destination == "spoor 7 · 1 change"


def test_read_trips_refuses_an_answer_it_cant_read():
    with pytest.raises(AnswerError):
        ns.read_trips({"trips": [{"legs": []}]}, "GVC", "UT", changes=False)


def test_read_disruptions_keeps_the_ones_on_the_route():
    answer = [
        disruption("Utrecht - Leiden.", "MAINTENANCE", "UT", "LEDN", "GVC"),
        disruption("Amsterdam - Köln.", "DISRUPTION", "ASD", "UT", "KOLN"),
        disruption("Den Haag - Utrecht", "DISRUPTION", "GVC", "UT", active=False),
    ]
    assert ns.read_disruptions(answer, "GVC", "UT") == (
        ns.Notice("Utrecht - Leiden", "MAINTENANCE"),
    )
    with pytest.raises(AnswerError):
        ns.read_disruptions({}, "GVC", "UT")


def test_station_codes_are_letters_in_capitals():
    assert Settings(train_from_1="gvc").train_from_1 == "GVC"
    with pytest.raises(ValidationError):
        Settings(train_from_1="GV/C")


def test_today_routes_needs_both_stations_and_keeps_the_days():
    settings = Settings(
        train_from_1="GVC", train_to_1="UT", train_days_1=("mon",), train_from_2="UT"
    )
    assert today_routes(settings, NOW) == []
    assert today_routes(settings, NOW + timedelta(days=2)) == [1]  # Monday


def fake_ns(monkeypatch, answers: dict) -> list:
    """Answers by part of the address: "trips" (one answer, or a list of one per request),
    "disruptions" and "tpc"."""
    asked = []

    def get(url, headers=None, **options):
        asked.append((url, dict(headers or {})))
        for key, body in answers.items():
            if f"/{key}" in url:
                body = body.pop(0) if key == "trips" and isinstance(body, list) else body
                return webrequest.Answer(200, json.dumps(body).encode(), {}, url)
        raise AssertionError(url)

    monkeypatch.setattr(webrequest, "get", get)
    return asked


TRAINS = {"stop_1": "", "train_from_1": "GVC", "train_to_1": "UT", "ns_key": "secret"}


def test_fetch_needs_a_stop_or_a_route(context, monkeypatch):
    fake_get(monkeypatch, b"{}")
    with pytest.raises(SettingsMissing):
        fetch(context(train_from_1="GVC"))


def test_fetch_says_when_trains_need_a_key(context, monkeypatch):
    asked = fake_get(monkeypatch, b"{}")
    board = fetch(context(train_from_1="GVC", train_to_1="UT", train_walk_1=12)).data
    assert board.sections == (
        Section("GVC → UT", 12, (), "Trains need an NS key (ns_key)", "to UT"),
    )
    assert asked == []


def test_fetch_asks_again_when_the_trips_end_too_soon(context, monkeypatch):
    answers = {
        "trips": [trips(trip("08:12"), trip("08:27")), trips(trip("08:27"), trip("08:42"))],
        "disruptions": [disruption("Works", "MAINTENANCE", "GVC", "UT")],
    }
    asked = fake_ns(monkeypatch, answers)
    fetched = fetch(context(**TRAINS))
    assert fetched.state is State.READY
    urls = [url for url, _ in asked]
    assert "fromStation=GVC&toStation=UT&dateTime=2026-10-24T08%3A05%3A00%2B02%3A00" in urls[0]
    assert "dateTime=2026-10-24T08%3A28%3A00" in urls[1]  # after the last one
    assert urls[2].endswith("/v3/disruptions/station/GVC")
    assert all(headers == {"Ocp-Apim-Subscription-Key": "secret"} for _, headers in asked)
    route = fetched.data.sections[0]
    assert route.title == "Den Haag Centraal → Utrecht Centraal"
    assert route.short == "to Utrecht Centraal"
    assert [f"{d.planned.astimezone(ZONE):%H:%M}" for d in route.departures] == [
        "08:12",
        "08:27",
        "08:42",
    ]
    assert fetched.data.notices == (ns.Notice("Works", "MAINTENANCE"),)


def test_a_disruption_makes_an_alert_only_when_asked(context, monkeypatch):
    def answers():
        return {
            "trips": trips(*(trip(f"0{h}:10") for h in range(8, 10))),
            "disruptions": [disruption("Signal fault", "DISRUPTION", "UT", "GVC")],
        }

    fake_ns(monkeypatch, answers())
    assert fetch(context(**TRAINS)).state is State.READY
    for saved in context().storage.iterdir():
        saved.unlink()
    fake_ns(monkeypatch, answers())
    assert fetch(context(**TRAINS, alert_on_disruption=True)).state is State.ALERT


def test_disruptions_are_asked_at_most_every_10_minutes(context, monkeypatch):
    answers = {"trips": trips(trip("09:30")), "disruptions": []}
    asked = fake_ns(monkeypatch, answers)
    fetch(context(**TRAINS))
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW + timedelta(minutes=9))
    fetch(context(**TRAINS))
    assert sum("disruptions" in url for url, _ in asked) == 1


def test_a_refused_key_doesnt_hide_the_trams(context, monkeypatch):
    def get(url, **options):
        if "ovapi" in url:
            return webrequest.Answer(200, json.dumps({"31001118": PERRON_A}).encode(), {}, url)
        raise webrequest.WebError("gateway.apiportal.ns.nl answered 401 Unauthorized")

    monkeypatch.setattr(webrequest, "get", get)
    board = fetch(context(**TRAINS | {"stop_1": "31001118"})).data
    assert board.sections[0].departures
    assert board.sections[1].problem == "NS key not accepted"


def test_draw_shows_the_notices(context):
    notices = (ns.Notice("Signal fault", "DISRUPTION"), ns.Notice("Works", "MAINTENANCE"))
    board = Board((Section("A", 0, (at(5),)),), NOW, NOW, notices)
    assert draw(board, context(stop_1="a"))["notice"] == "Disruption: Signal fault; Works: Works"


def test_trips_are_asked_for_whole_minutes():
    start = datetime(2026, 10, 24, 8, 5, 42, 123456, tzinfo=UTC)
    assert "dateTime=2026-10-24T10%3A05%3A00%2B02%3A00" in ns.trips_url("GVC", "UT", start)


def test_the_second_request_starts_after_the_last_trip_even_with_changes(context, monkeypatch):
    first = trips(*(trip(f"08:{m}", transfers=1) for m in ("10", "20", "30", "40", "50")))
    asked = fake_ns(monkeypatch, {"trips": [first, trips(trip("09:05"))], "disruptions": []})
    board = fetch(context(**TRAINS)).data
    assert "dateTime=2026-10-24T08%3A51%3A00" in asked[1][0]
    assert len(board.sections[0].departures) == 1


def test_a_failed_second_request_keeps_the_first_trips(context, monkeypatch):
    calls = []

    def get(url, **options):
        calls.append(url)
        if "trips" in url and len(calls) == 1:
            return webrequest.Answer(200, json.dumps(trips(trip("08:12"))).encode(), {}, url)
        if "disruptions" in url:
            return webrequest.Answer(200, b"[]", {}, url)
        raise webrequest.WebError("gateway.apiportal.ns.nl answered 503 Service Unavailable")

    monkeypatch.setattr(webrequest, "get", get)
    assert len(fetch(context(**TRAINS)).data.sections[0].departures) == 1


def test_train_times_are_reused_for_a_while(context, monkeypatch):
    asked = fake_ns(monkeypatch, {"trips": trips(trip("09:30")), "disruptions": []})
    fetch(context(**TRAINS))
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW + ns.TRIPS_EVERY - timedelta(seconds=1))
    fetch(context(**TRAINS))
    assert sum("trips" in url for url, _ in asked) == 1
    assert (context().storage / "trains_GVC-UT.json").is_file()


def test_saved_trips_are_shown_when_ns_fails(context, monkeypatch):
    fake_ns(monkeypatch, {"trips": trips(trip("08:40")), "disruptions": []})
    fetch(context(**TRAINS))
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW + timedelta(minutes=10))

    def get(url, **options):
        raise webrequest.WebError("gateway.apiportal.ns.nl can't be reached")

    monkeypatch.setattr(webrequest, "get", get)
    board = fetch(context(**TRAINS)).data
    assert board.sections[0].departures and board.fetched == NOW


@pytest.mark.parametrize(
    ("message", "problem"),
    [
        ("answered 401 Unauthorized", "NS key not accepted"),
        ("answered 429 Too Many Requests", None),
    ],
)
def test_a_refused_key_is_shown_even_with_only_trains(context, monkeypatch, message, problem):
    def get(url, **options):
        raise webrequest.WebError(f"gateway.apiportal.ns.nl {message}")

    monkeypatch.setattr(webrequest, "get", get)
    if problem:
        assert fetch(context(**TRAINS)).data.sections[0].problem == problem
    else:  # nothing at all to show: the update fails, PaperPi logs why and tries again
        with pytest.raises(webrequest.WebError):
            fetch(context(**TRAINS))


def test_too_many_requests_is_said_plainly(context, monkeypatch):
    def get(url, **options):
        if "ovapi" in url:
            return webrequest.Answer(200, json.dumps({"31001118": PERRON_A}).encode(), {}, url)
        raise webrequest.WebError("gateway.apiportal.ns.nl answered 429 Too Many Requests")

    monkeypatch.setattr(webrequest, "get", get)
    board = fetch(context(**TRAINS | {"stop_1": "31001118"})).data
    assert board.sections[1].problem == "NS: too many requests today"


def test_layout_counts_stops_and_routes_and_has_a_notice(monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)
    settings = Settings(
        stop_1="a", stop_2="b", **{k: v for k, v in TRAINS.items() if k != "stop_1"}
    )
    blocks = PLUGIN.layout("sections", settings).blocks
    assert sum(1 for n in blocks if n.startswith("head_")) == 3 and "notice" in blocks


def test_small_sections_leave_out_what_has_left(context):
    board = Board((Section("A", 0, (at(-2, left=True), at(-1), at(5), at(9))),), NOW, NOW)
    settings = {f"stop_{n}": "a" for n in range(1, 5)} | {"train_from_1": "A", "train_to_1": "B"}
    values = draw(board, context(**settings))
    assert values["time_0_0"] == "08:15"


# --- The layouts "by_time" and "next" --------------------------------------------------------


@pytest.fixture
def layout_context(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)

    def make(layout, **settings):
        settings = {"stop_1": "a"} | settings
        return Context(Settings(**settings), 1200, 825, ScreenMode.gray(16), tmp_path, layout)

    return make


def test_every_layout_has_a_title_and_a_footer(monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)
    for name in PLUGIN.layouts:
        blocks = PLUGIN.layout(name, Settings(stop_1="a")).blocks
        assert PLUGIN.layout_title(name) != name and {"notice", "footer"} <= set(blocks)


def test_by_time_merges_the_stops_soonest_first(layout_context):
    tram = Section("Tram", 4, (at(-2, left=True), at(6), at(20)))
    train = Section("A → B", 0, (at(9, line="IC"),), short="to B")
    values = draw(Board((tram, train), NOW, NOW), layout_context("by_time"))
    rows = [(values[f"time_{i}"], values[f"line_{i}"], values[f"stop_{i}"]) for i in range(3)]
    assert rows == [("08:16", "9", "Tram"), ("08:19", "IC", "to B"), ("08:30", "9", "Tram")]
    assert values["note_0"] == "leave in 2 min" and values["note_1"] == ""
    assert "time_3" not in values  # the one that left is left out


def test_by_time_shows_problems_first_and_fills_twelve_rows(layout_context):
    full = Section("Tram", 0, tuple(at(m) for m in range(1, 30)))
    lost = Section("Bus", 0, (), "Stop not found: check its code")
    values = draw(Board((full, lost), NOW, NOW), layout_context("by_time"))
    assert (values["stop_0"], values["dest_0"]) == ("Bus", "Stop not found: check its code")
    assert values["time_1"] == "08:11" and values["time_11"] == "08:21" and "time_12" not in values


def test_by_time_without_departures_says_so(layout_context):
    board = Board((Section("Tram", 0, (at(-1),)),), NOW, NOW)
    assert draw(board, layout_context("by_time"))["dest_0"] == "No departures in the next 60 min"


def test_next_shows_the_first_one_that_can_be_caught_large(layout_context):
    section = Section(
        "Tram",
        4,
        (at(-1, left=True), at(3), at(6, cancelled=True), at(8, line="12", delay=2), at(15)),
    )
    other = Section("Bus", 0, (at(1),))
    values = draw(Board((section, other), NOW, NOW), layout_context("next"))
    assert values["head_0"] == "Tram · 4 min walk"
    assert values["next_dest"] == "12  Vrederust"
    assert values["next_note"] == "Leave in 6 min"
    assert values["next_time"] == "08:20 (+2)"
    assert values["time_0_0"] == "08:25" and "time_0_1" not in values  # only those after it


@pytest.mark.parametrize(("minutes", "text"), [(9, "Leaves in 9 min"), (0, "Leaves now")])
def test_next_without_walking_time_says_when_it_leaves(layout_context, minutes, text):
    board = Board((Section("Tram", 0, (at(minutes),)),), NOW, NOW)
    assert draw(board, layout_context("next"))["next_note"] == text


@pytest.mark.parametrize(
    ("section", "text"),
    [
        (
            Section("Tram", 0, (), "Stop not found: check its code"),
            "Stop not found: check its code",
        ),
        (Section("Tram", 0, (at(2, cancelled=True),)), "No departures in the next 60 min"),
    ],
)
def test_next_without_a_departure_says_why(layout_context, section, text):
    values = draw(Board((section,), NOW, NOW), layout_context("next"))
    assert values["next_dest"] == text and "next_note" not in values


def test_next_with_nothing_today_only_has_the_footer(layout_context):
    assert draw(Board((), NOW, NOW), layout_context("next")) == {"footer": "Updated 08:10"}


def test_by_time_uses_the_title_without_a_short_one_and_shows_only_problems(layout_context):
    lost = tuple(Section(f"Stop {n}", 0, (), "Stop not found: check its code") for n in range(13))
    values = draw(Board(lost, NOW, NOW), layout_context("by_time"))
    assert values["stop_11"] == "Stop 11" and "stop_12" not in values
    assert all(values[f"dest_{i}"].startswith("Stop not found") for i in range(12))


def test_next_uses_only_the_first_section(layout_context):
    board = Board(
        (Section("Tram", 0, (), "No saved times yet"), Section("Bus", 0, (at(5),))), NOW, NOW
    )
    values = draw(board, layout_context("next"))
    assert values["next_dest"] == "No saved times yet" and "time_0_0" not in values


def test_next_keeps_cancelled_ones_in_the_small_rows(layout_context):
    board = Board((Section("Tram", 0, (at(2), at(5, cancelled=True), at(9))),), NOW, NOW)
    values = draw(board, layout_context("next"))
    assert values["note_0_0"] == "cancelled" and values["time_0_1"] == "08:19"


def test_next_fetches_only_the_first_stop_or_route(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)
    asked = fake_get(monkeypatch, json.dumps({"31001118": PERRON_A}).encode())
    settings = Settings(**TRAINS | {"stop_1": "31001118", "stop_2": "31001039"})
    board = fetch(Context(settings, 1200, 825, ScreenMode.gray(16), tmp_path, "next")).data
    assert [s.title for s in board.sections] == ["Rotterdam Centraal perron A"]
    assert len(asked) == 1 and asked[0].endswith("/tpc/31001118")


def test_next_with_only_trains_fetches_the_first_route(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_module, "_now", lambda: NOW)
    settings = Settings(**TRAINS | {"ns_key": "", "train_from_2": "UT", "train_to_2": "ASD"})
    board = fetch(Context(settings, 1200, 825, ScreenMode.gray(16), tmp_path, "next")).data
    assert [s.short for s in board.sections] == ["to UT"]  # no key: not asked
