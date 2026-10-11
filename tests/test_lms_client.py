"""The lms_client plugin: finding the player, reading its status, the pause timer, covers,
the "Find players" helper and drawing. No network, no LMS server needed."""

import base64
import io
import json
import socket
import threading

import pytest
from epdlib import ScreenMode
from PIL import Image

import paperpi.plugins.lms_client as lms
from paperpi import webrequest
from paperpi.helper import Query, clean
from paperpi.plugin import Context, HelperProblem, State
from paperpi.plugins.lms_client import (
    PLUGIN,
    Settings,
    Song,
    base_url,
    discover,
    fetch,
    find,
    parse_discovery,
)

BASE = "http://192.168.1.9:9000"
PLAYER_ID = "dc:a6:32:26:b9:ac"
COVER_URL = f"{BASE}/music/e2a2fa91/cover_500x500_m.jpg"


def jpeg(side=64) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (side, side), "red").save(buffer, "JPEG")
    return buffer.getvalue()


def track(**changes):
    """A song from LMS's library (shortened from a real status answer)."""
    return {
        "id": 3005,
        "title": "Robot Rock / Oh Yeah",
        "artist": "Daft Punk",
        "album": "Alive 2007",
        "coverid": "e2a2fa91",
        "remote": "0",
    } | changes


def status(mode="play", **changes):
    return {"mode": mode, "player_name": "develpi-4", "playlist_loop": [track()]} | changes


PLAYERS = [
    {"name": "develpi-4", "playerid": PLAYER_ID, "modelname": "SqueezeLite", "connected": 1,
     "power": 1, "isplaying": 1},
    {"name": "Kitchen", "playerid": "aa:bb", "modelname": "Squeezebox Radio", "connected": 1,
     "power": 0, "isplaying": 0},
]  # fmt: skip


class FakeLMS:
    """Stands in for webrequest: ``status`` is the player's status result, ``cover`` the
    cover's bytes (``None``: the download fails), ``refuse``: answer 401."""

    def __init__(self, monkeypatch, status=None, cover=None, players=PLAYERS, refuse=False):
        self.status, self.cover, self.players, self.refuse = status, cover, players, refuse
        self.calls = []  # (player id, command) of every JSON-RPC request
        self.gets = []  # (url, headers) of every download
        monkeypatch.setattr(lms.webrequest, "post", self.post)
        monkeypatch.setattr(lms.webrequest, "get", self.get)

    def post(self, url, data, headers=None, **options):
        if self.refuse:
            raise webrequest.WebError(f"{url} answered 401 Unauthorized")
        player_id, command = json.loads(data)["params"]
        self.calls.append((player_id, command))
        if command[0] == "players":
            result = {"count": len(self.players), "players_loop": self.players}
        else:
            result = self.status
        return webrequest.Answer(200, json.dumps({"result": result}).encode(), {}, url)

    def get(self, url, headers=None, **options):
        self.gets.append((url, headers))
        if self.cover is None:
            raise webrequest.WebError("192.168.1.9 answered 404 Not Found")
        return webrequest.Answer(200, self.cover, {}, url)


def context(tmp_path, layout="two_column_three_row", low_disk=False, **settings):
    settings = Settings(**({"server": "192.168.1.9:9000", "player": "develpi-4"} | settings))
    return Context(settings, 400, 300, ScreenMode.gray(16), tmp_path, layout, low_disk=low_disk)


@pytest.mark.parametrize(
    ("server", "base"),
    [
        ("192.168.1.9:9000", BASE),
        ("192.168.1.9", BASE),
        ("lms.local:9002", "http://lms.local:9002"),
        ("[fd00::9]:9000", "http://[fd00::9]:9000"),
    ],
)
def test_base_url(server, base):
    assert base_url(server) == base


def test_a_playing_song_is_shown(tmp_path, monkeypatch):
    server = FakeLMS(monkeypatch, status(), jpeg())
    fetched = fetch(context(tmp_path, player="DevelPi-4"))  # any upper or lower case
    assert fetched.state is State.READY
    assert fetched.data == Song("Robot Rock / Oh Yeah", "Daft Punk", "Alive 2007", jpeg())
    assert server.calls == [("", ["players", 0, 999]), (PLAYER_ID, ["status", "-", 1, lms.TAGS])]
    assert server.gets == [(COVER_URL, {})]


