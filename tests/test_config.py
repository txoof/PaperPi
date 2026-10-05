"""Reading and checking the config file (paperpi.config)."""

import os
import textwrap

import pytest
from epdlib import ScreenMode

from paperpi import config, limits
from paperpi.config import ConfigError, DisplaySettings, folder_name, load, parse

GOOD = """\
config_version = 1

[display]
type = "virtual"

[[plugin]]
name = "Clock"
type = "basic_clock"
"""


def toml(text: str) -> str:
    return textwrap.dedent(text).lstrip()


def problems(cfg, level=None):
    return [str(p) for p in cfg.problems if level is None or p.level == level]


def errors_of(text: str) -> list[str]:
    with pytest.raises(ConfigError) as error:
        parse(toml(text), "paperpi.toml")
    return [str(p) for p in error.value.problems]


# --- A good file -----------------------------------------------------------------------------


def test_good_file_uses_defaults():
    cfg = parse(GOOD)
    assert cfg.problems == []
    assert cfg.display.size == (1200, 825)
    assert cfg.display.screen_mode == ScreenMode.gray(16)
    (clock,) = cfg.plugins
    assert clock.entry.name == "Clock"
    assert clock.entry.enabled
    assert clock.entry.level == "rotation"
    assert clock.entry.time_limit == limits.PLUGIN_UPDATE
    assert clock.refresh == 60  # the plugin's suggestion
    assert clock.layout == "time"  # the plugin's first layout
    assert clock.settings.hours == 24
    assert cfg.plugin("Clock") is clock


def test_settings_are_read():
    cfg = parse(
        toml("""
        config_version = 1
        [display]
        type = "virtual"
        width = 800
        height = 480
        mode = "7color"
        rotation = 90
        [[plugin]]
        name = "Clock"
        type = "basic_clock"
        enabled = false
        level = "interrupt"
        refresh = 30
        time_limit = 5
        layout = "time_date"
        hours = 12
        """)
    )
    assert cfg.problems == []
    assert cfg.display.size == (800, 480)
    assert cfg.display.layout_size == (480, 800)
    assert cfg.display.screen_mode == ScreenMode.palette()
    clock = cfg.plugin("Clock")
    assert not clock.entry.enabled
    assert clock.refresh == 30
    assert clock.entry.time_limit == 5
    assert clock.layout == "time_date"
    assert clock.settings.hours == 12


def test_web_part_is_accepted_for_later():
    assert parse(GOOD + '\n[web]\npassword_hash = "x"\n').problems == []


def test_same_plugin_type_twice_with_different_names():
    cfg = parse(GOOD + '\n[[plugin]]\nname = "Clock 12"\ntype = "basic_clock"\nhours = 12\n')
    assert [p.entry.name for p in cfg.plugins] == ["Clock", "Clock 12"]


@pytest.mark.parametrize(
    ("color", "mode", "expected"),
    [
        (False, "7color", ScreenMode.bw()),
        (False, "rgb", ScreenMode.gray(256)),
        (False, "gray4", ScreenMode.gray(4)),
        (True, "rgb", ScreenMode.rgb()),
    ],
)
def test_color_false_draws_without_colour(color, mode, expected):
    assert DisplaySettings(type="virtual", color=color, mode=mode).screen_mode == expected


# --- Problems with the whole file -------------------------------------------------------------


def test_toml_syntax_error_names_the_line():
    (message,) = errors_of("""
        config_version = 1
        [display]
        type = virtual
        """)
    assert message.startswith("paperpi.toml line 3: not valid TOML")


def test_config_version_missing():
    (message,) = errors_of('[display]\ntype = "virtual"\n')
    assert "config_version = 1 is missing" in message


def test_config_version_from_a_newer_paperpi():
    (message,) = errors_of('config_version = 2\n[display]\ntype = "virtual"\n')
    assert message == (
        "paperpi.toml line 1: config_version 2 was written by a newer PaperPi; "
        "this one reads version 1"
    )


def test_display_missing():
    (message,) = errors_of("config_version = 1\n")
    assert "a [display] part is needed" in message


