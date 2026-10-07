import os
import re
import stat

import pytest

from paperpi import config
from paperpi.cli import main
from paperpi.web import password as web_password

CONFIG = (
    "config_version = 1\n"
    "# my screen\n"
    '[display]\ntype = "virtual"\n'
    "[[plugin]]\n"
    'name = "Clock"\ntype = "basic_clock"  # the first plugin\n'
)


@pytest.fixture(autouse=True)
def cheap_scrypt(monkeypatch):
    # The real cost (2**14) takes a moment on a Pi 3.
    monkeypatch.setattr(web_password, "_N", 16)
    monkeypatch.setattr(web_password, "_R", 1)


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "paperpi.toml"
    path.write_text(CONFIG)
    path.chmod(0o640)
    return path


def test_password_hash_round_trip():
    stored = web_password.hash_password("correct horse")
    assert stored.startswith("scrypt:16:1:1:")
    assert web_password.check_password("correct horse", stored)
    assert not web_password.check_password("correct hors", stored)
    # The same password gives a different hash each time (a new random salt).
    assert web_password.hash_password("correct horse") != stored


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "plain text",
        "md5:16:1:1:AAAA:AAAA",
        "scrypt:x:1:1:AAAA:AAAA",
        "scrypt:16:1:1:%%%:AAAA",
        # Costs that would use gigabytes of memory for one log-in are refused.
        "scrypt:1073741824:8:1:AAAA:AAAA",
        "scrypt:16:1000:1:AAAA:AAAA",
    ],
)
def test_a_broken_hash_never_matches(stored):
    assert not web_password.check_password("", stored)
    assert not web_password.check_password("anything", stored)


@pytest.mark.parametrize(
    ("password", "again", "problem"),
    [
        ("correct horse", "correct horse", None),
        ("12345678", "12345678", None),
        ("correct horse", "correct hors", "not the same"),
        ("1234567", "1234567", "at least 8"),
        ("x" * 1001, "x" * 1001, "at most 1000"),
    ],
)
def test_password_rules(password, again, problem):
    found = web_password.password_problem(password, again)
    assert (found is None) if problem is None else (problem in found)


def test_saving_the_password_keeps_the_rest_of_the_file(cfg):
    assert web_password.save_password_hash(cfg, "scrypt:one")
    text = cfg.read_text()
    assert text.startswith(CONFIG)  # comments and all other lines are unchanged
    assert config.parse(text).web.password_hash == "scrypt:one"
    assert stat.S_IMODE(os.stat(cfg).st_mode) == 0o640  # the permissions stay
    assert web_password.save_password_hash(cfg, "scrypt:two")
    assert config.parse(cfg.read_text()).web.password_hash == "scrypt:two"
    # Removing it (paperpi reset-password) leaves the file as it was, apart from [web].
    assert web_password.save_password_hash(cfg, None)
    assert config.parse(cfg.read_text()).web.password_hash is None
    assert not web_password.save_password_hash(cfg, None)  # nothing left to remove


def test_saving_into_a_web_part_written_by_hand(cfg):
    cfg.write_text(CONFIG.replace("[[plugin]]", "[web]\nport = 9000  # mine\n\n[[plugin]]"))
    web_password.save_password_hash(cfg, "scrypt:one")
    loaded = config.parse(cfg.read_text())
    assert (loaded.web.port, loaded.web.password_hash) == (9000, "scrypt:one")
    assert "port = 9000  # mine" in cfg.read_text()
    assert [p.entry.name for p in loaded.plugins] == ["Clock"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("config_version = \n", "not valid TOML"),
        ("web = 3\n", "web must be a [web] part"),
    ],
)
def test_saving_into_a_broken_file(cfg, text, message):
    cfg.write_text(text)
    with pytest.raises(web_password.PasswordError, match=re.escape(message)):
        web_password.save_password_hash(cfg, "scrypt:one")
    assert cfg.read_text() == text


def test_saving_into_a_missing_file(tmp_path):
    with pytest.raises(web_password.PasswordError, match="file not found"):
        web_password.save_password_hash(tmp_path / "nothing.toml", "scrypt:one")


def test_reset_password_with_a_broken_file(tmp_path, capsys):
    assert main(["reset-password", "--config", str(tmp_path / "nothing.toml")]) == 1
    assert "file not found" in capsys.readouterr().err


def test_login_false_is_a_hint():
    loaded = config.parse(CONFIG.replace("[[plugin]]", "[web]\nlogin = false\n[[plugin]]"))
    assert loaded.web.login is False
    (hint,) = loaded.problems
    assert hint.level == "hint" and "anyone on the home network" in hint.message


@pytest.mark.parametrize(
    ("web", "message"),
    [
        ("port = 0", "port: Input should be greater than or equal to 1"),
        ('port = "80"', "port: Input should be a valid integer"),
        ("login = 3", "login: Input should be a valid boolean"),
        ('address = ""', "address: String should have at least 1 character"),
    ],
)
def test_wrong_web_settings_are_errors(web, message):
    with pytest.raises(config.ConfigError) as error:
        config.parse(CONFIG.replace("[[plugin]]", f"[web]\n{web}\n[[plugin]]"), "paperpi.toml")
    assert message in str(error.value)
    assert "paperpi.toml line 6 [web]" in str(error.value)


def test_unknown_web_setting_is_a_warning():
    loaded = config.parse(CONFIG.replace("[[plugin]]", "[web]\npasword_hash = 1\n[[plugin]]"))
    (warning,) = loaded.problems
    assert "did you mean 'password_hash'?" in warning.message


def test_reset_password(cfg, capsys):
    """Step 1 of a forgotten password: paperpi reset-password removes the password."""
    web_password.save_password_hash(cfg, web_password.hash_password("correct horse"))
    assert main(["reset-password", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "removed the web password" in out and "set a new password" in out
    assert cfg.read_text().startswith(CONFIG)
    assert config.parse(cfg.read_text()).web.password_hash is None
    assert main(["reset-password", "--config", str(cfg)]) == 0
    assert "no web password is set" in capsys.readouterr().out
