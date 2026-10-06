"""Image tests: draw each plugin's sample data and compare with saved reference images.

After an intended change in how a plugin looks (or a new Pillow or epdlib version), update
the references and check them by eye:

    PAPERPI_UPDATE_IMAGES=1 uv run pytest tests/test_images.py

The plugins' READMEs link to these reference images as their sample images.
"""

import base64
import io
import os
from pathlib import Path

import pytest
from epdlib import ScreenMode
from PIL import Image, ImageChops

from paperpi import plugins
from paperpi.plugin import Context, draw_update

REFERENCE = Path(__file__).parent / "images"
UPDATE = os.environ.get("PAPERPI_UPDATE_IMAGES") == "1"
SCREENS = {
    "9in7": (1200, 825, ScreenMode.gray(16)),
    "7in5": (800, 480, ScreenMode.bw()),
    "5in65": (600, 448, ScreenMode.palette()),
}
# Settings to draw besides the defaults, per plugin.
VARIANTS = {
    "basic_clock": {"12h": {"hours": 12}},
    "word_clock": {"colors": {"text_color": "yellow", "background_color": "blue"}},
    "system_info": {"inverse": {"text_color": "white", "background_color": "black"}},
    "met_no": {"berlin-f": {"place": "Berlin", "temperature": "F", "rain": "inch"}},
}
# Share of pixels allowed to differ: font drawing can change slightly between Pillow builds.
TOLERANCE = 0.002


def cases():
    for plugin_type in plugins.available():
        plugin = plugins.load(plugin_type)
        variants = {"": {}} | VARIANTS.get(plugin_type, {})
        for layout in plugin.layouts:
            for variant, settings in variants.items():
                for screen in SCREENS:
                    name = "-".join(filter(None, [plugin_type, layout, variant, screen]))
                    yield pytest.param(plugin_type, layout, settings, screen, id=name)


@pytest.mark.parametrize(("plugin_type", "layout", "settings", "screen"), list(cases()))
def test_sample_matches_reference(plugin_type, layout, settings, screen, tmp_path, request, extras):
    plugin = plugins.load(plugin_type)
    width, height, mode = SCREENS[screen]
    context = Context(plugin.settings(**settings), width, height, mode, tmp_path, layout)
    _, image = draw_update(plugin, context, sample=True)
    path = REFERENCE / f"{request.node.callspec.id}.png"
    if UPDATE or not path.exists():
        image.save(path)
        if not UPDATE:
            pytest.fail(f"no reference image yet; saved {path.name}, check it and run again")
        return
    expected = Image.open(path).convert(image.mode)
    assert expected.size == image.size
    diff = ImageChops.difference(image.convert("RGB"), expected.convert("RGB")).convert("L")
    changed = 1 - diff.histogram()[0] / (width * height)
    if changed > TOLERANCE:
        # Put the new image and the difference in the HTML test report, to look at.
        import pytest_html

        for title, picture in [("new image", image), ("difference", diff)]:
            buffer = io.BytesIO()
            picture.convert("RGB").save(buffer, "PNG")
            data = base64.b64encode(buffer.getvalue()).decode()
            extras.append(pytest_html.extras.png(data, title))
    assert changed <= TOLERANCE, f"{changed:.2%} of pixels differ from {path.name}"
