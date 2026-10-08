"""Rules every plugin that comes with PaperPi must follow."""

from pathlib import Path

import pytest
from epdlib import ScreenMode

from paperpi import plugins
from paperpi.plugin import Context, Drawn, State, draw_update

ALL = plugins.available()
FOLDER = Path(plugins.__file__).parent


@pytest.mark.parametrize("plugin_type", ALL)
def test_plugin_loads_and_describes_itself(plugin_type):
    plugin = plugins.load(plugin_type)
    assert plugin.description
    assert (FOLDER / plugin_type / "README.md").is_file()
    for name, field in plugin.settings.model_fields.items():
        assert field.description, f"setting {name} needs a help text (description)"


@pytest.mark.parametrize("plugin_type", ALL)
@pytest.mark.parametrize("mode", [ScreenMode.bw(), ScreenMode.gray(16), ScreenMode.palette()])
@pytest.mark.parametrize("size", [(1200, 825), (264, 176), (480, 800)])
def test_sample_draws_in_every_layout(plugin_type, mode, size, tmp_path):
    plugin = plugins.load(plugin_type)
    for layout in plugin.layouts:
        context = Context(plugin.settings(), *size, mode, tmp_path, layout)
        state, image = draw_update(plugin, context, sample=True)
        assert state is not State.NOTHING
        assert image.size == size
        assert image.mode == mode.pil_mode


@pytest.mark.parametrize("plugin_type", ALL)
@pytest.mark.parametrize("size", [(1200, 825), (264, 176)], ids=["9in7", "2in7"])
def test_sample_text_is_never_cut(plugin_type, size, tmp_path):
    """In the default layout, no sample text ends in "…" on a large and a small screen.
    Text made smaller by ``shrink`` is fine."""
    plugin = plugins.load(plugin_type)
    layout = plugin.default_layout
    context = Context(plugin.settings(), *size, ScreenMode.gray(16), tmp_path, layout)
    drawn = plugin.draw(plugin.sample, context)
    if not isinstance(drawn, Drawn):
        drawn = Drawn(drawn)
    prepared = plugin.layout(layout, context.settings, drawn.colors).prepare(*size, context.mode)
    cut = [
        name
        for name, block in prepared.layout.blocks.items()
        if block.type == "text" and not prepared.text_fit(name, drawn.values.get(name)).complete
    ]
    assert not cut, f"text cut in {layout}: {', '.join(cut)}"