def test_radio_shows_the_station_and_its_artwork(tmp_path, monkeypatch):
    radio = track(
        remote=1, artist="", album="", coverid="-1", remote_title="Radio Berlin",
        artwork_url="/imageproxy/https%3A%2F%2Fexample.org%2Flogo.png/image.png",
    )  # fmt: skip
    server = FakeLMS(monkeypatch, status(playlist_loop=[radio]), jpeg())
    song = fetch(context(tmp_path)).data
    assert (song.title, song.artist) == ("Robot Rock / Oh Yeah", "Radio Berlin")
    assert server.gets[0][0] == BASE + radio["artwork_url"]


def test_the_password_is_sent_only_to_the_lms_server(tmp_path, monkeypatch):
    outside = track(remote=1, artwork_url="https://example.org/logo.png")
    server = FakeLMS(monkeypatch, status(playlist_loop=[outside]), jpeg())
    fetch(context(tmp_path, user="me", password="secret"))
    assert server.gets == [("https://example.org/logo.png", None)]
    server.status = status()
    fetch(context(tmp_path, user="me", password="secret"))
    token = base64.b64encode(b"me:secret").decode()
    assert server.gets[1] == (COVER_URL, {"Authorization": f"Basic {token}"})


@pytest.mark.parametrize(
    "answer", [status("stop"), status(playlist_loop=[]), {"mode": "play"}, status("off")]
)
def test_nothing_when_nothing_plays(tmp_path, monkeypatch, answer):
    FakeLMS(monkeypatch, answer, jpeg())
    (tmp_path / lms.PAUSED).write_text("{}")
    assert fetch(context(tmp_path)).state is State.NOTHING
    assert not (tmp_path / lms.PAUSED).exists()


def test_a_paused_song_stays_for_idle_timeout(tmp_path, monkeypatch):
    server = FakeLMS(monkeypatch, status("pause"), jpeg())
    ctx = context(tmp_path, idle_timeout=15)
    assert fetch(ctx, clock=lambda: 1000).state is State.READY
    assert fetch(ctx, clock=lambda: 1015).state is State.READY
    assert fetch(ctx, clock=lambda: 1016).state is State.NOTHING
    server.status = status()  # playing again
    assert fetch(ctx, clock=lambda: 1020).state is State.READY
    server.status = status("pause", playlist_loop=[track(id=7)])  # another song paused
    assert fetch(ctx, clock=lambda: 1030).state is State.READY
    assert fetch(ctx, clock=lambda: 1046).state is State.NOTHING


def test_a_clock_that_went_back_starts_the_timer_again(tmp_path, monkeypatch):
    FakeLMS(monkeypatch, status("pause"), jpeg())
    ctx = context(tmp_path)
    fetch(ctx, clock=lambda: 5000)
    assert fetch(ctx, clock=lambda: 1000).state is State.READY


def test_an_unknown_player_is_a_failure(tmp_path, monkeypatch):
    FakeLMS(monkeypatch, status())
    with pytest.raises(lms.LMSError, match='no player called "Garage".*Kitchen, develpi-4'):
        fetch(context(tmp_path, player="Garage"))


def test_a_password_is_asked_for(tmp_path, monkeypatch):
    FakeLMS(monkeypatch, refuse=True)
    with pytest.raises(lms.LMSError, match="asks for a user name and password"):
        fetch(context(tmp_path))


@pytest.mark.parametrize("body", [b"[1, 2]", b'{"result": "x"}', b"{}"])
def test_a_strange_answer_is_a_failure(tmp_path, monkeypatch, body):
    monkeypatch.setattr(
        lms.webrequest, "post", lambda url, data, **o: webrequest.Answer(200, body, {}, url)
    )
    with pytest.raises(lms.LMSError, match="sent no result"):
        fetch(context(tmp_path))


def test_lms_not_answering_is_a_failure(tmp_path, monkeypatch):
    def refuse(url, data, **options):
        raise webrequest.WebError("could not reach 192.168.1.9")

    monkeypatch.setattr(lms.webrequest, "post", refuse)
    with pytest.raises(lms.LMSError, match="does not answer"):
        fetch(context(tmp_path))


