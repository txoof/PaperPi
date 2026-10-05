"""Each update runs in its own process with a time limit (paperpi.runner)."""

import os
import signal
import time

import pytest
from epdlib import ScreenMode
from pydantic import SecretStr

from paperpi.plugin import Context, PluginSettings, State
from paperpi.runner import PluginFailed, PluginTimeout, run_update

from .fake_plugins.fake import Settings

FAKES = "tests.fake_plugins"
GRAY16 = ScreenMode.gray(16)


@pytest.fixture(scope="module", autouse=True)
def ready_copy(tmp_path_factory):
    """Start the ready copy once, so its start-up time doesn't count in the timing tests."""
    run_update("fake", context(tmp_path_factory.mktemp("warm-up")), package=FAKES)


def context(tmp_path, act="ok", mode=GRAY16, **settings):
    return Context(Settings(act=act, **settings), 200, 100, mode, tmp_path, "one")


def run(tmp_path, act, **options):
    return run_update("fake", context(tmp_path, act), package=FAKES, **options)


def test_ready_returns_the_image(tmp_path):
    result = run(tmp_path, "ok")
    assert result.state is State.READY
    assert result.image.size == (200, 100)
    assert result.image.getextrema() == (0, 255)  # something black was drawn on white
    assert_stopped(_pid(tmp_path, "plugin.pid"))


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


def test_secret_settings_are_hidden_in_errors(tmp_path):
    secret = "sk-123456789"
    with pytest.raises(PluginFailed) as error:
        run_update("fake", context(tmp_path, "secret", key=SecretStr(secret)), package=FAKES)
    assert error.value.reason == "ValueError: server refused key ****"
    assert secret not in error.value.details
    assert secret not in str(error.value)


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
    assert time.monotonic() - start < 5
    assert_stopped(_pid(tmp_path, "plugin.pid"))


def test_hang_while_loading_the_plugin_is_stopped(tmp_path, caplog):
    bare = Context(PluginSettings(), 200, 100, GRAY16, tmp_path, "one")
    with pytest.raises(PluginTimeout):
        run_update("slow_import", bare, package=FAKES, time_limit=1)
    assert "did not stop" not in caplog.text


def test_time_limit_before_the_process_is_ready(tmp_path, caplog):
    # So short that it runs out before the child has made its own process group.
    with pytest.raises(PluginFailed):
        run(tmp_path, "hang", time_limit=0.001)
    assert "did not stop" not in caplog.text


@pytest.mark.parametrize(("act", "error"), [("child", PluginTimeout), ("leave_child", None)])
def test_programs_started_by_the_plugin_are_stopped(tmp_path, act, error):
    try:
        if error:
            with pytest.raises(error):
                run(tmp_path, act, time_limit=3)
        else:
            assert run(tmp_path, act).state is State.READY
        assert_stopped(_pid(tmp_path, "child.pid"))
    finally:
        _kill(tmp_path / "child.pid")


def test_unknown_plugin_is_reported(tmp_path):
    with pytest.raises(PluginFailed, match="KeyError"):
        run_update("missing", context(tmp_path), package=FAKES)


def test_runner_keeps_working_after_failures(tmp_path):
    for act in ["raise", "crash"]:
        with pytest.raises(PluginFailed):
            run(tmp_path, act)
    assert run(tmp_path, "ok").state is State.READY


def test_updates_start_quickly(tmp_path):
    seconds = min(run(tmp_path, "ok").seconds for _ in range(3))
    print(f"one update, including the process start: {seconds:.3f} s")
    assert seconds < 2.5


def assert_stopped(pid: int) -> None:
    for _ in range(50):
        if not _running(pid):
            return
        time.sleep(0.1)
    raise AssertionError(f"process {pid} is still running")


def _pid(folder, name: str) -> int:
    path = folder / name
    for _ in range(50):  # the plugin may be slow to write it on a busy Pi
        if path.exists() and path.read_text():
            return int(path.read_text())
        time.sleep(0.1)
    raise AssertionError(f"the plugin did not write {name}")


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        with open(f"/proc/{pid}/stat") as stat:
            # A finished process that nobody has collected yet ("zombie") counts as stopped.
            return stat.read().split(") ")[1][0] != "Z"
    except (ProcessLookupError, FileNotFoundError):
        return False


def _kill(pid_file) -> None:
    """Clean up after a failed test, so no `sleep 3600` is left behind."""
    try:
        os.kill(int(pid_file.read_text()), signal.SIGKILL)
    except (FileNotFoundError, ValueError, ProcessLookupError):
        pass
