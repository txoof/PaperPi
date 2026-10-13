"""PaperPi's own log: the last lines in memory, the important ones in a file (paperpi.logbook)."""

import logging
import threading

import pytest

from paperpi import logbook
from paperpi.logbook import KEEP, Logbook

log = logging.getLogger("paperpi.test")


@pytest.fixture
def system_log():
    """Stands in for the handler ``logging.basicConfig`` adds (stderr, the system log)."""
    root = logging.getLogger()
    seen: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: seen.append(record.getMessage())
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    yield seen
    root.removeHandler(handler)
    root.setLevel(level)


@pytest.fixture
def started(tmp_path, system_log):
    book = logbook.start(tmp_path)
    yield book
    logbook.stop(book)


def texts(book: Logbook) -> list[str]:
    return [line.text for line in book.lines()]


def test_memory_keeps_info_and_up_the_file_only_what_matters(started, tmp_path):
    log.debug("details")
    log.info("chatty")
    log.info("started", extra=KEEP)
    log.warning("careful")
    log.error("broken")
    assert texts(started) == ["chatty", "started", "careful", "broken"]
    assert [line.number for line in started.lines()] == [1, 2, 3, 4]
    kept = (tmp_path / "paperpi.log").read_text().splitlines()
    assert [row.split(": ", 1)[1] for row in kept] == ["started", "careful", "broken"]
    assert kept[1].endswith(" WARNING paperpi.test: careful")


def test_the_system_log_gets_what_it_got_before_plus_kept_lines(started, system_log):
    log.info("chatty")
    log.info("health", extra=KEEP)
    log.warning("careful")
    assert system_log == ["health", "careful"]


def test_verbose_keeps_debug_lines_too(tmp_path, system_log):
    book = logbook.start(tmp_path, verbose=True)
    try:
        log.debug("details")
    finally:
        logbook.stop(book)
    assert texts(book) == ["details"]
    assert not (tmp_path / "paperpi.log").exists()


def test_stop_puts_everything_back(tmp_path, system_log):
    book = logbook.start(tmp_path)
    logbook.stop(book)
    log.info("after the stop")
    log.warning("seen")
    assert texts(book) == []
    assert system_log == ["seen"]
    assert logging.getLogger().level == logging.WARNING


def test_only_the_last_lines_are_kept_in_memory():
    book = Logbook(None, lines=3)
    for number in range(5):
        book.add(logging.makeLogRecord({"msg": f"line {number}", "levelno": 20}), f"line {number}")
    assert texts(book) == ["line 2", "line 3", "line 4"]
    assert [line.number for line in book.lines(after=3)] == [4, 5]


def test_a_traceback_is_one_entry_also_when_read_back(started, tmp_path):
    try:
        raise ValueError("bad value")
    except ValueError:
        log.exception("it went wrong")
    assert "\n    Traceback (most recent call last):" in (tmp_path / "paperpi.log").read_text()
    (earlier,) = Logbook(tmp_path).lines()
    assert earlier.earlier
    assert earlier.level == "ERROR"
    assert earlier.source == "paperpi.test"
    assert earlier.text.startswith("it went wrong\nTraceback (most recent call last):\n")
    assert earlier.text.endswith("ValueError: bad value")
    assert earlier.text == started.lines()[-1].text


def test_entries_from_before_the_start_come_first(tmp_path):
    first = Logbook(tmp_path)
    first.add(logging.makeLogRecord({"msg": "x", "levelno": 30, "levelname": "WARNING"}), "old")
    first.close()
    second = Logbook(tmp_path)
    second.add(logging.makeLogRecord({"msg": "x", "levelno": 20, "levelname": "INFO"}), "new")
    assert [(line.text, line.number) for line in second.lines()] == [("old", 0), ("new", 1)]
    # Asking for the new lines after a number leaves the earlier ones out.
    assert texts_after(second, 0) == ["old", "new"]
    assert texts_after(second, 1) == []


def texts_after(book: Logbook, after: int) -> list[str]:
    return [line.text for line in book.lines(after)]


def test_a_full_file_is_replaced_and_the_old_one_kept(tmp_path):
    book = Logbook(tmp_path, file_bytes=200)
    for number in range(20):
        record = logging.makeLogRecord({"levelno": 30, "levelname": "WARNING"})
        book.add(record, f"warning number {number}")
    book.close()
    current, old = tmp_path / "paperpi.log", tmp_path / "paperpi.log.1"
    assert old.exists()
    sizes = [path.stat().st_size for path in (current, old) if path.exists()]
    assert sum(sizes) < 2 * 200 + 100
    read = [line.text for line in logbook.read(current)]
    assert read[-1] == "warning number 19"
    assert read == sorted(read, key=lambda text: int(text.split()[-1]))


def test_lines_that_cant_be_read_are_left_out(tmp_path):
    path = tmp_path / "paperpi.log"
    path.write_text(
        "    a continuation without an entry\n"
        "2026-10-12 14:00:03 WARNING paperpi.scheduler: kept\n"
        "something else\n"
        "2026-10-12 99:00:03 WARNING paperpi.scheduler: wrong time\n"
        "2026-10-12 14:00:04 LOUD paperpi.scheduler: unknown level\n"
    )
    assert [line.text for line in logbook.read(path)] == ["kept"]


def test_a_file_that_cant_be_written_is_reported_once(tmp_path, capsys):
    (tmp_path / "state").write_text("a file, not a folder")
    book = Logbook(tmp_path / "state")
    for _ in range(3):
        book.add(logging.makeLogRecord({"levelno": 40, "levelname": "ERROR"}), "broken")
    assert capsys.readouterr().err.count("can't write the log file") == 1
    assert texts(book) == ["broken"] * 3


def test_a_crash_in_a_thread_is_logged_with_its_traceback(started):
    def crash():
        raise RuntimeError("thread bug")

    thread = threading.Thread(target=crash, name="worker")
    thread.start()
    thread.join()
    (line,) = started.lines()
    assert line.level == "CRITICAL"
    assert line.text.startswith("thread worker crashed\nTraceback")
    assert line.text.endswith("RuntimeError: thread bug")
