"""Pages of the manual website made from the code (paperpi.manual).

The docs workflow builds the whole site with ``mkdocs build --strict``, which checks every
link; these tests check what the pages say.
"""

import re
from pathlib import Path

import pytest
from epdlib.drivers import it8951, waveshare

from paperpi import manual, plugins
from paperpi.config import DisplaySettings, WebSettings
from paperpi.example import suggested
from paperpi.plugin import PluginEntry

ROOT = Path(__file__).parent.parent
TYPES = plugins.available()
#: The first cells of the tables' header rows.
HEADERS = ("| Setting ", "| Name ", "| `model =`", "| | ")


def rows(text: str) -> list[list[str]]:
    """The cells of each table row in ``text``, without the header lines."""
    found = []
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith(HEADERS):
            found.append([cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]])
    return found


def test_the_settings_page_has_every_setting():
    page = manual.settings_page()
    for fields in (DisplaySettings.model_fields, WebSettings.model_fields):
        keys = [row[0] for row in rows(manual.settings_table(fields))]
        assert keys == [f"`{key}`" for key in fields]
        for key in keys:
            assert f"| {key} |" in page, key
    for key in PluginEntry.model_fields:
        assert f"| `{key}` |" in page, key


def test_a_settings_table_shows_defaults_required_and_choices():
    table = manual.settings_table(DisplaySettings.model_fields)
    cells = {row[0]: row[1:] for row in rows(table)}
    assert cells["`type`"][0] == "required"
    assert cells["`rotation`"] == ["`0`", "Turn the picture, in degrees. One of: 0, 90, 180, 270"]
    assert cells["`width`"][0] == "not set"


def test_a_secret_default_is_never_shown():
    plugin = plugins.load("nl_openbaar_vervoer")
    table = manual.settings_table(plugin.settings.model_fields)
    ns_key = next(row for row in rows(table) if row[0] == "`ns_key`")
    assert ns_key[1] == "not set"
    # "See the [README](readme)": on the plugin's own page, the README is the page itself.
    assert "[README](readme)" not in table and "See the README" in table


def test_config_file_wording_reads_right_on_the_site():
    page = manual.settings_page()
    assert "(shown below)" not in page and '"Layouts" above' not in page


@pytest.mark.parametrize("plugin_type", TYPES)
def test_every_plugin_page_has_its_settings_and_working_pictures(plugin_type):
    page, used = manual.plugin_page(plugin_type, TYPES, ROOT)
    plugin = plugins.load(plugin_type)
    assert page.startswith(f"# {plugin.shown_title}\n\nType `{plugin_type}` · needs ")
    assert "## All settings" in page
    for key in plugin.settings.model_fields:
        assert f"| `{key}` |" in page, key
    pictures = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", page)
    assert pictures, "no sample pictures"
    for picture in pictures:
        if picture.startswith("../images/"):  # one of the manual's own pictures
            assert (ROOT / "docs" / picture.removeprefix("../")).is_file(), picture
            continue
        assert picture.startswith(manual.FILES), picture
        assert picture.removeprefix(manual.FILES) in used
    for path in used:
        assert (ROOT / path).is_file(), path
    # Relative links left from the README would point nowhere on the site.
    for target in re.findall(r"\]\(([^)\s]+)\)", page):
        assert re.match(r"(https?:|mailto:|#|\.\./|files/|\w+\.md)", target), target


def test_readme_links_become_links_that_work_on_the_site():
    here = "src/paperpi/plugins/met_no/"
    used = set()

    def target(link):
        return manual._site_target(link, here, set(TYPES), ROOT, used)

    assert target("../basic_clock/README.md#layouts") == "basic_clock.md#layouts"
    assert target("../../../../docs/install-systemd.md") == "../install-systemd.md"
    assert target("../../../../README.md") == "../index.md"
    assert target("../../fonts/Lato-OFL.txt") == (
        "https://github.com/txoof/PaperPi/blob/main/src/paperpi/fonts/Lato-OFL.txt"
    )
    assert target("../../../../tests/images/") == (
        "https://github.com/txoof/PaperPi/tree/main/tests/images"
    )
    picture = "tests/images/met_no-now-berlin-9in7.png"
    assert target(f"../../../../{picture}") == f"files/{picture}"
    assert used == {picture}
    assert target("https://api.met.no/") == "https://api.met.no/"
    assert target("#wind-barbs") == "#wind-barbs"


