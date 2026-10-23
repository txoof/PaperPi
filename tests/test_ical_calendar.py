"""The ical_calendar plugin: reading iCal files, the saved events, merging and drawing."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from epdlib import ScreenMode
from pydantic import SecretStr

import paperpi.plugins.ical_calendar as ical_calendar
from paperpi import webrequest
from paperpi.plugin import Context
from paperpi.plugins.ical_calendar import Agenda, Settings, address, draw, fetch
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


def test_read_refuses_what_is_not_a_calendar():
    with pytest.raises(CalendarError):
        read(b"<html><body>Sign in</body></html>", NOW, NOW + timedelta(days=7))


# --- Settings --------------------------------------------------------------------------------


def test_address_turns_webcal_into_https():
    assert address("calendar_1", SecretStr(" webcal://example.com/a.ics ")) == (
        "https://example.com/a.ics"
    )


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
    assert fetched.data.saved is None
    assert (tmp_path / "calendar_1.json").is_file() and (tmp_path / "calendar_3.json").is_file()


def test_fetch_uses_saved_events_when_a_calendar_cant_be_downloaded(calendars, tmp_path):
    calendars[URL_1] = ics(soon("Mine", 2))
    calendars[URL_2] = ics(soon("Family", 3))
    settings = {"calendar_1": URL_1, "calendar_2": URL_2}
    fetch(context(tmp_path, **settings))
    calendars[URL_2] = webrequest.WebError("calendar.example.com can't be reached")
    fetched = fetch(context(tmp_path, **settings))
    assert sorted(e.title for e in fetched.data.events) == ["Family", "Mine"]
    assert fetched.data.saved is not None


def test_fetch_fails_without_usable_saved_events(calendars, tmp_path):
    calendars[URL_1] = webrequest.WebError("calendar.example.com can't be reached")
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path, calendar_1=URL_1))
    # Saved events of another address, or too old, are not used.
    old = datetime.now(UTC) - timedelta(days=2)
    event = Event("Old", old, old + timedelta(hours=1))
    (tmp_path / "calendar_1.json").write_bytes(save([event], "another key", datetime.now(UTC)))
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path, calendar_1=URL_1))
    key = ical_calendar.hashlib.sha256(URL_1.encode()).hexdigest()
    (tmp_path / "calendar_1.json").write_bytes(save([event], key, old))
    with pytest.raises(webrequest.WebError):
        fetch(context(tmp_path, calendar_1=URL_1))


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


def drawn(events, layout="list", saved=None, calendars=("Mine", None, None), **settings):
    agenda = Agenda(tuple(events), NOW, saved, "Europe/Berlin", calendars)
    return draw(agenda, Context(Settings(calendar_1=URL_1, **settings), 1200, 825,
                                ScreenMode.gray(16), None, layout))  # fmt: skip


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
    assert values["today"] == "Wednesday 30 September" and values["legend"] == ""


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


def test_draw_12_hour_times_and_the_saved_time():
    values = drawn([Event("Club", *at(0, 18, 45))], hours=12, saved=NOW - timedelta(hours=2))
    assert values["time_0"] == "6:45 PM" and values["legend"] == "Saved 7:15 AM"


def test_small_layout_puts_day_and_time_together():
    values = drawn(
        [Event("Club", *at(0, 18, 45)), Event("Rent", date(2026, 10, 1), date(2026, 10, 2))],
        layout="small",
    )
    assert values == {"when_0": "18:45", "title_0": "Club", "when_1": "Thu 1", "title_1": "Rent"}


def test_draw_marks_each_calendar_when_there_are_several():
    values = drawn(
        [Event("Club", *at(0, 18)), Event("Rent", *at(0, 20), calendar=2)],
        saved=NOW - timedelta(hours=2),
        calendars=("Personal", None, "Family"),
    )
    assert values["legend"] == "● Personal  ■ Family  Saved 07:15"
    assert values["title_0"] == "● Club" and values["title_1"] == "■ Rent"
