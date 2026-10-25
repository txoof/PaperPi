"""lms_client: the song a Lyrion Music Server (LMS) player is playing."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw, UnidentifiedImageError
from pydantic import Field, SecretStr

from ... import limits, webrequest
from ...files import write_atomic
from ...plugin import (
    NOTHING,
    Context,
    Helper,
    HelperProblem,
    Plugin,
    PluginSettings,
    Query,
    ready,
    setting,
)
from .layouts import LAYOUTS

log = logging.getLogger(__name__)

#: LMS's web port when the address has none.
PORT = 9000
#: LMS servers answer a "who is there" message on this UDP port (see :func:`discover`).
DISCOVERY_PORT = 3483
DISCOVERY = b"eNAME\0JSON\0VERS\0"
#: The tags asked for in "status": artist, album, coverid, artwork_url, remote, remote_title.
TAGS = "tags:alcKxN"
#: Remembers when the song was paused, between updates (each update is a new process).
PAUSED = "paused.json"
COVER = ".cover"
COVER_SIZE = "cover_500x500_m.jpg"
COVER_BYTES = 2_000_000
FORMATS = ("JPEG", "PNG")
MAX_SIDE = 3000
SAMPLE = Path(__file__).parent / "sample" / "cover.png"


class Settings(PluginSettings):
    server: str = setting(
        "",
        required=True,
        helper="find",
        max_length=255,
        pattern=r"^$|^[A-Za-z0-9.\-\[\]:]+$",
        description="Address of the LMS server, with its web port, e.g. 192.168.1.9:9000",
    )
    player: str = setting(
        "",
        required=True,
        max_length=100,
        description="Name of the player, as LMS shows it, e.g. Kitchen",
    )
    user: str = setting(
        "",
        group="Login",
        max_length=100,
        description="User name, only when the LMS server has a password",
    )
    password: SecretStr = setting(
        SecretStr(""), group="Login", description="Password, only when the LMS server has one"
    )
    idle_timeout: float = Field(
        15,
        ge=0,
        le=limits.LONGEST_SETTING,
        description="Seconds a paused song stays on the screen before other plugins are shown",
    )


@dataclass(frozen=True)
class Song:
    """What ``draw`` gets. ``cover`` is the picture file's content, a path (only for the
    sample), or ``None`` when the song has no cover."""

    title: str
    artist: str
    album: str
    cover: bytes | Path | None


class LMSError(RuntimeError):
    pass


# --- Talking to LMS --------------------------------------------------------------------------


def base_url(server: str) -> str:
    """``http://host:port`` for a server setting such as ``192.168.1.9`` or ``lms:9000``."""
    server = server.strip().removeprefix("http://").rstrip("/")
    host, _, port = server.rpartition(":")
    if not host or not port.isdigit() or (":" in host and not host.startswith("[")):
        host, port = server, str(PORT)  # no port, or an IPv6 address without brackets
    return f"http://{host}:{port}"