def test_the_plugins_page_lists_the_plugin_library_with_a_picture_each():
    page, used = manual.plugins_page(TYPES, ROOT)
    listed = [t for t in TYPES if t not in manual.OWN]
    assert len(rows(page)) == len(listed)
    for plugin_type in listed:
        assert f"{{ width=200 }}]({plugin_type}.md)" in page, plugin_type
    assert len(used) == len(listed)


def test_full_addresses_of_manual_pages_become_links_between_pages():
    pages = ["index.md", "settings.md", "plugins/index.md", "plugins/met_no.md"]
    text = (
        f"[a]({manual.SITE}settings/#web) [b]({manual.SITE}) [c]({manual.SITE}plugins/) "
        f"[d]({manual.SITE}gone/) [e](https://example.com/)"
    )
    assert manual.site_links(text, "plugins/met_no.md", pages) == (
        "[a](../settings.md#web) [b](../index.md) [c](index.md) [d](../gone.md) "
        "[e](https://example.com/)"
    )


def test_the_screens_page_lists_every_model_epdlib_has():
    page = manual.fill_screens((ROOT / "docs" / "screens.md").read_text())
    assert "<!-- made from epdlib" not in page
    it_rows = [r for r in rows(page) if r[0].startswith('`"')]
    assert [r[0].strip('`"') for r in it_rows] == list(it8951.MODELS)
    ws = {r[1].strip("`"): r for r in rows(page) if r[1].startswith("`epd")}
    assert set(ws) == set(waveshare.MODELS)
    for name, info in waveshare.MODELS.items():
        assert ws[name][5] == ("yes" if info.tested else "no"), name
        assert ws[name][2] == f"{info.width} × {info.height}", name


def test_a_missing_place_for_a_table_stops_the_build():
    with pytest.raises(ValueError, match="not working"):
        manual.fill_screens("<!-- made from epdlib: it8951 models -->")


def test_waveshare_models_are_listed_tested_first_then_by_size():
    names = [name for name, _ in manual.waveshare_models()]
    tested = [n for n, info in waveshare.MODELS.items() if info.tested]
    assert set(names[: len(tested)]) == set(tested)
    assert names.index("epd1in02") < names.index("epd2in13") < names.index("epd13in3k")


def test_every_screen_that_takes_two_layers_is_named_a_three_colour_screen():
    # epdlib's private table says which Waveshare files take a black and a red layer.
    for name in waveshare.MODELS:
        if waveshare._CALLS[name].layers == 2:
            assert manual._three_colour(name), name
    assert not manual._three_colour("epd7in5_V2") and manual._three_colour("epd7in5b_HD")


def test_shared_settings_with_a_plugin_suggestion_say_so():
    assert set(manual._SUGGESTED) == set(suggested(plugins.load("met_no")))
    refresh = next(row for row in rows(manual.settings_page()) if row[0] == "`refresh`")
    assert refresh[1] == "the plugin's suggestion"


def test_the_menu_and_the_list_of_plugins_use_the_same_order():
    order = manual.listed(TYPES)
    page, _ = manual.plugins_page(TYPES, ROOT)
    assert [re.search(r"\]\((\w+)\.md\)", row[1])[1] for row in rows(page)] == order
    titles = [plugins.load(t).shown_title.lower() for t in order]
    assert titles == sorted(titles) and not set(order) & set(manual.OWN)


def test_a_picture_before_the_first_section_is_the_plugins_preview():
    page, _ = manual.plugin_page("lms_client", TYPES, ROOT)
    intro, _, sections = page.partition("\n## ")
    assert intro.count("{ .preview }") == 1 and "{ .preview }" not in sections
    assert ".." not in intro.splitlines()[2]
