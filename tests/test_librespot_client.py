"""The librespot_client plugin: reading go-librespot's status, the pause timer, covers, the
"Find go-librespot" helper and drawing. No network, no go-librespot needed."""

import io
import json

import pytest
from epdlib import ScreenMode
from PIL import Image

import paperpi.plugins.librespot_client as spotify
from paperpi import webrequest
from paperpi.helper import Query, clean
from paperpi.plugin import Context, HelperProblem, State
from paperpi.plugins.librespot_client import (
    PLUGIN,
    Settings,
    Song,
    config_choice,
    fetch,
    find,
    running_config_folders,
)

COVER_URL = "https://i.scdn.co/image/ab67616d00001e02ee0d0dce888c6c8a70db6e8b"


def jpeg(side=64) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (side, side), "red").save(buffer, "JPEG")
    return buffer.getvalue()


def status(**changes):
    """go-librespot's answer while a song plays (shortened from a real one)."""
    track = {
        "album_cover_url": COVER_URL,
        "album_name": "This Is Happening",
        "artist_names": ["LCD Soundsystem"],
        "name": "Dance Yrself Clean",
        "uri": "spotify:track:2cmRpmO04TLaKPzmAzySYZ",
    } | changes.pop("track", {})
    return (
        {"device_name": "DevelPi-Spotify", "paused": False, "stopped": False}
        | {"track": track}
        | changes
    )


class FakeLibrespot:
    """Stands in for webrequest.get: ``answer`` is the /status JSON (``None``: 204, nobody
    connected), ``cover`` the cover's bytes (``None``: the download fails)."""

    def __init__(self, monkeypatch, answer=None, cover=None):
        self.answer = answer
        self.cover = cover
        self.urls = []
        monkeypatch.setattr(spotify.webrequest, "get", self)

    def __call__(self, url, **options):
        self.urls.append(url)
        if url.endswith("/status"):
            if self.answer is None:
                return webrequest.Answer(204, b"", {}, url)
            return webrequest.Answer(200, json.dumps(self.answer).encode(), {}, url)
        if url == COVER_URL and self.cover is not None:
            return webrequest.Answer(200, self.cover, {}, url)
        raise webrequest.WebError("i.scdn.co answered 404 Not Found")


def context(tmp_path, layout="two_column_three_row", low_disk=False, **settings):
    settings = Settings(**settings)
    return Context(settings, 400, 300, ScreenMode.gray(16), tmp_path, layout, low_disk=low_disk)


def test_a_playing_song_is_shown(tmp_path, monkeypatch):
    player = FakeLibrespot(monkeypatch, status(), jpeg())
    fetched = fetch(context(tmp_path, port=3678))
    assert fetched.state is State.READY
    assert fetched.data == Song(
        "Dance Yrself Clean", "LCD Soundsystem", "This Is Happening", jpeg()
    )
    assert player.urls == ["http://localhost:3678/status", COVER_URL]


def test_all_artists_are_named(tmp_path, monkeypatch):
    FakeLibrespot(monkeypatch, status(track={"artist_names": ["A", "B"]}), jpeg())
    assert fetch(context(tmp_path)).data.artist == "A, B"


@pytest.mark.parametrize(
    "answer", [None, status(stopped=True), {**status(), "track": None}, ["not", "a dict"]]
)
def test_nothing_when_nothing_plays(tmp_path, monkeypatch, answer):
    FakeLibrespot(monkeypatch, answer)
    (tmp_path / spotify.PAUSED).write_text("{}")
    assert fetch(context(tmp_path)).state is State.NOTHING
    assert not (tmp_path / spotify.PAUSED).exists()  # a new pause starts the timer again


def test_a_paused_song_stays_for_idle_timeout(tmp_path, monkeypatch):
    player = FakeLibrespot(monkeypatch, status(paused=True), jpeg())
    ctx = context(tmp_path, idle_timeout=10)
    assert fetch(ctx, clock=lambda: 1000).state is State.READY
    assert fetch(ctx, clock=lambda: 1010).state is State.READY
    assert fetch(ctx, clock=lambda: 1011).state is State.NOTHING
    player.answer = status()  # playing again
    assert fetch(ctx, clock=lambda: 1020).state is State.READY
    player.answer = status(paused=True)  # paused again: the timer starts again
    assert fetch(ctx, clock=lambda: 1030).state is State.READY
    assert fetch(ctx, clock=lambda: 1041).state is State.NOTHING


def test_another_paused_song_starts_the_timer_again(tmp_path, monkeypatch):
    player = FakeLibrespot(monkeypatch, status(paused=True), jpeg())
    ctx = context(tmp_path)
    fetch(ctx, clock=lambda: 1000)
    player.answer = status(paused=True, track={"uri": "spotify:track:other"})
    assert fetch(ctx, clock=lambda: 1050).state is State.READY


def test_a_clock_that_went_back_starts_the_timer_again(tmp_path, monkeypatch):
    FakeLibrespot(monkeypatch, status(paused=True), jpeg())
    ctx = context(tmp_path)
    fetch(ctx, clock=lambda: 5000)
    assert fetch(ctx, clock=lambda: 1000).state is State.READY
    assert fetch(ctx, clock=lambda: 1011).state is State.NOTHING


def test_a_damaged_pause_file_starts_the_timer_again(tmp_path, monkeypatch):
    FakeLibrespot(monkeypatch, status(paused=True), jpeg())
    (tmp_path / spotify.PAUSED).write_text("not json")
    assert fetch(context(tmp_path), clock=lambda: 1000).state is State.READY


