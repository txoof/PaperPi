import tomllib

import pytest

from paperpi import example, plugins
from paperpi.web import config_file
from paperpi.web.config_file import ChangedMeanwhile, EditError

CONFIG = """\
config_version = 1
[display]
type = "virtual"

# the clock in the kitchen
[[plugin]]
id = "Clock"
type = "basic_clock"
# refresh = 60

# words
[[plugin]]
id = "Words"
type = "word_clock"
enabled = true  # for now
[plugin.extra]
a = 1

[web]
port = 8081
"""


def names(text):
    return [b["id"] for b in tomllib.loads(text).get("plugin", [])]


def test_blocks_start_at_their_comments():
    found = config_file.blocks(CONFIG)
    lines = CONFIG.splitlines()
    assert [lines[b.start] for b in found] == ["# the clock in the kitchen", "# words"]
    assert [lines[b.header] for b in found] == ["[[plugin]]", "[[plugin]]"]
    # The second block holds its [plugin.extra] part, not [web].
    assert lines[found[1].own_end] == "[plugin.extra]"
    assert lines[found[1].end] == "[web]"


def test_moving_a_block_takes_its_comments_and_parts_along():
    moved = config_file.move(CONFIG, 1, "Words", -1)
    assert names(moved) == ["Words", "Clock"]
    assert moved.index("# words") < moved.index('id = "Words"') < moved.index("[plugin.extra]")
    assert moved.index("[plugin.extra]") < moved.index("# the clock in the kitchen")
    assert tomllib.loads(moved)["plugin"][0]["extra"] == {"a": 1}
    assert tomllib.loads(moved)["web"] == {"port": 8081}
    # And back again: the same settings, nothing lost.
    back = config_file.move(moved, 0, "Words", 1)
    assert tomllib.loads(back) == tomllib.loads(CONFIG)
    for comment in ["# the clock in the kitchen", "# refresh = 60", "# words", "# for now"]:
        assert back.count(comment) == 1


def test_a_block_cant_move_past_the_ends():
    with pytest.raises(EditError, match="can't move further"):
        config_file.move(CONFIG, 0, "Clock", -1)
    with pytest.raises(EditError, match="can't move further"):
        config_file.move(CONFIG, 1, "Words", 1)


def test_removing_a_block_removes_its_comments():
    removed = config_file.remove(CONFIG, 0, "Clock")
    assert names(removed) == ["Words"]
    assert "kitchen" not in removed and "# refresh" not in removed
    gone = config_file.remove(removed, 0, "Words")
    assert "plugin" not in tomllib.loads(gone)
    assert tomllib.loads(gone)["web"] == {"port": 8081}


def test_switching_off_and_on():
    off = config_file.set_enabled(CONFIG, 0, "Clock", False)
    assert 'type = "basic_clock"\nenabled = false\n' in off
    assert config_file.set_enabled(off, 0, "Clock", True) == CONFIG
    # An "enabled" line written by hand is changed; switching on removes it (the default).
    words_off = config_file.set_enabled(CONFIG, 1, "Words", False)
    assert tomllib.loads(words_off)["plugin"][1]["enabled"] is False
    assert (
        "enabled"
        not in tomllib.loads(config_file.set_enabled(words_off, 1, "Words", True))["plugin"][1]
    )


def test_adding_a_block_after_the_last_plugin():
    block = example.plugin_block(plugins.load("dec_binary_clock"), "Dots", {})
    added = config_file.add(CONFIG, block)
    assert names(added) == ["Clock", "Words", "Dots"]
    assert added.index('id = "Dots"') < added.index("[web]")
    assert tomllib.loads(added)["web"] == {"port": 8081}
    # A file without plugins: at the end.
    empty = 'config_version = 1\n[display]\ntype = "virtual"'
    assert names(config_file.add(empty, block)) == ["Dots"]


def test_a_block_changed_meanwhile_is_not_touched():
    with pytest.raises(ChangedMeanwhile):
        config_file.remove(CONFIG, 0, "Words")
    with pytest.raises(ChangedMeanwhile):
        config_file.move(CONFIG, 5, "Clock", 1)


def test_files_it_doesnt_understand_are_not_changed():
    # A [[plugin]] line inside a multi-line string is not a block...
    text = CONFIG.replace('type = "virtual"', 'type = "virtual"\nnote = """\n[[plugin]]\n"""')
    assert names(config_file.remove(text, 0, "Clock")) == ["Words"]
    # ... and a header written in another way is not found, so nothing is changed.
    quoted = CONFIG.replace('[[plugin]]\nid = "Words"', '[["plugin"]]\nid = "Words"')
    with pytest.raises(EditError, match="config file itself"):
        config_file.move(quoted, 0, "Clock", 1)
    with pytest.raises(EditError, match="not valid TOML"):
        config_file.move("[[plugin]\n", 0, "Clock", 1)