def test_unknown_display_type_suggests_a_name():
    (message,) = errors_of('config_version = 1\n[display]\ntype = "virtul"\n')
    assert message == (
        "paperpi.toml line 3 [display]: unknown screen type 'virtul' "
        "(did you mean 'virtual'?); known: virtual"
    )


def test_wrong_display_value_names_line_and_setting():
    (message,) = errors_of("""
        config_version = 1
        [display]
        type = "virtual"
        rotation = 45
        """)
    assert message == (
        "paperpi.toml line 4 [display]: rotation: Input should be 0, 90, 180 or 270 (got 45)"
    )


def test_size_is_only_for_a_virtual_screen(monkeypatch):
    monkeypatch.setattr(config, "DISPLAY_TYPES", ("virtual", "it8951"))
    (message,) = errors_of("""
        config_version = 1
        [display]
        type = "it8951"
        width = 800
        """)
    assert message.startswith("paperpi.toml line 4 [display]: width is only for type")


def test_plugin_problems_are_not_checked_while_the_file_is_wrong():
    messages = errors_of('config_version = 1\n[[plugin]]\nname = "x"\ntype = "nope"\n')
    assert len(messages) == 1


# --- Problems in one plugin block -------------------------------------------------------------


def test_wrong_plugin_value_leaves_only_that_plugin_out():
    cfg = parse(
        GOOD + '\n[[plugin]]\nname = "Bad"\ntype = "basic_clock"\nhours = 13\n', "paperpi.toml"
    )
    assert [p.entry.name for p in cfg.plugins] == ["Clock"]
    assert problems(cfg) == [
        "paperpi.toml line 13 [[plugin]] 'Bad': hours: Input should be 12 or 24 (got 13)"
    ]


def test_unknown_plugin_type_suggests_a_name():
    cfg = parse(GOOD.replace('"basic_clock"', '"basic_clok"'), "paperpi.toml")
    assert cfg.plugins == []
    # Only the start: the list of known types grows with every new plugin.
    [problem] = problems(cfg)
    assert problem.startswith(
        "paperpi.toml line 8 [[plugin]] 'Clock': unknown plugin type 'basic_clok' "
        "(did you mean 'basic_clock'?); known: basic_clock, debugging, default"
    )


def test_missing_name_and_type():
    cfg = parse("config_version = 1\n[display]\ntype = 'virtual'\n[[plugin]]\nlevel = 'alert'\n")
    assert cfg.plugins == []
    assert problems(cfg) == [
        "config line 4 [[plugin]] 1: name: required setting is missing",
        "config line 4 [[plugin]] 1: type: required setting is missing",
    ]


def test_unknown_layout():
    cfg = parse(GOOD + 'layout = "big"\n')
    assert problems(cfg) == [
        "config line 9 [[plugin]] 'Clock': unknown layout 'big'; "
        "choose from: time, time_date, small"
    ]


def test_wrong_level():
    cfg = parse(GOOD + 'level = "sometimes"\n')
    assert cfg.plugins == []
    assert "level: Input should be 'alert', 'interrupt' or 'rotation'" in problems(cfg)[0]


@pytest.mark.parametrize("value", ["0", "-5", f"{limits.PLUGIN_UPDATE_MAX + 1}", '"long"'])
def test_wrong_time_limit(value):
    cfg = parse(GOOD + f"time_limit = {value}\n")
    assert cfg.plugins == []
    assert "time_limit:" in problems(cfg)[0]


@pytest.mark.parametrize("other", ["Clock", "clock", "CLOCK!"])
def test_names_must_be_different(other):
    cfg = parse(GOOD + f'\n[[plugin]]\nname = "{other}"\ntype = "basic_clock"\n')
    assert [p.entry.name for p in cfg.plugins] == ["Clock"]
    assert problems(cfg) == [
        f"config line 11 [[plugin]] '{other}': name '{other}' is already used by the plugin "
        "block at line 6; names must be different (also ignoring capitals and punctuation)"
    ]


def test_single_brackets_for_plugin():
    cfg = parse('config_version = 1\n[display]\ntype = "virtual"\n[plugin]\nname = "x"\n')
    assert cfg.plugins == []
    assert problems(cfg) == ["config line 4: write [[plugin]] (two brackets) above each plugin"]