def test_go_librespot_not_answering_is_a_failure(tmp_path, monkeypatch):
    def refuse(url, **options):
        raise webrequest.WebError("localhost refused the connection")

    monkeypatch.setattr(spotify.webrequest, "get", refuse)
    with pytest.raises(spotify.LibrespotError, match="does not answer on port 24879"):
        fetch(context(tmp_path))


def test_the_cover_is_downloaded_once(tmp_path, monkeypatch):
    player = FakeLibrespot(monkeypatch, status(), jpeg())
    fetch(context(tmp_path))
    assert fetch(context(tmp_path)).data.cover == jpeg()
    assert player.urls.count(COVER_URL) == 1


def test_the_cover_is_not_saved_when_the_disk_is_nearly_full(tmp_path, monkeypatch):
    player = FakeLibrespot(monkeypatch, status(), jpeg())
    assert fetch(context(tmp_path, low_disk=True)).data.cover == jpeg()
    fetch(context(tmp_path, low_disk=True))
    assert player.urls.count(COVER_URL) == 2


@pytest.mark.parametrize(
    ("url", "cover"),
    [
        (None, jpeg()),  # no cover
        ("file:///etc/passwd", jpeg()),  # not a web address
        (COVER_URL, None),  # the download fails
        (COVER_URL, b"<html>not a picture</html>"),
        (COVER_URL, jpeg()[:200]),  # damaged
    ],
)
def test_a_song_without_a_usable_cover_is_shown_without_it(tmp_path, monkeypatch, url, cover):
    FakeLibrespot(monkeypatch, status(track={"album_cover_url": url}), cover)
    fetched = fetch(context(tmp_path))
    assert fetched.state is State.READY
    assert fetched.data.cover is None
    assert not list(tmp_path.glob(f"*{spotify.COVER}"))


@pytest.mark.parametrize("layout", PLUGIN.layouts)
def test_draw_gives_each_block_of_the_layout(tmp_path, layout):
    for cover in (jpeg(), None):  # None: the record picture
        values = PLUGIN.draw(Song("Title", "Artist", "Album", cover), context(tmp_path, layout))
        blocks = PLUGIN.layout(layout, Settings()).blocks
        assert set(values) == set(blocks)
        if "cover" in values:
            assert isinstance(values["cover"], Image.Image)


# --- The "Find go-librespot" helper ----------------------------------------------------------


def write_config(folder, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "config.yml").write_text(text)
    return folder / "config.yml"


CONFIG = "device_name: Kitchen\nserver:\n  enabled: true\n  port: 3678\n"


def test_running_config_folders(tmp_path):
    for number, words in enumerate(
        [
            ["/usr/local/bin/go-librespot-daemon", "--config_dir", "/var/lib/go-librespot"],
            ["go-librespot", "--config_dir=/srv/spotify"],
            ["/usr/bin/python3", "--config_dir", "/not/this/one"],
            ["go-librespot", "--config_dir"],  # no folder after it
            ["go-librespot", "--config_dir="],
        ]
    ):
        (tmp_path / str(number)).mkdir()
        (tmp_path / str(number) / "cmdline").write_bytes("\0".join(words).encode() + b"\0")
    (tmp_path / "self").mkdir()  # not a program number
    found = sorted(str(path) for path in running_config_folders(tmp_path))
    assert found == ["/srv/spotify", "/var/lib/go-librespot"]


def test_helper_fills_the_port(tmp_path):
    choice = config_choice(write_config(tmp_path, CONFIG), answers=lambda port: port == 3678)
    assert choice["fill"] == {"port": 3678}
    assert choice["show"]["Player"] == "Kitchen"
    assert choice["show"]["Answers now"] == "yes"


def test_helper_says_when_nothing_answers(tmp_path):
    choice = config_choice(write_config(tmp_path, CONFIG), answers=lambda port: False)
    assert choice["show"]["Answers now"].startswith("no")
    assert choice["fill"] == {"port": 3678}


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("device_name: Kitchen\n", "API server is off"),
        ("server:\n  enabled: false\n  port: 3678\n", "API server is off"),
        ("server:\n  enabled: true\n", "API server is off"),  # no port
        ("server:\n  enabled: true\n  port: 0\n", "API server is off"),
        ("server: [1, 2]\n", "API server is off"),
        ("server:\n  enabled: true\n  port: 3678\n  address: 192.0.2.7\n", "only on 192.0.2.7"),
        ("server:\n  enabled: true\n  port: 3678\n  cert_file: /x.pem\n", "https"),
        ("server: [unclosed\n", "can't be read"),
    ],
)
def test_helper_explains_a_config_it_cant_use(tmp_path, text, problem):
    choice = config_choice(write_config(tmp_path, text), answers=lambda port: True)
    assert problem in choice["show"]["Problem"]
    assert "Answers now" not in choice["show"]


def test_helper_skips_missing_files(tmp_path):
    assert config_choice(tmp_path / "config.yml", answers=lambda port: True) is None


def test_find_reads_running_and_usual_folders_once(tmp_path, monkeypatch):
    running = tmp_path / "running"
    usual = tmp_path / "usual"
    write_config(running, CONFIG)
    write_config(usual, CONFIG.replace("3678", "24879"))
    monkeypatch.setattr(spotify, "CONFIG_FOLDERS", (usual, running))
    monkeypatch.setattr(spotify, "_answers", lambda port: True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    found = clean(find(Query("", Settings()), folders=lambda: [running]), ["port"])
    assert [choice.fill for choice in found.choices] == [{"port": 3678}, {"port": 24879}]


def test_find_without_any_config(tmp_path, monkeypatch):
    monkeypatch.setattr(spotify, "CONFIG_FOLDERS", ())
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(HelperProblem, match="No go-librespot config.yml"):
        find(Query("", Settings()), folders=lambda: [])
