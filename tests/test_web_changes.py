"""The Review changes page (paperpi.web.changes, /changes in paperpi.web.app)."""

from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from paperpi import config, limits
from paperpi.scheduler import Summary
from paperpi.web import auth, changes
from paperpi.web.app import create_app
from paperpi.web.plugins import PluginEditor

CONFIG = """\
config_version = 1
[display]
type = "virtual"

[web]
password_hash = "old"

[[plugin]]
id = "clock"
name = "Clock"
type = "basic_clock"

[[plugin]]
id = "music"
type = "lms_client"
player_name = "Kitchen"
password = "one"

[[plugin]]
id = "old"
type = "basic_clock"
"""
PI = "http://192.168.1.20:8080"


def edited(*pairs: tuple[str, str]) -> str:
    text = CONFIG
    for old, new in pairs:
        assert old in text
        text = text.replace(old, new)
    return text


def groups(new: str, old: str = CONFIG) -> dict[str, changes.Group]:
    found = changes.review(old, new).groups
    return {g.title: g for g in found}


@pytest.mark.parametrize(
    ("new", "waiting"),
    [
        (CONFIG, False),
        (CONFIG + "\n# only a comment\n", False),
        (edited(('name = "Clock"', 'name   =   "Clock"  # same')), False),
        (edited(('name = "Clock"', 'name = "Big clock"')), True),
        (CONFIG + "\n[display\n", True),  # not valid TOML: the page names the mistake
    ],
)
def test_only_changed_settings_are_hand_edits(new, waiting):
    assert changes.waiting(CONFIG, new) is waiting


def test_a_changed_screen_setting_with_its_default_and_a_next_start_note():
    found = groups(edited(('type = "virtual"', 'type = "virtual"\nmode = "bw"\nclean_every = 0')))
    assert list(found) == ["Screen"]
    mode, clean = found["Screen"].changes
    assert (mode.key, mode.old, mode.new) == ("mode", None, '"bw"')
    assert mode.note == changes.NEXT_START_NOTE
    assert (clean.key, clean.old, clean.new, clean.default, clean.note) == (
        "clean_every",
        None,
        "0",
        "3600",
        "",
    )


def test_secrets_are_not_shown():
    found = groups(edited(('"old"\n', '"new"\n'), ('password = "one"', 'password = "two"')))
    (web,) = found["Web interface"].changes
    assert (web.key, web.old, web.new) == ("password_hash", changes.HIDDEN, changes.HIDDEN)
    assert "log in with the new one" in web.note
    (music,) = found["music"].changes
    assert (music.key, music.old, music.new) == ("password", changes.HIDDEN, changes.HIDDEN)


def test_a_secret_stays_hidden_when_the_type_changes():
    found = groups(
        edited(('"lms_client"', '"lms_clientt"'), ('password = "one"', 'password = "two"'))
    )
    music = {c.key: c for c in found["music"].changes}
    assert (music["type"].old, music["type"].new) == ('"lms_client"', '"lms_clientt"')
    assert (music["password"].old, music["password"].new) == (changes.HIDDEN, changes.HIDDEN)
    # A type that is not known: only the shared settings are shown.
    unknown = CONFIG + '\n[[plugin]]\nid = "x"\ntype = "nothing"\napi_key = "abc"\nrefresh = 5\n'
    added = {c.key: c.new for c in groups(unknown)["x"].changes}
    assert added == {"api_key": changes.HIDDEN, "refresh": "5"}


def test_an_id_written_another_way_is_the_same_plugin():
    found = groups(edited(('id = "clock"', 'id = "CLOCK"')))
    (change,) = found["Clock"].changes
    assert (change.key, change.old, change.new, change.note) == ("id", '"clock"', '"CLOCK"', "")


@pytest.mark.parametrize(
    ("before", "after", "moved"),
    [
        ("abc", "cab", {"c"}),
        ("abc", "bca", {"a"}),
        ("abcd", "abdc", {"c"}),  # c or d: both change their place
        ("aDbc", "abDc", set()),  # D is a default block: it takes no place
        ("abc", "bc", set()),  # removed: the others are pushed along
    ],
)
def test_only_plugins_that_moved_among_the_others_are_moved(before, after, moved):
    def text(order):
        blocks = [
            f'[[plugin]]\nid = "{n}"\ntype = "{"default" if n == "D" else "basic_clock"}"\n'
            for n in order
        ]
        return "config_version = 1\n" + "\n".join(blocks)

    found = changes.compare(changes._toml(text(before)), changes._toml(text(after)))
    assert {g.title for g in found if g.note.startswith("Moves")} == moved


