"""paperpi new-plugin: the template makes a plugin that follows every plugin rule."""

import sys

import pytest
from epdlib import ScreenMode

from paperpi import cli, plugins
from paperpi.newplugin import NewPluginError, new_plugin, title_of
from paperpi.plugin import Context, State, draw_update


@pytest.fixture
def package(tmp_path, monkeypatch):
    """An empty package ``made_plugins`` to make plugins in, like ``paperpi.plugins``."""
    folder = tmp_path / "made_plugins"
    folder.mkdir()
    (folder / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield folder
    for name in [m for m in sys.modules if m.startswith("made_plugins")]:
        del sys.modules[name]


def test_the_made_plugin_loads_and_draws_in_every_layout(package, tmp_path):
    folder = new_plugin("bus_times", package)
    assert sorted(p.name for p in folder.iterdir()) == ["README.md", "__init__.py", "layouts.py"]
    plugin = plugins.load("bus_times", "made_plugins")
    assert plugin.title == "Bus times"
    assert set(plugin.layout_titles) == set(plugin.layouts)
    assert plugins.readme("bus_times", "made_plugins").startswith("# bus_times\n")
    for name, field in plugin.settings.model_fields.items():
        assert field.description, name
    for mode in (ScreenMode.bw(), ScreenMode.gray(16), ScreenMode.palette()):
        for layout in plugin.layouts:
            context = Context(plugin.settings(), 264, 176, mode, tmp_path, layout)
            for sample in (True, False):
                state, image = draw_update(plugin, context, sample=sample)
                assert state is State.READY
                assert image.size == (264, 176)


def test_its_title_can_be_given(package):
    new_plugin("bus_times", package, title="Next buses")
    assert plugins.load("bus_times", "made_plugins").title == "Next buses"


@pytest.mark.parametrize("bad", ["Bus", "1bus", "bus-times", "bus times", ""])
def test_a_wrong_type_is_refused(package, bad):
    with pytest.raises(NewPluginError, match="lowercase"):
        new_plugin(bad, package)


@pytest.mark.parametrize("title", ['A "quoted" title', "x" * 41, " "])
def test_a_wrong_title_is_refused(package, title):
    with pytest.raises(NewPluginError):
        new_plugin("bus_times", package, title=title)
    assert not (package / "bus_times").exists()


def test_an_existing_folder_is_left_alone(package):
    (package / "bus_times").mkdir()
    with pytest.raises(NewPluginError, match="already there"):
        new_plugin("bus_times", package)


def test_title_of():
    assert title_of("bus_times") == "Bus times"
    assert title_of("xkcd") == "Xkcd"


def test_the_command_refuses_a_plugin_that_is_there(capsys):
    assert cli.main(["new-plugin", "basic_clock"]) == 2
    assert "already there" in capsys.readouterr().err
