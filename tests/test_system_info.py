"""The system_info plugin: reading the Linux files, and turning numbers into text."""

from pathlib import Path

import pytest
from epdlib import ScreenMode

from paperpi.plugin import Context, draw_update
from paperpi.plugins.system_info import (
    PLUGIN,
    Settings,
    disk_text,
    draw,
    readers,
    uptime_text,
)

WIRELESS = """Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   56.  -54.  -256        0      0      0     34      0        0
"""
MEMINFO = "MemTotal:        1000000 kB\nMemFree:          100000 kB\nMemAvailable:     380000 kB\n"


@pytest.fixture
def root(tmp_path):
    """A folder of made-up Linux files, standing for ``/``."""
    files = {
        "proc/net/wireless": WIRELESS,
        "proc/loadavg": "1.44 1.16 0.79 3/236 69781\n",
        "proc/uptime": "87826.25 340915.42\n",
        "proc/meminfo": MEMINFO,
        "sys/class/thermal/thermal_zone0/temp": "51234\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def test_readers(root):
    assert readers.wifi(root) == 80  # 56 of 70
    assert readers.load(root, cores=4) == pytest.approx((36.0, 29.0, 19.75))
    assert readers.uptime(root) == 87826.25
    assert readers.memory(root) == pytest.approx(62.0)
    assert readers.temperature(root) == pytest.approx(51.234)


def test_disk_used_and_free_add_up(tmp_path):
    used, total = readers.disk(tmp_path)
    assert 0 < used <= total


def test_missing_files_give_none(tmp_path):
    assert readers.wifi(tmp_path) is None
    assert readers.load(tmp_path) is None
    assert readers.uptime(tmp_path) is None
    assert readers.memory(tmp_path) is None
    assert readers.temperature(tmp_path) is None
    assert readers.disk(tmp_path / "missing") == (None, None)


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("proc/net/wireless", WIRELESS.splitlines()[0] + "\n"),  # Wi-Fi switched off
        ("proc/loadavg", "garbage\n"),
        ("proc/uptime", ""),
        ("proc/meminfo", "MemTotal: 0 kB\n"),
        ("sys/class/thermal/thermal_zone0/temp", "hot\n"),
    ],
)
def test_broken_files_give_none(root, name, text):
    (root / name).write_text(text)
    read = {
        "proc/net/wireless": readers.wifi,
        "proc/loadavg": readers.load,
        "proc/uptime": readers.uptime,
        "proc/meminfo": readers.memory,
        "sys/class/thermal/thermal_zone0/temp": readers.temperature,
    }[name]
    assert read(root) is None


def test_ip_address_is_found_or_none():
    address = readers.ip_address()
    assert address is None or address.count(".") == 3


@pytest.mark.parametrize(
    ("used", "total", "text"),
    [
        (12_400_000_000, 31_200_000_000, "12 of 31 GB used"),
        (1_500_000_000_000, 2_000_000_000_000, "1.5 of 2.0 TB used"),
        (None, None, "disk ?"),
    ],
)
def test_disk_text(used, total, text):
    assert disk_text(used, total) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (12 * 86400 + 4 * 3600 + 59, "up 12 days 4 h"),
        (86400 + 60, "up 1 day 0 h"),
        (3 * 3600 + 12 * 60, "up 3 h 12 min"),
        (299, "up 4 min"),
        (None, "up ?"),
    ],
)
def test_uptime_text(seconds, text):
    assert uptime_text(seconds) == text


def context(layout, mode=None, **settings):
    return Context(Settings(**settings), 400, 300, mode or ScreenMode.gray(16), Path("."), layout)


def test_unknown_numbers_show_a_question_mark():
    info = PLUGIN.sample.__class__(
        hostname=None,
        ip=None,
        wifi=None,
        disk_used=None,
        disk_total=None,
        temperature=None,
        load=None,
        memory=None,
        uptime=None,
        version="2.0.0",
        time="09:04",
    )
    values = draw(info, context("full")).values
    assert values["hostname"] == "?"
    assert values["ip"] == "no network"
    assert values["wifi"] == ""
    assert values["cpu"] == "? · memory ?"
    assert values["load"] == "load ?"
    portrait = draw(info, context("portrait")).values
    assert portrait["network"] == "no network"
    assert portrait["temp_value"] == "?"


def test_sample_values():
    values = draw(PLUGIN.sample, context("full")).values
    assert values["disk"] == "12 of 31 GB used"
    assert values["cpu"] == "51°C · memory 62%"
    assert values["load"] == "load 12% · 9% · 8%"
    assert values["about"] == "up 12 days 4 h · PaperPi 2.0.0"
    small = draw(PLUGIN.sample, context("small")).values
    assert small == {"hostname": "paperpi", "ip": "192.0.2.10", "temp": "51°C"}


def test_colours_reach_the_pictures(tmp_path):
    ctx = Context(
        Settings(text_color="white", background_color="black"),
        400,
        300,
        ScreenMode.gray(16),
        tmp_path,
        "portrait",
    )
    drawn = draw(PLUGIN.sample, ctx)
    assert drawn.colors == ("white", "black")
    corner = drawn.values["load_bar"].convert("L").getpixel((30, 30))
    assert corner == 0  # the empty part of the bar is the black background
    _, image = draw_update(PLUGIN, ctx, sample=True)
    histogram = image.convert("L").histogram()
    assert histogram[0] > histogram[255]


def test_live_fetch_works_on_this_computer(tmp_path):
    """fetch reads the real files; on any Linux computer it must not fail."""
    fetched = PLUGIN.fetch(Context(Settings(), 400, 300, ScreenMode.bw(), tmp_path, "full"))
    assert fetched.data.version