# --- Warnings and hints -----------------------------------------------------------------------


def test_unknown_settings_are_warnings_with_suggestions():
    cfg = parse(
        toml("""
        config_version = 1
        plugins = []
        [display]
        type = "virtual"
        rotaton = 90
        [[plugin]]
        name = "Clock"
        type = "basic_clock"
        houres = 12
        dispaly_time = 30
        colour = "red"
        """)
    )
    assert len(cfg.plugins) == 1
    assert problems(cfg, "warning") == [
        "config line 2: unknown setting 'plugins' (did you mean 'plugin'?)",
        "config line 5 [display]: unknown setting 'rotaton' (did you mean 'rotation'?)",
        "config line 9 [[plugin]] 'Clock': unknown setting 'houres' (did you mean 'hours'?)",
        "config line 10 [[plugin]] 'Clock': unknown setting 'dispaly_time' "
        "(did you mean 'display_time'?)",
        "config line 11 [[plugin]] 'Clock': unknown setting 'colour'",
    ]


def test_hint_when_refresh_equals_display_time():
    cfg = parse(GOOD + "display_time = 60\n")  # the clock suggests a 60 s refresh
    assert len(cfg.plugins) == 1
    assert problems(cfg, "hint") == [
        "config line 9 [[plugin]] 'Clock': refresh equals display time: the plugin may redraw "
        "just as it is swapped out; make refresh slightly longer, or a fraction of the display "
        "time"
    ]


@pytest.mark.parametrize(
    "settings",
    ["display_time = 61", "display_time = 30\nrefresh = 31", 'display_time = 60\nlevel = "alert"'],
)
def test_no_hint_otherwise(settings):
    assert parse(GOOD + settings + "\n").problems == []


# --- Reading the file -------------------------------------------------------------------------


def test_file_not_found(tmp_path):
    with pytest.raises(ConfigError, match="file not found"):
        load(tmp_path / "missing.toml", state_dir=None)


