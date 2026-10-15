"""A plugin's README as part of a web page (paperpi.web.readme)."""

from paperpi import plugins
from paperpi.web.readme import to_html

TYPES = ["basic_clock", "met_no"]


def test_the_first_heading_and_pictures_are_left_out():
    found = to_html(
        "# basic_clock\n\nShows the time.\n\n![time](../../tests/images/x.png)\n", TYPES
    )
    assert found == "<p>Shows the time.</p>\n"


def test_a_table_of_pictures_and_the_sample_images_section_are_left_out():
    text = (
        "## Layouts\n\n| Layout | Shows |\n|---|---|\n| `time` | the time |\n\n"
        "| time | small |\n|---|---|\n| ![a](a.png) | ![b](b.png) |\n\n"
        "## Sample images\n\nAll sample images are in `tests/images/`.\n\n"
        "## Licence\n\nFree.\n"
    )
    found = to_html(text, TYPES)
    assert found.count("<table>") == 1 and "<td><code>time</code></td>" in found
    assert "Sample images" not in found and "tests/images" not in found
    assert "<h2>Licence</h2>\n<p>Free.</p>" in found


def test_links_to_websites_and_other_readmes_stay_other_links_become_text():
    text = (
        "[go](https://example.com/go), [weather](../met_no/README.md#layouts), "
        "[gone](../gone/README.md), [main](../../../../README.md), [here](#settings), "
        "[`fonts/OFL.txt`](../../fonts/OFL.txt)"
    )
    found = to_html(text, TYPES)
    assert '<a href="https://example.com/go">go</a>' in found
    assert '<a href="/library/met_no/readme">weather</a>' in found
    assert "gone, main, here, <code>fonts/OFL.txt</code>" in found
    assert found.count("<a ") == 2


def test_html_in_a_readme_is_shown_as_text():
    found = to_html("<script>alert(1)</script> and <b>bold</b> [x](javascript:alert(1))", TYPES)
    assert "&lt;script&gt;" in found and "<script" not in found and "<b>" not in found
    assert "href=" not in found  # not a link that runs a script


def test_every_plugins_readme_can_be_shown():
    types = plugins.available()
    for plugin_type in types:
        found = to_html(plugins.readme(plugin_type), types)
        assert "<h2>Layouts</h2>" in found and "<img" not in found, plugin_type
        assert "Sample images" not in found