def test_blocks_without_an_id_or_with_the_same_id_and_tables_inside_blocks():
    old = 'config_version = 1\n[[plugin]]\ntype = "basic_clock"\n'
    old += '[[plugin]]\nid = "a"\ntype = "basic_clock"\n'
    old += '[[plugin]]\nid = "a"\ntype = "basic_clock"\n[plugin.layout_settings]\nsize = 1\n'
    new = old.replace("size = 1", "size = 2").replace(
        'type = "basic_clock"\n[[plugin]]', 'type = "basic_clock"\nrefresh = 9\n[[plugin]]', 1
    )
    found = changes.compare(changes._toml(old), changes._toml(new))
    assert [(g.title, [(c.key, c.old, c.new) for c in g.changes]) for g in found] == [
        ("A plugin without an ID", [("refresh", None, "9")]),
        ("a", [("layout_settings.size", "1", "2")]),  # the second "a", matched by its place
    ]


def test_dates_are_shown_as_written():
    found = groups(CONFIG.replace("config_version = 1", "config_version = 1\nsince = 1979-05-27"))
    (change,) = found["Other settings"].changes
    assert change.new == "1979-05-27"


def test_a_changed_plugin_links_to_its_settings_page():
    found = groups(edited(('name = "Clock"', 'name = "Clock"\nenabled = false\nrefresh = 30')))
    clock = found["Clock"]
    assert (clock.index, clock.plugin_id, clock.status, clock.kind) == (
        0,
        "clock",
        "",
        "basic_clock",
    )
    assert [(c.key, c.old, c.new, c.default) for c in clock.changes] == [
        ("enabled", None, "false", "true"),
        ("refresh", None, "30", "60"),  # the plugin's own suggestion
    ]


def test_added_removed_and_moved_plugins():
    clock = '[[plugin]]\nid = "clock"\nname = "Clock"\ntype = "basic_clock"\n'
    old = '[[plugin]]\nid = "old"\ntype = "basic_clock"\n'
    new = edited((clock, '[[plugin]]\nid = "new"\ntype = "basic_clock"\n'), (old, clock))
    found = changes.review(CONFIG, new).groups
    assert [(g.title, g.status) for g in found] == [
        ("new", "added"),
        ("Clock", ""),
        ("old", "removed"),
    ]
    added, moved, removed = found
    assert added.note.startswith("Joins the order at place 1 (where it is in the file).")
    assert "empty storage folder" in added.note
    assert added.changes == ()  # only its ID and type
    assert moved.note == "Moves to place 3 in the order." and moved.changes == ()
    assert "storage folder is kept" in removed.note and removed.index is None


def test_an_added_plugin_shows_its_settings_without_old_values():
    new = CONFIG + '\n[[plugin]]\nid = "x"\ntype = "basic_clock"\nenabled = false\n'
    added = groups(new)["x"]
    assert added.note.startswith("Switched off.")
    assert [(c.key, c.old, c.new) for c in added.changes] == [("enabled", None, "false")]


def test_long_values_are_cut_short_and_other_parts_are_listed():
    new = CONFIG.replace("config_version = 1", f'config_version = 1\nextra = "{"a" * 200}"')
    (change,) = groups(new)["Other settings"].changes
    assert change.key == "extra" and len(change.new) == changes.LONGEST_VALUE
    assert change.new.endswith("…")


def test_a_file_that_cant_be_used_has_mistakes_and_no_changes():
    found = changes.review(CONFIG, CONFIG + "\n[display\n")
    assert found.groups == ()
    assert len(found.mistakes) == 1 and "not valid TOML" in found.mistakes[0]


def test_a_plugin_block_with_an_error_is_a_problem_but_can_be_applied():
    found = changes.review(CONFIG, edited(('name = "Clock"', 'name = "Clock"\nrefresh = "often"')))
    assert found.mistakes == ()
    assert len(found.problems) == 1 and "refresh" in found.problems[0]
    assert [g.title for g in found.groups] == ["Clock"]


# The page


