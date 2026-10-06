"""Unit tests for the test tools, using the fake candidate (no hardware needed)."""

import csv

import pytest

from it8951bench import images, pins
from it8951bench.run import Recorder, run_child

GPIOINFO = """gpiochip0 - 58 lines:
\tline   2:\t"GPIO2"         \tinput consumer="kernel"
\tline   8:\t"GPIO8"         \toutput active-low consumer="spi0 CS0"
\tline  17:\t"GPIO17"        \toutput consumer="it8951"
\tline  18:\t"GPIO18"        \tinput consumer="kernel"
\tline  24:\t"GPIO24"        \tinput consumer="it8951"
\tline  25:\t"GPIO25"        \tinput
"""

OPTS = {"vcom": -1.5, "repeat": 1, "image": "gray", "mode": "GC16"}


@pytest.fixture(autouse=True)
def no_gpio(monkeypatch):
    monkeypatch.setenv("IT8951BENCH_NO_GPIO", "1")


def test_parse_gpioinfo_finds_lines_in_use():
    used = pins.parse_gpioinfo(GPIOINFO)
    assert used == {2: "kernel", 8: "spi0 CS0", 17: "it8951", 18: "kernel", 24: "it8951"}


def test_pin_check_allows_reset_and_busy_only():
    before = {2: "kernel", 8: "spi0 CS0", 18: "kernel"}
    ok, _ = pins.check(before, {**before, 17: "x", 24: "x"})
    assert ok
    ok, detail = pins.check(before, {**before, 17: "x", 25: "x"})
    assert not ok
    assert "25" in detail


def test_pins_released_check():
    before = {2: "kernel"}
    assert pins.check_released(before, before)[0]
    assert not pins.check_released(before, {2: "kernel", 17: "x"})[0]


def test_images_have_the_right_size_and_mode():
    for make in (images.gray_steps, images.fine_text, images.gradient, images.blank):
        img = make(1200, 825)
        assert img.size == (1200, 825)
        assert img.mode == "L"
    assert images.clock().size == images.CLOCK_SIZE


def test_gray_steps_uses_all_16_levels():
    img = images.gray_steps(1600, 100)
    levels = {img.getpixel((round((i + 0.1) * 100), 5)) for i in range(16)}
    assert levels == {i * 17 for i in range(16)}


def test_black_white_has_only_two_values():
    bw = images.to_black_white(images.gradient(200, 100))
    assert len(bw.histogram()) == 256 and sum(bw.histogram()[1:255]) == 0


def test_basic_scenario_runs_on_fake_and_writes_csv(tmp_path):
    path = tmp_path / "out.csv"
    rec = Recorder(path, "fake", echo=False)
    assert run_child("fake", "basic", OPTS, rec, limit=60)
    steps = [r["step"] for r in rec.rows]
    assert "open" in steps and "pin check" in steps and "pins released" in steps
    assert all(r["ok"] for r in rec.rows), [r for r in rec.rows if not r["ok"]]
    with path.open() as f:
        assert len(list(csv.DictReader(f))) == len(rec.rows)


def test_hanging_candidate_is_killed(monkeypatch):
    monkeypatch.setenv("FAKE_HANG", "1")
    rec = Recorder(None, "fake", echo=False)
    assert not run_child("fake", "basic", OPTS, rec, limit=5)
    assert rec.rows[-1]["step"] == "hung"


def test_pack_4bpp_puts_first_pixel_in_high_half():
    from PIL import Image

    from it8951bench.new import pack_4bpp

    img = Image.frombytes("L", (4, 1), bytes([0x00, 0xFF, 0x80, 0x10]))
    assert pack_4bpp(img) == bytes([0x0F, 0x81])


def test_new_driver_refuses_bad_vcom():
    from it8951bench.new import New

    with pytest.raises(ValueError):
        New().open(1.9)


def test_endurance_pattern():
    from it8951bench.endurance import kind_of

    kinds = [kind_of(n) for n in range(1, 21)]
    assert kinds[:10] == ["fast"] * 4 + ["full"] + ["fast"] * 4 + ["fault"]
    assert kinds.count("fault") == 2


def test_endurance_runs_briefly_on_fake(tmp_path, monkeypatch):
    from it8951bench import endurance, fault

    monkeypatch.setattr(fault, "hold_reset_low", lambda: None)
    monkeypatch.setattr(fault, "release_reset", lambda: None)
    monkeypatch.setattr(endurance, "RESULTS_DIR", tmp_path)
    assert (
        endurance.main(["fake", "--vcom", "-1.5", "--hours", "0.0003", "--interval", "0.05"]) == 0
    )
    (out,) = tmp_path.glob("endurance-fake-*.csv")
    rows = list(csv.DictReader(out.open()))
    assert rows[-1]["kind"] == "end"
    assert int(rows[0]["open_files"]) > 0