def test_the_cover_is_downloaded_once(tmp_path, monkeypatch):
    server = FakeLMS(monkeypatch, status(), jpeg())
    fetch(context(tmp_path))
    assert fetch(context(tmp_path)).data.cover == jpeg()
    assert len(server.gets) == 1


def test_the_cover_is_not_saved_when_the_disk_is_nearly_full(tmp_path, monkeypatch):
    server = FakeLMS(monkeypatch, status(), jpeg())
    fetch(context(tmp_path, low_disk=True))
    fetch(context(tmp_path, low_disk=True))
    assert len(server.gets) == 2


@pytest.mark.parametrize(
    ("song", "cover"),
    [
        (track(coverid=None), jpeg()),  # no cover
        (track(remote=1, artwork_url="file:///etc/passwd"), jpeg()),  # not a web address
        (track(), None),  # the download fails
        (track(), b"<html>not a picture</html>"),
        (track(), jpeg()[:200]),  # damaged
    ],
)
def test_a_song_without_a_usable_cover_is_shown_without_it(tmp_path, monkeypatch, song, cover):
    FakeLMS(monkeypatch, status(playlist_loop=[song]), cover)
    fetched = fetch(context(tmp_path))
    assert fetched.state is State.READY
    assert fetched.data.cover is None
    assert not list(tmp_path.glob(f"*{lms.COVER}"))


@pytest.mark.parametrize("layout", PLUGIN.layouts)
def test_draw_gives_each_block_of_the_layout(tmp_path, layout):
    for cover in (jpeg(), None):  # None: the record picture
        values = PLUGIN.draw(Song("Title", "Artist", "Album", cover), context(tmp_path, layout))
        assert set(values) == set(PLUGIN.layout(layout, Settings()).blocks)


# --- The "Find players" helper ---------------------------------------------------------------


def test_parse_discovery():
    reply = b"ENAME\x0cmedia-serverJSON\x049000VERS\x059.1.1"
    assert parse_discovery(reply) == {"NAME": "media-server", "JSON": "9000", "VERS": "9.1.1"}
    assert parse_discovery(b"ENAME\x20short") == {"NAME": "short"}  # a length too long
    assert parse_discovery(b"D old format") == {}


def test_discover_on_this_computer():
    """A pretend LMS server on 127.0.0.1 answers the discovery message."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as lms_server:
        lms_server.bind(("127.0.0.1", 0))

        def answer():
            message, sender = lms_server.recvfrom(100)
            assert message == lms.DISCOVERY
            lms_server.sendto(b"ENAME\x03denJSON\x049002", sender)

        thread = threading.Thread(target=answer)
        thread.start()
        found = discover(wait=2, to=lms_server.getsockname())
        thread.join()
    assert found == [("127.0.0.1:9002", "den")]


def test_find_lists_every_player(tmp_path, monkeypatch):
    FakeLMS(monkeypatch)
    result = find(Query("", Settings()), servers=lambda: [("192.168.1.9:9000", "media-server")])
    found = clean(result, ["server", "player"])
    assert [c.fill for c in found.choices] == [
        {"server": "192.168.1.9:9000", "player": "develpi-4"},
        {"server": "192.168.1.9:9000", "player": "Kitchen"},
    ]
    assert dict(found.choices[0].show)["Server"] == "media-server (192.168.1.9:9000)"
    assert [dict(c.show)["State"] for c in found.choices] == ["playing", "switched off"]


def test_find_also_asks_the_server_in_the_form(monkeypatch):
    server = FakeLMS(monkeypatch)
    find(Query("", Settings(server="10.0.0.5")), servers=lambda: [])
    assert server.calls == [("", ["players", 0, 999])]
    server.calls.clear()  # the same server as one found: asked once
    find(Query("", Settings(server="192.168.1.9")), servers=lambda: [("192.168.1.9:9000", "x")])
    assert len(server.calls) == 1


def test_find_says_when_a_password_is_needed(monkeypatch):
    FakeLMS(monkeypatch, refuse=True)
    result = find(Query("", Settings()), servers=lambda: [("192.168.1.9:9000", "media-server")])
    assert result["choices"] == [] and "user name and password" in result["note"]


def test_find_without_servers():
    with pytest.raises(HelperProblem, match="No LMS server answered"):
        find(Query("", Settings()), servers=lambda: [])