def _auth(settings: Settings) -> dict[str, str]:
    """HTTP basic auth (user name and password in a header), when a password is set."""
    password = settings.password.get_secret_value()
    if not settings.user and not password:
        return {}
    token = base64.b64encode(f"{settings.user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def rpc(base: str, player_id: str, command: list, headers: dict[str, str]) -> dict:
    """One LMS JSON-RPC request; its ``result``. Raises :class:`LMSError`."""
    request = {"id": 1, "method": "slim.request", "params": [player_id, command]}
    try:
        answer = webrequest.post(
            f"{base}/jsonrpc.js", json.dumps(request).encode(), headers=headers
        )
        result = answer.json().get("result")
    except webrequest.WebError as error:
        if " 401 " in str(error):
            raise LMSError(
                f"LMS at {base} asks for a user name and password (user and password settings)"
            ) from None
        raise LMSError(f"LMS at {base} does not answer: {error}") from None
    except AttributeError:  # the JSON is not a dictionary
        result = None
    if not isinstance(result, dict):
        raise LMSError(f"LMS at {base} sent no result for {command[0]}")
    return result


def players(base: str, headers: dict[str, str]) -> list[dict]:
    loop = rpc(base, "", ["players", 0, 999], headers).get("players_loop")
    return [p for p in loop if isinstance(p, dict)] if isinstance(loop, list) else []


# --- Fetch -----------------------------------------------------------------------------------


def fetch(context: Context, clock: Callable[[], float] = time.time):
    """The song the player is playing, or paused less than ``idle_timeout`` seconds ago.
    Nothing when it plays nothing. ``clock`` is for tests."""
    settings = context.settings
    base, headers = base_url(settings.server), _auth(settings)
    found = players(base, headers)
    wanted = settings.player.strip().casefold()
    player = next((p for p in found if str(p.get("name", "")).casefold() == wanted), None)
    if player is None:
        names = ", ".join(sorted(str(p.get("name")) for p in found)) or "none"
        raise LMSError(f'LMS has no player called "{settings.player}" (its players: {names})')
    status = rpc(base, str(player.get("playerid", "")), ["status", "-", 1, TAGS], headers)
    loop = status.get("playlist_loop")
    track = loop[0] if isinstance(loop, list) and loop and isinstance(loop[0], dict) else None
    mode = status.get("mode")
    if track is None or mode not in ("play", "pause"):  # stopped, or switched off
        _forget_pause(context.storage)
        return NOTHING
    key = str(track.get("id") or track.get("url") or track.get("title"))
    if mode == "pause" and _paused_too_long(context, key, clock()):
        return NOTHING
    if mode == "play":
        _forget_pause(context.storage)
    station = str(track.get("remote_title") or status.get("remote_title") or "")
    return ready(
        Song(
            title=str(track.get("title") or status.get("current_title") or ""),
            artist=str(track.get("artist") or station),
            album=str(track.get("album") or ""),
            cover=cover_for(_cover_url(base, track), context, headers),
        )
    )


def _cover_url(base: str, track: dict) -> str | None:
    """The cover's address: from LMS's cover store for songs in its library, else the
    ``artwork_url`` (for radio; LMS often gives a path on itself)."""
    remote = str(track.get("remote", "0")) == "1"  # LMS sends "0" or 1
    if not remote and track.get("coverid"):
        return f"{base}/music/{quote(str(track['coverid']), safe='')}/{COVER_SIZE}"
    url = track.get("artwork_url")
    if not isinstance(url, str) or not url:
        return None
    if url.startswith("/"):
        return base + url
    return url if url.startswith(("https://", "http://")) else None


def _paused_too_long(context: Context, key: str, now: float) -> bool:
    """True when this song was paused more than ``idle_timeout`` seconds ago. The first
    update that sees it paused saves the time."""
    path = context.storage / PAUSED
    try:
        saved = json.loads(path.read_bytes())
        since = float(saved["since"]) if saved["song"] == key else None
    except (OSError, ValueError, TypeError, KeyError):
        since = None
    if since is None or since > now:  # not seen paused before, or the clock went back
        try:
            write_atomic(path, json.dumps({"song": key, "since": now}).encode(), durable=False)
        except OSError as error:
            log.warning("can't save when the song was paused: %s", error)
        return False
    return now - since > context.settings.idle_timeout


def _forget_pause(storage: Path) -> None:
    (storage / PAUSED).unlink(missing_ok=True)


def cover_for(url: str | None, context: Context, headers: dict[str, str]) -> bytes | None:
    """The album cover, from storage or downloaded (and then saved, unless the disk is
    nearly full). ``None`` when there is none or it can't be used: the song is shown
    without it. ``headers`` (the password) go only to the LMS server itself."""
    if url is None:
        return None
    # Named after its address, so the address can't choose a path.
    path = context.storage / (hashlib.sha256(url.encode()).hexdigest()[:24] + COVER)
    try:
        image = path.read_bytes()
    except OSError:
        image = b""
    if usable(image):
        return image
    own = url.startswith(base_url(context.settings.server) + "/")
    try:
        image = webrequest.get(url, headers=headers if own else None, max_bytes=COVER_BYTES).body
    except webrequest.WebError as error:
        log.info("can't download the album cover, showing the song without it: %s", error)
        return None
    if not usable(image):
        log.info("the album cover is not a JPEG or PNG file, or is damaged: %s", url)
        return None
    if not context.low_disk:
        try:
            write_atomic(path, image, durable=False)
        except OSError as error:
            log.warning("can't save the album cover, showing it anyway: %s", error)
    return image


def usable(image: bytes) -> bool:
    """True for a JPEG or PNG picture of at most MAX_SIDE x MAX_SIDE pixels that decodes."""
    try:
        with Image.open(io.BytesIO(image), formats=FORMATS) as picture:
            if max(picture.size) > MAX_SIDE:  # read from the header, before decoding
                return False
            picture.load()  # decodes it all, so a damaged file is found here, not in draw
        return True
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return False


# --- Drawing ---------------------------------------------------------------------------------


def no_cover(side: int = 300) -> Image.Image:
    """A plain picture of a record, for songs without a cover."""
    picture = Image.new("L", (side, side), 255)
    pen = ImageDraw.Draw(picture)
    pen.ellipse((side * 0.1, side * 0.1, side * 0.9, side * 0.9), fill=60)
    pen.ellipse((side * 0.38, side * 0.38, side * 0.62, side * 0.62), fill=200)
    pen.ellipse((side * 0.47, side * 0.47, side * 0.53, side * 0.53), fill=255)
    return picture


def draw(song: Song, context: Context) -> dict:
    layout = PLUGIN.layout(context.layout, context.settings)
    if song.cover is None:
        cover = no_cover()
    else:
        cover = Image.open(io.BytesIO(song.cover) if isinstance(song.cover, bytes) else song.cover)
        cover.load()
    values = {"cover": cover, "title": song.title, "artist": song.artist, "album": song.album}
    return {name: value for name, value in values.items() if name in layout.blocks}


# --- The "Find players" helper ---------------------------------------------------------------


def parse_discovery(reply: bytes) -> dict[str, str]:
    """An LMS server's answer to :data:`DISCOVERY`: ``E`` and then, for each field, a
    4-letter name, 1 byte with the length, and the value. E.g. ``{"NAME": "media-server",
    "JSON": "9000"}``. Empty for anything else."""
    if not reply.startswith(b"E"):
        return {}
    fields, at = {}, 1
    while at + 5 <= len(reply):
        name, length = reply[at : at + 4], reply[at + 4]
        fields[name.decode(errors="replace")] = reply[at + 5 : at + 5 + length].decode(
            errors="replace"
        )
        at += 5 + length
    return fields


def discover(
    wait: float = 2, to: tuple[str, int] = ("255.255.255.255", DISCOVERY_PORT)
) -> list[tuple[str, str]]:
    """The LMS servers on the local network that answer within ``wait`` seconds, as
    (``host:port``, name), found the way LMS players find them: a UDP broadcast."""
    servers: dict[str, str] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.sendto(DISCOVERY, to)
        except OSError as error:  # e.g. no network
            log.info("can't look for LMS servers: %s", error)
            return []
        end = time.monotonic() + wait
        while (left := end - time.monotonic()) > 0:
            sock.settimeout(left)
            try:
                reply, (host, _) = sock.recvfrom(1500)
            except (TimeoutError, OSError):
                break
            fields = parse_discovery(reply)
            port = fields.get("JSON", "")
            if port.isdigit():
                servers[f"{host}:{port}"] = fields.get("NAME") or host
    return sorted(servers.items())


def _state(player: dict) -> str:
    if not player.get("connected"):
        return "not connected"
    if not player.get("power"):
        return "switched off"
    return "playing" if player.get("isplaying") else "on, not playing"


def find(query: Query, servers: Callable[[], list[tuple[str, str]]] = discover) -> dict:
    """Every player of every LMS server found on the network, and of the server in the
    form (for a server the broadcast can't reach, e.g. in another network)."""
    found = dict(servers())
    typed = query.settings.server.strip()
    if typed and not any(base_url(s) == base_url(typed) for s in found):
        found[typed] = typed
    if not found:
        raise HelperProblem(
            "No LMS server answered on the local network. Is it running? You can also type "
            "its address (e.g. 192.168.1.9:9000) and search again."
        )
    choices, problems = [], []
    for server, name in found.items():
        try:
            listed = players(base_url(server), _auth(query.settings))
        except LMSError as error:
            problems.append(str(error))
            continue
        for player in listed:
            show = {
                "Player": str(player.get("name") or "?"),
                "Server": name if name == server else f"{name} ({server})",
                "Model": str(player.get("modelname") or player.get("model") or "?"),
                "State": _state(player),
            }
            choices.append({"show": show, "fill": {"server": server, "player": show["Player"]}})
    if not choices and not problems:
        problems.append("The LMS server has no players. Start a player, then search again.")
    return {"choices": choices, "note": " ".join(problems)}


PLUGIN = Plugin(
    type="lms_client",
    title="Music server (LMS)",
    network="home",
    setup=(
        "Needs a Lyrion Music Server (LMS) on your home network, and the name "
        "of one of its players."
    ),
    description="The song a Lyrion Music Server (LMS) player is playing, with its cover. "
    "Shown only while music plays (interrupt); the other plugins are shown when it stops.",
    settings=Settings,
    layouts=LAYOUTS,
    layout_titles={
        "two_column_three_row": "Cover, artist, album and title",
        "album_art_title": "Cover and title",
        "cover_art_only": "Cover only",
        "two_rows_text_only": "Title and artist",
        "three_rows_text_only": "Title, artist and album",
    },
    fetch=fetch,
    draw=draw,
    sample=Song("Night Train to the Coast", "The Paper Orchestra", "Late Signals", SAMPLE),
    refresh=5,
    level="interrupt",
    helpers={
        "find": Helper(
            find,
            prompt="Look for LMS servers and their players on the local network",
            button="Find players",
            typed=False,
        )
    },
)