def test_saving_keeps_the_permissions(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    path.chmod(0o640)
    real, text = config_file.read(path)
    config_file.write(real, config_file.remove(text, 0, "Clock"))
    assert names(path.read_text()) == ["Words"]
    assert path.stat().st_mode & 0o777 == 0o640
    with pytest.raises(EditError, match="file not found"):
        config_file.read(tmp_path / "nothing.toml")


def test_comments_right_after_a_setting_stay_with_the_block_above():
    text = '[[plugin]]\nid = "A"\ntype = "x"\n# refresh = 60\n[[plugin]]\nid = "B"\ntype = "y"\n'
    assert config_file.remove(text, 1, "B") == '[[plugin]]\nid = "A"\ntype = "x"\n# refresh = 60\n'


def test_windows_line_endings_are_kept():
    text = CONFIG.replace("\n", "\r\n")
    block = example.plugin_block(plugins.load("dec_binary_clock"), "Dots", {})
    for changed in [
        config_file.move(text, 1, "Words", -1),
        config_file.set_enabled(text, 0, "Clock", False),
        config_file.set_enabled(text, 1, "Words", True),
        config_file.remove(text, 0, "Clock"),
        config_file.add(text, block),
    ]:
        assert "\n" not in changed.replace("\r\n", "")


def test_a_file_without_a_last_line_break():
    text = CONFIG.removesuffix("\n")
    assert tomllib.loads(config_file.move(text, 1, "Words", -1))["web"] == {"port": 8081}
    last = '[[plugin]]\nid = "A"\ntype = "x"'
    off = config_file.set_enabled(last, 0, "A", False)
    assert tomllib.loads(off)["plugin"][0]["enabled"] is False


def test_other_parts_between_blocks_stay_where_they_are():
    text = CONFIG.replace("[web]\nport = 8081\n", "").replace(
        "# words\n", "[web]\nport = 8081\n\n# words\n"
    )
    moved = config_file.move(text, 1, "Words", -1)
    assert names(moved) == ["Words", "Clock"]
    # The blocks swap places; [web] stays between them.
    assert moved.index('id = "Words"') < moved.index("[web]") < moved.index('id = "Clock"')
    assert tomllib.loads(moved)["web"] == {"port": 8081}


def test_enabled_in_a_part_or_a_string_is_not_the_switch():
    text = (
        '[[plugin]]\nid = "A"\nnote = """\nenabled = true\n"""\ntype = "x"\n'
        "[plugin.extra]\nenabled = true\n"
    )
    off = config_file.set_enabled(text, 0, "A", False)
    data = tomllib.loads(off)["plugin"][0]
    assert data["enabled"] is False and data["extra"] == {"enabled": True}
    assert data["note"] == "enabled = true\n"
    assert config_file.set_enabled(off, 0, "A", True) == text
    # Only a "type" inside a string: the new line goes right below [[plugin]].
    hidden = '[[plugin]]\nnote = """\ntype = "y"\n"""\nid = "B"\n'
    assert tomllib.loads(config_file.set_enabled(hidden, 0, "B", False))["plugin"][0] == {
        "note": 'type = "y"\n',
        "id": "B",
        "enabled": False,
    }


def test_unicode_line_breaks_inside_a_value_are_not_line_breaks():
    text = CONFIG.replace('id = "Words"', 'id = "Words"\nplace = "a b\x85c"')
    assert names(config_file.remove(text, 0, "Clock")) == ["Words"]
    off = config_file.set_enabled(text, 1, "Words", False)
    assert tomllib.loads(off)["plugin"][1]["place"] == "a b\x85c"


def test_a_file_too_large_for_paperpi_is_not_saved(tmp_path, monkeypatch):
    from paperpi import limits

    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    monkeypatch.setattr(limits, "CONFIG_FILE_BYTES", len(CONFIG))
    with pytest.raises(EditError, match="larger than"):
        config_file.write(path, CONFIG + "#\n")
    assert path.read_text() == CONFIG
    config_file.write(path, CONFIG)
    assert config_file.saved_here(path, CONFIG)
    assert not config_file.saved_here(path, CONFIG + "#\n")
