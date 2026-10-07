"""The system_info plugin: reading the Linux files, and turning numbers into text."""

from pathlib import Path

import pytest
from epdlib import ScreenMode
from PIL import Image

from paperpi.plugin import Context, draw_update
from paperpi.plugins.system_info import (
    PLUGIN,
    Settings,
    disk_text,
    draw,
    pictures,
    readers,
    uptime_text,
)
from paperpi.plugins.system_info.readers import Info

WIRELESS = """Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   56.  -54.  -256        0      0      0     34      0        0
"""
ROUTE = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask
eth0\t00000000\t0102000C\t0003\t0\t0\t100\t00000000
wlan0\t00000000\t0102000C\t0003\t0\t0\t600\t00000000
eth0\t0002000C\t00000000\t0001\t0\t0\t100\t00FFFFFF
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
        "proc/net/route": ROUTE,
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


def test_wifi_only_for_the_connection_in_use(root):
    assert readers.network_interface(root) == "eth0"  # the cable has the lower metric
    assert readers.wifi(root, interface="eth0") is None
    assert readers.wifi(root, interface="wlan0") == 80
    (root / "proc/net/route").write_text(ROUTE.replace("\t100\t00000000\n", "\t900\t00000000\n", 1))
    assert readers.network_interface(root) == "wlan0"


def test_no_route_no_interface(tmp_path):
    assert readers.network_interface(tmp_path) is None


class FakeSocket:
    def __init__(self, address=None, error=None):
        self.address, self.error = address, error

    def __call__(self, *args):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def connect(self, place):
        if self.error:
            raise self.error

    def getsockname(self):
        return (self.address, 12345)


@pytest.mark.parametrize(
    ("fake", "address"),
    [
        (FakeSocket("192.0.2.10"), "192.0.2.10"),
        (FakeSocket(error=OSError("Network is unreachable")), None),
        (FakeSocket("0.0.0.0"), None),
    ],
)
def test_ip_address(monkeypatch, fake, address):
    monkeypatch.setattr(readers.socket, "socket", fake)
    assert readers.ip_address() == address


def test_memory_without_available(root):
    (root / "proc/meminfo").write_text("MemTotal: 1000 kB\nMemFree: 10 kB\n")
    assert readers.memory(root) is None


@pytest.mark.parametrize(
    ("share", "upright", "dark_at"),
    [
        (0.5, True, (200, 1500)),
        (0.5, False, (100, 200)),
        (None, True, None),
        (2.0, True, (200, 20)),
    ],
)
def test_bars(share, upright, dark_at):
    width, height = (400, 1600) if upright else (1600, 400)
    image = pictures.bar(share, width, height, "black", "white", upright=upright).convert("L")
    middle_top = image.getpixel((image.width // 2, image.height // 4))
    if dark_at:
        assert image.getpixel(dark_at) == 0
    if share is None:
        assert middle_top == 255  # an empty outline


@pytest.mark.parametrize("layout", ["full", "portrait"])
def test_pictures_have_their_blocks_exact_size(layout):
    """Bars and icons are drawn at their block's size, so the layout never resizes them."""
    ctx = context(layout)
    prepared = PLUGIN.layout(layout, ctx.settings).prepare(ctx.width, ctx.height, ctx.mode)
    pictures_drawn = {
        name: value
        for name, value in draw(PLUGIN.sample, ctx).values.items()
        if isinstance(value, Image.Image)
    }
    assert pictures_drawn
    for name, picture in pictures_drawn.items():
        width, height = prepared.content_size(name)
        if name.endswith("_icon"):
            assert picture.size == (min(width, height),) * 2
        else:
            assert picture.size == (width, height)


@pytest.mark.parametrize("draw_icon", [pictures.disk_icon, pictures.chip_icon])
@pytest.mark.parametrize("side", [1, 7, 240])
def test_icons_at_any_size(draw_icon, side):
    icon = draw_icon(side, "black", "white")
    assert icon.size == (side, side)
    if side > 1:
        assert icon.convert("L").getextrema() == (0, 255)


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
    info = Info(
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
    info = PLUGIN.fetch(Context(Settings(), 400, 300, ScreenMode.bw(), tmp_path, "full")).data
    assert info.version
    # These exist on every Linux computer, including GitHub's test machines. Wi-Fi and the
    # temperature may be missing there.
    assert info.hostname
    assert info.load is not None
    assert info.memory is not None
    assert info.uptime > 0
    assert 0 < info.disk_used <= info.disk_total