@dataclass
class FakeScheduler:
    editor: PluginEditor
    summary: Summary = field(default_factory=Summary)
    reloads: int = 0
    loads: bool = True
    """A reload loads the file at once (else it is busy for longer)."""

    def reload(self):
        self.reloads += 1
        if self.loads:
            self.editor.loaded(self.editor.path.read_text())


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def setup(cfg):
    editor = PluginEditor(cfg)
    editor.loaded(CONFIG)
    scheduler = FakeScheduler(editor)
    app = create_app(auth.Auth(cfg, config.WebSettings(login=False)), editor, controls=scheduler)
    return TestClient(app, follow_redirects=False, base_url=PI), scheduler


def test_no_bar_and_nothing_to_review_without_hand_edits(setup):
    client, _ = setup
    assert "edits-bar" not in client.get("/").text
    page = client.get("/changes").text
    assert "No hand edits are waiting" in page and "Apply changes" not in page


def test_hand_edits_show_the_bar_on_every_page_but_the_review_page(setup, cfg):
    client, _ = setup
    cfg.write_text(edited(('name = "Clock"', 'name = "Big clock"')))
    for address in ("/", "/library", "/warnings", "/plugins/0/settings?id=clock"):
        assert 'href="/changes">Review changes</a>' in client.get(address).text, address
    page = client.get("/changes").text
    assert "edits-bar" not in page
    assert "<h2>Big clock</h2>" in page and "&#34;Clock&#34;" in page
    assert 'href="/plugins/0/settings?id=clock">Edit</a>' in page
    assert "kill -HUP" in page and "is this PaperPi's process ID" in page


def test_a_change_saved_in_the_web_interface_is_no_hand_edit(setup, cfg):
    client, scheduler = setup
    scheduler.loads = False  # the moment before PaperPi has loaded the saved file
    response = client.post("/plugins/0/enabled", data={"id": "clock", "on": "0"})
    assert response.status_code == 303
    assert cfg.read_text() != CONFIG
    assert "edits-bar" not in client.get("/").text


def test_apply_loads_the_file_again(setup, cfg):
    client, scheduler = setup
    cfg.write_text(edited(('name = "Clock"', 'name = "Big clock"')))
    response = client.post("/changes/apply")
    assert scheduler.reloads == 1
    assert response.headers["location"] == "/changes?done=applied"
    page = client.get(response.headers["location"]).text
    assert "Applied. PaperPi uses the changed config file now." in page
    assert "No hand edits" not in page
    assert "edits-bar" not in client.get("/").text


def test_apply_says_when_paperpi_is_still_busy(setup, cfg, monkeypatch):
    client, scheduler = setup
    monkeypatch.setattr(limits, "APPLY_WAIT", 0.0)
    scheduler.loads = False
    cfg.write_text(edited(('name = "Clock"', 'name = "Big clock"')))
    response = client.post("/changes/apply")
    assert response.headers["location"] == "/changes?done=applying"
    assert "between two screen writes" in client.get(response.headers["location"]).text


def test_a_mistake_in_the_file_turns_apply_off(setup, cfg):
    client, scheduler = setup
    cfg.write_text(CONFIG + "\n[display\n")
    page = client.get("/changes").text
    assert "The edited file has a mistake" in page
    assert '<button type="submit" disabled>Apply changes</button>' in page
    assert "kill -HUP" not in page
    # Sent anyway: nothing is asked of PaperPi.
    response = client.post("/changes/apply")
    assert response.headers["location"] == "/changes"
    assert scheduler.reloads == 0


def test_as_a_service_the_page_shows_systemctl(setup, cfg, monkeypatch):
    client, _ = setup
    monkeypatch.setenv("INVOCATION_ID", "abc")
    cfg.write_text(edited(('name = "Clock"', 'name = "Big clock"')))
    page = client.get("/changes").text
    assert "<code>sudo systemctl reload paperpi</code>" in page and "kill" not in page


def test_without_the_screen_running_there_is_nothing_to_apply(cfg):
    editor = PluginEditor(cfg)
    editor.loaded(CONFIG)
    app = create_app(auth.Auth(cfg, config.WebSettings(login=False)), editor)
    client = TestClient(app, follow_redirects=False, base_url=PI)
    cfg.write_text(edited(('name = "Clock"', 'name = "Big clock"')))
    assert "edits-bar" not in client.get("/").text
    assert "screen is not running" in client.get("/changes").text
    assert client.post("/changes/apply").status_code == 409
