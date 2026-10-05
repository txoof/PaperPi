"""The debugging and default plugins, run in plugin processes as the scheduler runs them."""

from dataclasses import replace

import pytest
from epdlib import ScreenMode

from paperpi import plugins
from paperpi.plugin import Context, PluginsStatus, State, draw_update
from paperpi.plugins.default import message
from paperpi.runner import PluginFailed, PluginTimeout, run_update

DEBUGGING = plugins.load("debugging")


def update(tmp_path, time_limit=10, **settings):
    context = Context(
        DEBUGGING.settings(**settings), 200, 100, ScreenMode.gray(16), tmp_path, "text_state"
    )
    return run_update("debugging", context, time_limit=time_limit)


def test_states_follow_the_pattern_and_start_over(tmp_path):
    pattern = ("nothing", "ready", "alert")
    states = [update(tmp_path, states=pattern).state for _ in range(5)]
    assert states == [State.NOTHING, State.READY, State.ALERT, State.NOTHING, State.READY]
    assert (tmp_path / "count").read_text() == "5"


def test_same_state_gives_the_same_image(tmp_path):
    first, second = update(tmp_path), update(tmp_path)
    assert first.image.tobytes() == second.image.tobytes()


def test_crash_every(tmp_path):
    outcomes = []
    for _ in range(4):
        try:
            outcomes.append(update(tmp_path, crash_every=2).state)
        except PluginFailed as error:
            assert "update 2: crash" in str(error) or "update 4: crash" in str(error)
            outcomes.append("crash")
    assert outcomes == [State.READY, "crash", State.READY, "crash"]


def test_hang_every_is_stopped_by_the_time_limit(tmp_path):
    update(tmp_path, hang_every=2, time_limit=2)
    with pytest.raises(PluginTimeout):
        update(tmp_path, hang_every=2, time_limit=1)
    assert update(tmp_path, hang_every=2).state is State.READY  # the count went on


def test_delay(tmp_path):
    assert update(tmp_path, delay=0.5).seconds >= 0.5


@pytest.mark.parametrize(
    ("failing", "total", "text"),
    [
        (3, 4, "3 of 4 plugins are not working."),
        (1, 1, "1 of 1 plugin is not working."),
        (0, 0, "No plugins are switched on."),
    ],
)
def test_default_message(failing, total, text):
    assert message(PluginsStatus(failing, total)) == text


def test_default_gets_the_status_in_its_process(tmp_path):
    plugin = plugins.load("default")
    context = Context(
        plugin.settings(), 300, 200, ScreenMode.bw(), tmp_path, "message", PluginsStatus(2, 5)
    )
    result = run_update("default", context)
    assert result.state is State.READY
    # The same picture as drawn here for "2 of 5", and not the one for another count.
    _, expected = draw_update(plugin, context, sample=False)
    _, other = draw_update(plugin, replace(context, status=PluginsStatus(0, 0)), sample=False)
    assert result.image.tobytes() == expected.tobytes() != other.tobytes()
