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
        "scrypt:x:1:1:AAAA:AAAA",
        "scrypt:16:1:1:%%%:AAAA",
        "scrypt:16:1:1::AAAA",  # no salt
        "scrypt:16:1:1:AAAA:",  # no hash
        "scrypt:16:1:1:AAAA:AAAA",  # a hash of 3 bytes
        "scrypt:16:1:1:AAAA:AAAA:AAAA",
        # Costs a hand-edited hash may not have: they would use too much memory or time.
        "scrypt:0:1:1:AAAA:" + "A" * 43,
        "scrypt:24:1:1:AAAA:" + "A" * 43,  # N must be a power of 2
        "scrypt:131072:32:1:AAAA:" + "A" * 43,  # 512 MB
        "scrypt:1048576:1:1:AAAA:" + "A" * 43,  # 128 MB
        "scrypt:16384:8:16:AAAA:" + "A" * 43,  # too much work
        "scrypt:16384:0:1:AAAA:" + "A" * 43,
        "scrypt:16384:8:0:AAAA:" + "A" * 43,
    ],
)
def test_a_broken_hash_is_never_checked_and_never_matches(stored, monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("scrypt was run for a broken hash")

    monkeypatch.setattr(web_password, "_scrypt", never)
    assert not web_password.check_password("", stored)
    assert not web_password.check_password("anything", stored)
    assert not web_password.looks_like_hash(stored)


def test_only_scrypt_hashes_are_used():
    stored = web_password.hash_password("correct horse")
    assert not web_password.check_password("correct horse", "md5" + stored.removeprefix("scrypt"))


def test_a_hash_is_checked_with_its_own_costs(monkeypatch):
    # Made with other costs (e.g. by an older PaperPi): it still works.
    monkeypatch.setattr(web_password, "_N", 32)
    stored = web_password.hash_password("correct horse")
    monkeypatch.setattr(web_password, "_N", 64)
    assert web_password.check_password("correct horse", stored)
    assert web_password.looks_like_hash(stored)


def test_the_largest_cost_allowed_still_works(monkeypatch):
    monkeypatch.setattr(web_password, "_N", 2**16)
    monkeypatch.setattr(web_password, "_R", 8)  # 64 MB: the most a hash may use
    stored = web_password.hash_password("correct horse")
    assert web_password.check_password("correct horse", stored)


@pytest.mark.parametrize(
    ("password", "again", "problem"),
    [
        ("correct horse", "correct horse", None),
        ("12345678", "12345678", None),
        ("correct horse", "correct hors", "not the same"),
        ("1234567", "1234567", "at least 8"),
        ("x" * 1001, "x" * 1001, "at most 1000"),
        ("abcdefg\ud800", "abcdefg\ud800", "can't be saved"),  # a broken character
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


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read every file")
def test_reset_password_without_sudo(cfg, capsys):
    cfg.chmod(0o000)
    assert main(["reset-password", "--config", str(cfg)]) == 1
    error = capsys.readouterr().err
    assert "Permission denied" in error and error.endswith("; run it with sudo\n")


def test_saving_as_root_keeps_the_owner(cfg, monkeypatch):
    """With sudo, the new file must still belong to the PaperPi service's user."""
    owners = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: owners.append((uid, gid)))
    web_password.save_password_hash(cfg, "scrypt:one")
    info = os.stat(cfg)
    assert owners == [(info.st_uid, info.st_gid)]


def test_saving_through_a_link_changes_the_real_file(cfg):
    link = cfg.with_name("link.toml")
    link.symlink_to(cfg)
    web_password.save_password_hash(link, "scrypt:one")
    assert link.is_symlink()
    assert config.parse(cfg.read_text()).web.password_hash == "scrypt:one"


@pytest.mark.parametrize("stored", ["", "garbage", "scrypt:16:1:1:AAAA"])
def test_a_broken_password_hash_is_a_warning(stored):
    text = CONFIG.replace("[[plugin]]", f'[web]\npassword_hash = "{stored}"\n[[plugin]]')
    (warning,) = config.parse(text).problems
    assert warning.level == "warning" and "nobody can log in" in warning.message


def test_no_login_hint_without_a_web_interface():
    text = CONFIG.replace("[[plugin]]", "[web]\nenabled = false\nlogin = false\n[[plugin]]")
    assert config.parse(text).problems == []


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
        ('address = "0.0.0.0 "', "address: String should match pattern"),
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
    cfg.write_text(CONFIG.replace("[[plugin]]", "[web]\nport = 9000  # mine\n[[plugin]]"))
    before = cfg.read_text()
    web_password.save_password_hash(cfg, web_password.hash_password("correct horse"))
    assert main(["reset-password", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "removed the web password" in out and "set a new password" in out
    assert "reload signal: kill -HUP" in out  # the next step
    assert cfg.read_text() == before  # only the password line is gone
    assert config.parse(cfg.read_text()).web.password_hash is None
    assert main(["reset-password", "--config", str(cfg)]) == 0
    assert "no web password is set" in capsys.readouterr().out
