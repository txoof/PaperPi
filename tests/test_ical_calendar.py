"""The ical_calendar plugin: reading iCal files, the saved events, merging and drawing."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from epdlib import ScreenMode
from PIL import ImageOps
from pydantic import SecretStr

import paperpi.plugins.ical_calendar as ical_calendar
from paperpi import webrequest
from paperpi.plugin import Context
from paperpi.plugins.ical_calendar import (
    Agenda,
    Settings,
    address,
    draw,
    fetch,
    mark,
    saved_key,
)
from paperpi.plugins.ical_calendar import events as events_module
from paperpi.plugins.ical_calendar.events import CalendarError, Event, load, read, save

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 9, 30, 9, 15, tzinfo=BERLIN)  # a Wednesday
URL_1 = "https://calendar.example.com/private-abc/basic.ics"
URL_2 = "https://calendar.example.com/private-def/basic.ics"


def ics(*events: str) -> bytes:
    """An iCal file with these VEVENT bodies."""
    parts = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//test//EN"]
    for i, body in enumerate(events):
        parts += ["BEGIN:VEVENT", f"UID:{i}@test", "DTSTAMP:20260901T000000Z", body, "END:VEVENT"]
    parts.append("END:VCALENDAR")
    return "\r\n".join(parts).encode()


def stamp(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


# --- Reading iCal files ----------------------------------------------------------------------


def test_read_keeps_events_in_the_window_and_repeats_weekly_ones():
    body = ics(
        "SUMMARY:Dentist\r\nDTSTART;TZID=Europe/Berlin:20261001T143000\r\n"
        "DTEND;TZID=Europe/Berlin:20261001T153000",
        "SUMMARY:Running club\r\nDTSTART;TZID=Europe/Berlin:20260901T184500\r\n"
        "DURATION:PT1H30M\r\nRRULE:FREQ=WEEKLY",
        "SUMMARY:Autumn break\r\nDTSTART;VALUE=DATE:20260926\r\nDTEND;VALUE=DATE:20261005",
        "SUMMARY:Last week\r\nDTSTART;VALUE=DATE:20260920",
        "SUMMARY:Next month\r\nDTSTART;VALUE=DATE:20261105",
    )
    found = read(body, NOW, NOW + timedelta(days=7))
    titles = sorted(e.title for e in found)
    assert titles == ["Autumn break", "Dentist", "Running club"]  # the 1st, 8th... are Tuesdays
    dentist = next(e for e in found if e.title == "Dentist")
    assert dentist.start == datetime(2026, 10, 1, 14, 30, tzinfo=BERLIN)
    assert dentist.end - dentist.start == timedelta(hours=1)
    autumn = next(e for e in found if e.title == "Autumn break")
    assert autumn.all_day and autumn.end == date(2026, 10, 5)
    club = next(e for e in found if e.title == "Running club")
    assert club.start.date() == date(2026, 10, 6) and club.end - club.start == timedelta(hours=1.5)


def test_read_leaves_out_cancelled_events_and_tidies_titles():
    body = ics(
        "SUMMARY:Gone\r\nSTATUS:CANCELLED\r\nDTSTART;VALUE=DATE:20261001",
        "SUMMARY:  Two\\n lines \r\nDTSTART;VALUE=DATE:20261002",
        "DTSTART;VALUE=DATE:20261003",
    )
    assert sorted(e.title for e in read(body, NOW, NOW + timedelta(days=7))) == [
        "(no title)",
        "Two lines",
    ]


def test_read_takes_floating_times_in_the_given_zone():
    body = ics("SUMMARY:Floating\r\nDTSTART:20261001T100000\r\nDTEND:20261001T110000")
    (event,) = read(body, NOW, NOW + timedelta(days=7), BERLIN)
    assert event.start == datetime(2026, 10, 1, 10, tzinfo=BERLIN)


@pytest.mark.parametrize(
    "body",
    [b"<html><body>Sign in</body></html>", b"", b"BEGIN:VCALENDAR", b'{"a": 1}'],
    ids=["web page", "empty", "cut off", "json"],
)
def test_read_refuses_what_is_not_a_calendar(body):
    with pytest.raises(CalendarError):
        read(body, NOW, NOW + timedelta(days=7))


GOOD = "SUMMARY:Good\r\nDTSTART;TZID=Europe/Berlin:20261001T100000\r\nDURATION:PT1H"


@pytest.mark.parametrize(
    "bad",
    [
        "SUMMARY:No start",
        "SUMMARY:Every second\r\nDTSTART:19000101T000000Z\r\nRRULE:FREQ=SECONDLY",
        "SUMMARY:Every minute\r\nDTSTART:20260930T000000Z\r\nRRULE:FREQ=MINUTELY",
        "SUMMARY:Every hour\r\nDTSTART:20000101T000000Z\r\nRRULE:FREQ=HOURLY",
        "SUMMARY:Too long\r\nDTSTART:20261001T100000Z\r\nDURATION:P99999999D",
    ],
    ids=["no start", "secondly", "minutely", "hourly", "impossible length"],
)
def test_read_leaves_out_broken_or_too_frequent_events(bad):
    """Anyone can send an invitation: one bad event must not stop the calendar or keep
    the Pi busy."""
    assert [e.title for e in read(ics(GOOD, bad), NOW, NOW + timedelta(days=7))] == ["Good"]


def test_read_mends_odd_events():
    body = ics(
        "SUMMARY:First\r\nSUMMARY:Second\r\nDTSTART;VALUE=DATE:20261001",
        "SUMMARY:Same day\r\nDTSTART;VALUE=DATE:20261002\r\nDTEND;VALUE=DATE:20261002",
        f"SUMMARY:{'x' * 500}\r\nDTSTART;VALUE=DATE:20261003",
    )
    found = {e.title[:10]: e for e in read(body, NOW, NOW + timedelta(days=7))}
    assert set(found) == {"First", "Same day", "x" * 10}
    assert found["Same day"].end == date(2026, 10, 3)  # lasts its one day
    assert len(found["x" * 10].title) == 200


def test_read_keeps_the_first_events_only(monkeypatch):
    monkeypatch.setattr(events_module, "MOST_EVENTS", 2)
    body = ics(*(f"SUMMARY:Day {d}\r\nDTSTART;VALUE=DATE:2026100{d}" for d in (3, 1, 2)))
    assert [e.title for e in read(body, NOW, NOW + timedelta(days=7))] == ["Day 1", "Day 2"]


def test_weekly_event_keeps_its_time_after_summer_time_ends():
    body = ics(
        "SUMMARY:Club\r\nDTSTART;TZID=Europe/Berlin:20261020T184500\r\nDURATION:PT1H\r\n"
        "RRULE:FREQ=WEEKLY"
    )
    now = datetime(2026, 10, 24, 9, tzinfo=BERLIN)  # summer time ends on 25 October
    (event,) = read(body, now, now + timedelta(days=7))
    assert event.start.astimezone(BERLIN).hour == 18


# --- Settings --------------------------------------------------------------------------------


def test_address_turns_webcal_into_https():
    assert address("calendar_1", SecretStr(" webcal://example.com/a.ics ")) == (
        "https://example.com/a.ics"
    )


@pytest.mark.parametrize(
    "url",
    ["http://192.168.1.5/cal.ics", "http://nas.local/cal.ics", "http://nas/cal.ics"],
)
def test_address_allows_http_on_the_home_network(url):
    assert address("calendar_1", SecretStr(url)) == url


def test_address_refuses_http_on_the_internet():
    with pytest.raises(ValueError, match="not encrypted") as caught:
        address("calendar_1", SecretStr("http://calendar.example.com/private-secret-123"))
    assert "secret-123" not in str(caught.value)


def test_address_error_never_shows_the_secret():
    with pytest.raises(ValueError, match="calendar_2") as caught:
        address("calendar_2", SecretStr("private-secret-123"))
    assert "secret-123" not in str(caught.value)


# --- Fetching, merging and the saved events --------------------------------------------------


@pytest.fixture
def calendars(monkeypatch):
    """Fake downloads: each address gives its file, or raises its error."""
    answers = {}

    def get(url, **kwargs):
        result = answers[url]
        if isinstance(result, Exception):
            raise result
        return webrequest.Answer(200, result, {}, url)

    monkeypatch.setattr(webrequest, "get", get)
    return answers


def context(tmp_path, **settings):
    return Context(Settings(**settings), 800, 480, ScreenMode.bw(), tmp_path, "list")


def soon(title: str, hours: float) -> str:
    start = datetime.now(UTC) + timedelta(hours=hours)
    return f"SUMMARY:{title}\r\nDTSTART:{stamp(start)}\r\nDTEND:{stamp(start + timedelta(hours=1))}"


def test_fetch_merges_calendars_and_saves_each(calendars, tmp_path):
    calendars[URL_1] = ics(soon("Mine", 2))
    calendars[URL_2] = ics(soon("Family", 1), soon("Far away", 24 * 40))
    fetched = fetch(context(tmp_path, calendar_1=URL_1, calendar_3=URL_2, name_3="Family"))
    assert sorted((e.title, e.calendar) for e in fetched.data.events) == [
        ("Family", 2),
        ("Mine", 0),
    ]
    assert fetched.data.calendars == ("Calendar 1", None, "Family")
    assert (tmp_path / "calendar_1.json").is_file() and (tmp_path / "calendar_3.json").is_file()


def test_fetch_uses_saved_events_when_a_calendar_cant_be_downloaded(calendars, tmp_path):
    calendars[URL_1] = ics(soon("Mine", 2))
    calendars[URL_2] = ics(soon("Family", 3))
    settings = {"calendar_1": URL_1, "calendar_2": URL_2}
    fetch(context(tmp_path, **settings))
    calendars[URL_2] = webrequest.WebError("calendar.example.com can't be reached")
    fetched = fetch(context(tmp_path, **settings))
    assert sorted(e.title for e in fetched.data.events) == ["Family", "Mine"]


def saved_soon(tmp_path, key=None, age=timedelta(hours=1)):
    """A saved file for calendar_1 with one event in 2 hours, saved ``age`` ago."""
    now = datetime.now(UTC)
    event = Event("Saved", now + timedelta(hours=2), now + timedelta(hours=3))
    key = key or saved_key(URL_1, 7)
    (tmp_path / "calendar_1.json").write_bytes(save([event], key, now - age))


@pytest.mark.parametrize(
    "saved",
    [
        pytest.param({}, id="nothing saved"),
        pytest.param({"key": "another address"}, id="other address"),
        pytest.param({"key": saved_key(URL_1, 10)}, id="other days"),
        pytest.param({"age": timedelta(hours=25)}, id="too old"),
    ],
)
def test_fetch_fails_without_usable_saved_events(calendars, tmp_path, saved):
    calendars[URL_1] = webrequest.WebError("calendar.example.com can't be reached")
    if saved:
        saved_soon(tmp_path, **saved)
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path, calendar_1=URL_1))


@pytest.mark.parametrize(
    "failure",
    [
        webrequest.WebError("calendar.example.com can't be reached"),
        b"<html><body>Sign in</body></html>",  # e.g. a login page instead of the calendar
    ],
    ids=["unreachable", "not a calendar"],
)
def test_saved_events_are_used_for_up_to_a_day(calendars, tmp_path, failure):
    calendars[URL_1] = failure
    saved_soon(tmp_path, age=timedelta(hours=23))
    assert [e.title for e in fetch(context(tmp_path, calendar_1=URL_1)).data.events] == ["Saved"]


def test_fetch_shows_the_other_calendars_when_one_fails(calendars, tmp_path):
    calendars[URL_1] = ics(soon("Mine", 2))
    calendars[URL_2] = webrequest.WebError("calendar.example.com answered 404 Not Found")
    fetched = fetch(context(tmp_path, calendar_1=URL_1, calendar_2=URL_2, name_2="Family"))
    assert [e.title for e in fetched.data.events] == ["Mine"]
    assert fetched.data.failed == (1,)
    # A bad address counts as a failed calendar too.
    fetched = fetch(context(tmp_path, calendar_1=URL_1, calendar_2="ftp://example.com/x.ics"))
    assert fetched.data.failed == (1,)


def test_fetch_needs_an_address(tmp_path):
    with pytest.raises(ical_calendar.SettingsMissing):
        fetch(context(tmp_path))


def test_fetch_downloads_webcal_addresses_over_https(calendars, tmp_path):
    calendars[URL_1] = ics(soon("Mine", 2))  # the fake download knows only the https address
    webcal = URL_1.replace("https://", "WEBCAL://")
    assert [e.title for e in fetch(context(tmp_path, calendar_1=webcal)).data.events] == ["Mine"]


def test_saved_file_is_private(calendars, tmp_path):
    calendars[URL_1] = ics(soon("Mine", 2))
    fetch(context(tmp_path, calendar_1=URL_1))
    assert (tmp_path / "calendar_1.json").stat().st_mode & 0o777 == 0o600


def test_fetch_shows_events_it_cant_save(calendars, tmp_path, monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ical_calendar, "write_atomic", fail)
    calendars[URL_1] = ics(soon("Mine", 2))
    assert [e.title for e in fetch(context(tmp_path, calendar_1=URL_1)).data.events] == ["Mine"]
    assert "can't save" in caplog.text


def test_no_new_saved_file_when_the_disk_is_almost_full(calendars, tmp_path):
    calendars[URL_1] = ics(soon("Mine", 2))
    low = Context(Settings(calendar_1=URL_1), 800, 480, ScreenMode.bw(), tmp_path, "list",
                  low_disk=True)  # fmt: skip
    fetch(low)
    assert not (tmp_path / "calendar_1.json").exists()


def test_saved_events_load_back(tmp_path):
    events = [
        Event("Timed", NOW, NOW + timedelta(hours=1)),
        Event("All day", date(2026, 10, 1), date(2026, 10, 2)),
    ]
    path = tmp_path / "saved.json"
    path.write_bytes(save(events, "k", NOW))
    saved = load(path, "k")
    assert saved.events == events and saved.fetched == NOW
    assert load(path, "other") is None
    path.write_bytes(b"not json")
    assert load(path, "k") is None


# --- Drawing ---------------------------------------------------------------------------------


def drawn(events, layout="list", calendars=("Mine", None, None), failed=(), **settings):
    agenda = Agenda(tuple(events), NOW, "Europe/Berlin", calendars, failed)
    screen = Context(Settings(**settings), 1200, 825, ScreenMode.gray(16), None, layout)
    return draw(agenda, screen)


def at(days, hour, minute=0, hours=1.0):
    start = NOW.replace(hour=hour, minute=minute) + timedelta(days=days)
    return start, start + timedelta(hours=hours)


def test_draw_names_each_day_once_and_puts_all_day_events_first():
    values = drawn([
        Event("Club", *at(1, 18, 45)),
        Event("Rent", date(2026, 10, 1), date(2026, 10, 2)),
        Event("Dentist", *at(0, 14, 30)),
        Event("Over", *at(0, 7)),  # ended at 08:00
    ])  # fmt: skip
    assert [values[f"day_{i}"] for i in range(3)] == ["Today", "Tomorrow", ""]
    assert [values[f"title_{i}"] for i in range(3)] == ["Dentist", "Rent", "Club"]
    assert [values[f"time_{i}"] for i in range(3)] == ["14:30", "all day", "18:45"]
    assert values["today"] == "Wednesday 30 September"
    assert not any(name.startswith(("mark_", "key_")) for name in values)  # one calendar


def test_draw_shows_how_long_earlier_events_still_last():
    values = drawn([
        Event("Break", date(2026, 9, 26), date(2026, 10, 5)),
        Event("Ends today", date(2026, 9, 29), date(2026, 10, 1)),
        Event("Night shift", *at(-1, 22, hours=12)),
        Event("Trip", *at(-1, 8, hours=50)),
    ])  # fmt: skip
    times = {values[f"title_{i}"]: values[f"time_{i}"] for i in range(4)}
    assert times == {
        "Break": "until Sun 4",
        "Ends today": "ends today",
        "Night shift": "until 10:00",
        "Trip": "until Thu 1",
    }


def test_draw_says_how_many_more_events_there_are():
    values = drawn([Event(f"Event {n}", *at(1, 8 + n)) for n in range(10)])
    assert values["title_7"] == "+ 3 more" and "day_7" not in values


def test_draw_says_when_nothing_is_planned():
    assert drawn([], days=1)["title_0"] == "Nothing planned for today"
    assert drawn([])["title_0"] == "Nothing planned for the next 7 days"


def test_draw_leaves_out_events_after_the_days_shown():
    assert drawn([Event("Later", *at(3, 10))], days=3)["title_0"].startswith("Nothing")


def test_draw_12_hour_times():
    values = drawn([Event("Club", *at(0, 18, 45))], hours=12)
    assert values["time_0"] == "6:45 PM"
    assert drawn([Event("Club", *at(1, 18, 45))], "small", hours=12)["when_0"] == "Thu 6:45p"


def test_small_layout_puts_day_and_time_together():
    values = drawn(
        [Event("Club", *at(0, 18, 45)), Event("Rent", date(2026, 10, 1), date(2026, 10, 2))],
        layout="small",
    )
    assert values == {"when_0": "18:45", "title_0": "Club", "when_1": "Thu 1", "title_1": "Rent"}


def test_draw_marks_each_calendar_when_there_are_several():
    values = drawn(
        [Event("Club", *at(0, 18)), Event("Rent", *at(0, 20), calendar=2)],
        calendars=("Personal", None, "Family"),
    )
    # Filled from the right: the first of the three places in the header stays empty.
    assert (values["key_name_1"], values["key_name_2"]) == ("Personal", "Family")
    assert "key_name_0" not in values
    assert values["title_0"] == "Club" and values["title_1"] == "Rent"

    # Each event has its calendar's mark, the same size as the one in the header.
    size = ink(values["mark_0"])[0]
    assert values["mark_0"].tobytes() == mark("dot", *values["mark_0"].size, size).tobytes()
    assert values["mark_1"].tobytes() == mark("square", *values["mark_1"].size, size).tobytes()
    assert ink(values["mark_0"]) == ink(values["key_mark_1"])


def ink(picture):
    """The width and height of what was drawn in black."""
    box = ImageOps.invert(picture).getbbox()
    return box[2] - box[0], box[3] - box[1]


def test_draw_three_calendars_fill_the_header():
    values = drawn(
        [Event(t, *at(0, 18 + i), calendar=i) for i, t in enumerate("ABC")],
        calendars=("Personal", "Family", "Work"),
    )
    assert [values[f"key_name_{k}"] for k in range(3)] == ["Personal", "Family", "Work"]
    size = ink(values["mark_0"])[0]
    for k, kind in enumerate(("dot", "ring", "square")):
        picture = values[f"key_mark_{k}"]
        assert picture.tobytes() == mark(kind, *picture.size, size).tobytes()


def test_draw_says_which_calendar_was_not_updated():
    events = [Event(f"Event {n}", *at(1, 8 + n)) for n in range(10)]
    values = drawn(events, calendars=("Personal", "Family", None), failed=(1,))
    assert values["title_7"] == "Family: not updated" and "mark_7" in values
    assert values["title_6"] == "+ 4 more" and "mark_6" not in values
    values = drawn([], calendars=("Personal", "Family", None), failed=(1,))
    assert values["title_0"].startswith("Nothing planned")
    assert values["title_1"] == "Family: not updated"


def test_small_layout_has_marks_but_no_header():
    values = drawn(
        [Event("Club", *at(0, 18)), Event("Rent", *at(0, 20), calendar=1)],
        "small",
        calendars=("Personal", "Family", None),
    )
    assert "mark_0" in values and not any(name.startswith("key_") for name in values)


def test_marks_are_the_same_size_and_differ():
    dot, ring, square = (mark(kind, 40, 60, 24) for kind in ("dot", "ring", "square"))
    assert dot.size == ring.size == square.size == (40, 60)
    assert len({dot.tobytes(), ring.tobytes(), square.tobytes()}) == 3
    ink = [ImageOps.invert(m).getbbox() for m in (dot, ring)]  # where black was drawn
    assert ink[0] == ink[1] is not None  # the circles have the same size and place


def test_draw_an_event_ending_at_midnight_ends_today():
    assert drawn([Event("Night", *at(-1, 20, hours=28))])["time_0"] == "ends today"


@pytest.mark.parametrize(("hour", "text"), [(0, "12:00 AM"), (12, "12:00 PM"), (23, "11:00 PM")])
def test_12_hour_times_around_midnight_and_noon(hour, text):
    assert ical_calendar.clock(datetime(2026, 10, 1, hour), 12) == text