def test_file_too_large(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(GOOD + "#" * limits.CONFIG_FILE_BYTES)
    with pytest.raises(ConfigError, match="larger than"):
        load(path, state_dir=None)


def test_file_not_utf8(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_bytes(GOOD.encode() + b"# \xff\n")
    with pytest.raises(ConfigError, match="not UTF-8"):
        load(path, state_dir=None)


# --- The last good copy -----------------------------------------------------------------------


@pytest.fixture
def files(tmp_path):
    path = tmp_path / "etc" / "paperpi.toml"
    path.parent.mkdir()
    path.write_text(GOOD)
    state = tmp_path / "state"
    return path, state, state / config.LAST_GOOD_NAME


def test_good_load_saves_last_good_copy(files):
    path, state, last_good = files
    load(path, state_dir=state)
    assert last_good.read_text() == GOOD
    assert last_good.stat().st_mode & 0o777 == 0o600  # it may hold passwords
    assert list(state.iterdir()) == [last_good]  # no temporary files left


def test_unchanged_file_is_not_written_again(files):
    path, state, last_good = files
    load(path, state_dir=state)
    os.utime(last_good, (0, 0))
    load(path, state_dir=state)
    assert last_good.stat().st_mtime == 0


def test_errors_in_a_plugin_block_dont_replace_last_good_copy(files):
    path, state, last_good = files
    load(path, state_dir=state)
    path.write_text(GOOD + "hours = 13\n")
    cfg = load(path, state_dir=state)
    assert not cfg.from_last_good
    assert cfg.plugins == []
    assert last_good.read_text() == GOOD


def test_broken_file_uses_last_good_copy(files):
    path, state, _ = files
    load(path, state_dir=state)
    path.write_text("config_version = 1\n[display\n")
    cfg = load(path, state_dir=state)
    assert cfg.from_last_good
    assert [p.entry.name for p in cfg.plugins] == ["Clock"]
    assert problems(cfg) == [
        "paperpi.toml line 2: not valid TOML: Expected ']' at the end of a table declaration "
        "(at line 2, column 9)",
        f"paperpi.toml: {path} can't be used; running on the last good copy",
    ]


def test_missing_file_uses_last_good_copy(files):
    path, state, _ = files
    load(path, state_dir=state)
    path.unlink()
    assert load(path, state_dir=state).from_last_good


def test_broken_file_without_last_good_copy_raises(files):
    path, state, last_good = files
    path.write_text("config_version = 1\n")
    with pytest.raises(ConfigError, match="a \\[display\\] part is needed"):
        load(path, state_dir=state)
    assert not last_good.exists()


def test_state_folder_that_cant_be_written_is_only_a_warning(files, caplog):
    path, state, _ = files
    state.write_text("a file where the folder should be")
    cfg = load(path, state_dir=state)
    assert len(cfg.plugins) == 1
    assert "can't save the last good copy" in caplog.text


# --- Small helpers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "folder"),
    [
        ("Weather Berlin", "weather-berlin"),
        ("../../etc", "etc"),
        ("Clock!", "clock"),
        ("Ünïcode", "n-code"),
        ("!!!", "plugin"),
    ],
)
def test_folder_name_is_safe(name, folder):
    assert folder_name(name) == folder


# --- Added after review ------------------------------------------------------------------------


def test_config_version_wrong_type():
    (message,) = errors_of('config_version = "1"\n[display]\ntype = "virtual"\n')
    assert message == "paperpi.toml line 1: config_version must be a whole number, got '1'"


def test_web_must_be_a_part():
    (message,) = errors_of('config_version = 1\nweb = 3\n[display]\ntype = "virtual"\n')
    assert message == "paperpi.toml line 2: web must be a [web] part"


def test_plugin_list_of_numbers():
    cfg = parse('config_version = 1\nplugin = [1]\n[display]\ntype = "virtual"\n')
    assert cfg.plugins == []
    assert problems(cfg) == ["config line 2: each plugin must be a [[plugin]] block"]


@pytest.mark.parametrize(
    "text",
    [
        "config_version = 1\nx = " + "[" * 5000 + "]" * 5000 + "\n",  # nested very deep
        "config_version = 1\nx = " + "9" * 5000 + "\n",  # a number with 5000 digits
    ],
    ids=["deep", "long-number"],
)
def test_strange_toml_is_an_error_not_a_crash(text):
    with pytest.raises(ConfigError, match="not valid TOML"):
        parse(text)


def test_too_many_plugin_blocks():
    block = '\n[[plugin]]\nname = "Clock {n}"\ntype = "basic_clock"\n'
    text = GOOD + "".join(block.format(n=n) for n in range(limits.PLUGIN_BLOCKS + 5))
    cfg = parse(text)
    assert len(cfg.plugins) == limits.PLUGIN_BLOCKS
    assert "at most 100 are used" in problems(cfg, "error")[0]


def test_broken_plugin_code_only_switches_off_that_plugin(monkeypatch):
    real_load = config.plugins.load

    def load(plugin_type, package=None):
        if plugin_type == "broken":
            raise ModuleNotFoundError("No module named 'requests'")
        return real_load(plugin_type)

    monkeypatch.setattr(config.plugins, "load", load)
    monkeypatch.setattr(config.plugins, "available", lambda *a: ["basic_clock", "broken"])
    cfg = parse(GOOD + '\n[[plugin]]\nname = "Broken"\ntype = "broken"\n')
    assert [p.entry.name for p in cfg.plugins] == ["Clock"]
    assert problems(cfg) == [
        "config line 12 [[plugin]] 'Broken': the plugin itself is broken: "
        "ModuleNotFoundError: No module named 'requests'"
    ]


def test_secret_values_are_never_shown(monkeypatch):
    from pydantic import SecretStr

    from paperpi.plugin import Plugin, PluginSettings, ready

    class Settings(PluginSettings):
        api_key: SecretStr = SecretStr("")
        count: int = 1

    plugin = Plugin(
        type="keyed",
        description="Has a key.",
        settings=Settings,
        layouts={"one": {"column": [{"name": "t", "type": "text"}]}},
        fetch=lambda context: ready(1),
        draw=lambda data, context: {"t": "x"},
        sample=1,
        refresh=60,
    )
    monkeypatch.setattr(config.plugins, "available", lambda: ["keyed"])
    monkeypatch.setattr(config.plugins, "load", lambda plugin_type, package=None: plugin)
    cfg = parse(GOOD.replace("basic_clock", "keyed") + "api_key = 12345678\ncount = 'x'\n")
    text = "\n".join(problems(cfg))
    assert "api_key: Input should be a valid string" in text
    assert "12345678" not in text
    assert "count: Input should be a valid integer" in text and "(got 'x')" in text


def test_long_values_are_shortened_in_messages():
    cfg = parse(GOOD + f'hours = "{"x" * 500}"\n')
    (message,) = problems(cfg)
    assert message.endswith("(got 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx...)")


def test_duplicate_name_is_found_even_if_the_first_block_is_broken():
    first = '[[plugin]]\nname = "Clock"\ntype = "basic_clock"\nhours = 13\n'
    second = '\n[[plugin]]\nname = "Clock"\ntype = "basic_clock"\n'
    cfg = parse('config_version = 1\n[display]\ntype = "virtual"\n' + first + second)
    assert cfg.plugins == []
    assert len(problems(cfg, "error")) == 2


def test_line_numbers_after_a_multi_line_string():
    text = toml('''
        config_version = 1
        [display]
        type = "virtual"
        [[plugin]]
        name = "Clock"
        type = "basic_clock"
        note = """
        hours = 1
        """
        hours = 13
        ''')
    assert problems(parse(text), "error") == [
        "config line 10 [[plugin]] 'Clock': hours: Input should be 12 or 24 (got 13)"
    ]


def test_hint_names_the_refresh_line_when_refresh_is_set():
    cfg = parse(GOOD + "refresh = 120\n")  # display_time defaults to 120
    (hint,) = problems(cfg, "hint")
    assert hint.startswith("config line 9 ")


def test_file_that_cant_be_read(tmp_path):
    with pytest.raises(ConfigError, match="can't read"):
        load(tmp_path, state_dir=None)  # a folder, not a file


def test_file_with_only_warnings_is_saved_as_last_good(files):
    path, state, last_good = files
    path.write_text(GOOD + "colour = 1\n")
    cfg = load(path, state_dir=state)
    assert problems(cfg, "warning")
    assert last_good.is_file()


def test_broken_last_good_copy_raises_the_files_own_error(files):
    path, state, last_good = files
    state.mkdir()
    last_good.write_text("not toml [")
    path.write_text("config_version = 1\n")
    with pytest.raises(ConfigError, match="a \\[display\\] part is needed"):
        load(path, state_dir=state)


def test_damaged_last_good_copy_is_replaced(files):
    path, state, last_good = files
    state.mkdir()
    last_good.write_bytes(b"\xff\xfe broken")
    load(path, state_dir=state)
    assert last_good.read_text() == GOOD


def test_state_folder_is_private_and_old_temporary_files_are_removed(files):
    path, state, last_good = files
    load(path, state_dir=state)
    assert state.stat().st_mode & 0o777 == 0o700
    leftover = state / f".{last_good.name}.abc123.tmp"
    leftover.write_text("half written")
    path.write_text(GOOD + "# changed\n")
    load(path, state_dir=state)
    assert not leftover.exists()


@pytest.mark.parametrize(
    "setting", ["refresh = inf", "display_time = 1e300", "alert_max_time = 700000"]
)
def test_time_settings_have_an_upper_limit(setting):
    cfg = parse(GOOD + setting + "\n")
    assert cfg.plugins == []
    assert "less than or equal to 604800" in problems(cfg)[0]


@pytest.mark.parametrize("value", ["0.5", "4.9"])
def test_refresh_is_at_least_5_seconds(value):
    cfg = parse(GOOD + f"refresh = {value}\n")
    assert cfg.plugins == []
    assert "refresh: Input should be greater than or equal to 5" in problems(cfg)[0]


def test_hint_when_the_fallback_clock_is_switched_off():
    cfg = parse(GOOD.replace('type = "virtual"', 'type = "virtual"\nfallback_clock = false'))
    assert cfg.display.fallback_clock is False
    assert len(cfg.plugins) == 1
    [hint] = problems(cfg, "hint")
    assert "fallback_clock = false is not recommended" in hint
