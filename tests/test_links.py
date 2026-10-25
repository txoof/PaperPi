"""Links in setting help texts (paperpi.links): shown as links on the settings page, as plain
text in the config file and the other plain-text places."""

from fastapi.testclient import TestClient

from paperpi import config, example, links
from paperpi.plugins.nl_openbaar_vervoer import PLUGIN
from paperpi.web import auth
from paperpi.web.app import create_app
from paperpi.web.plugins import PluginEditor

from .test_web_settings import PI

ID = "nl_openbaar_vervoer-6e1f3b92"
CONFIG = f"""\
config_version = 1

[display]
type = "virtual"

[[plugin]]
id = "{ID}"
type = "nl_openbaar_vervoer"
stop_1 = "31001118"
"""


def test_links_become_their_text_or_parts():
    text = "See the [README](readme) or [NS](https://apiportal.ns.nl), [not a link](ftp://x)"
    assert links.plain(text) == "See the README or NS, [not a link](ftp://x)"
    assert links.parts(text, "/library/x/readme") == (
        ("See the ", ""),
        ("README", "/library/x/readme"),
        (" or ", ""),
        ("NS", "https://apiportal.ns.nl"),
        (", [not a link](ftp://x)", ""),
    )
    assert links.parts("no links", "/r") == (("no links", ""),)


def test_the_config_file_shows_only_the_text():
    block = example.plugin_block(PLUGIN, ID)
    text = " ".join(line.removeprefix("# ") for line in block.splitlines())
    assert "NS API key needed for trains. See the README for information on obtaining" in text
    assert "](readme)" not in block


def test_the_settings_page_links_to_the_readme(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    editor = PluginEditor(path)
    editor.loaded(path.read_text())
    app = create_app(auth.Auth(path, config.WebSettings(login=False)), editor)
    page = TestClient(app, base_url=PI).get("/plugins/0/settings", params={"id": ID}).text
    assert (
        'NS API key needed for trains. See the <a href="/library/nl_openbaar_vervoer/readme">'
        "README</a> for information on obtaining a free key" in page
    )
    assert "](readme)" not in page
