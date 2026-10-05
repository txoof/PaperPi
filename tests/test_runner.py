"""Each update runs in its own process with a time limit (paperpi.runner)."""

import os
import time

import pytest
from epdlib import ScreenMode

from paperpi.plugin import Context, State
from paperpi.runner import PluginFailed, PluginTimeout, run_update

from .fake_plugins.fake import Settings

FAKES = "tests.fake_plugins"


GRAY16 = ScreenMode.gray(16)


def context(tmp_path, act="ok", mode=GRAY16):
    return Context(Settings(act=act), 200, 100, mode, tmp_path, "one")


def run(tmp_path, act, **options):
    return run_update("fake", context(tmp_path, act), package=FAKES, **options)


def test_ready_returns_the_image(tmp_path):
    result = run(tmp_path, "ok")
    assert result.state is State.READY
    assert result.image.size == (200, 100)
    assert result.image.getextrema() == (0, 255)  # something black was drawn on white


@pytest.mark.parametrize("mode", [ScreenMode.bw(), ScreenMode.gray(4), ScreenMode.palette()])
def test_image_comes_back_in_the_screen_mode(tmp_path, mode):
    result = run_update("fake", context(tmp_path, mode=mode), package=FAKES)
    assert result.image.mode == mode.pil_mode


def test_sample_is_drawn_without_fetching(tmp_path):
    # "raise" would fail if fetch were called.
    result = run(tmp_path, "raise", sample=True)
    assert result.state is State.READY


def test_nothing_has_no_image(tmp_path):
    result = run(tmp_path, "nothing")
    assert result.state is State.NOTHING
    assert result.image is None


def test_alert(tmp_path):
    assert run(tmp_path, "alert").state is State.ALERT


def test_error_in_plugin_is_reported_with_traceback(tmp_path):
    with pytest.raises(PluginFailed, match="ValueError: data source said no") as error:
        run(tmp_path, "raise")
    assert "fetch" in error.value.details


def test_wrong_return_value_is_reported(tmp_path):
    with pytest.raises(PluginFailed, match="use NOTHING, ready"):
        run(tmp_path, "wrong")


def test_sys_exit_in_plugin_is_reported(tmp_path):
    with pytest.raises(PluginFailed, match="SystemExit"):
        run(tmp_path, "exit")


@pytest.mark.parametrize("act", ["crash", "kill"])
def test_crash_is_reported(tmp_path, act):
    with pytest.raises(PluginFailed, match="ended without a result"):
        run(tmp_path, act)


def test_hang_is_stopped_at_the_time_limit(tmp_path):
    start = time.monotonic()
    with pytest.raises(PluginTimeout, match="no result within 1 s"):
        run(tmp_path, "hang", time_limit=1)
    assert time.monotonic() - start < 3


def test_programs_started_by_a_hung_plugin_are_stopped_too(tmp_path):
    with pytest.raises(PluginTimeout):
        run(tmp_path, "child", time_limit=2)
    pid = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not _running(pid):
            break
        time.sleep(0.1)
    assert not _running(pid)


def test_unknown_plugin_is_reported(tmp_path):
    with pytest.raises(PluginFailed, match="KeyError"):
        run_update("missing", context(tmp_path), package=FAKES)


def test_runner_keeps_working_after_failures(tmp_path):
    for act in ["raise", "crash"]:
        with pytest.raises(PluginFailed):
            run(tmp_path, act)
    assert run(tmp_path, "ok").state is State.READY


def test_updates_start_quickly(tmp_path):
    run(tmp_path, "ok")  # the first update also starts the ready copy
    seconds = min(run(tmp_path, "ok").seconds for _ in range(3))
    print(f"one update, including the process start: {seconds:.3f} s")
    assert seconds < 1.5


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A finished child that nobody has collected yet ("zombie") counts as stopped.
    with open(f"/proc/{pid}/stat") as stat:
        return stat.read().split(") ")[1][0] != "Z"
