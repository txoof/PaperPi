"""librespot_client: the song Spotify is playing on this device, through go-librespot."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, UnidentifiedImageError
from pydantic import Field

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

#: go-librespot's API server only listens on this device unless its config says otherwise.
HOST = "localhost"
#: The port in PaperPi v1's example config; go-librespot itself has no default port.
PORT = 24879
#: Remembers when the song was paused, between updates (each update is a new process).
PAUSED = "paused.json"
COVER = ".cover"
COVER_BYTES = 2_000_000
FORMATS = ("JPEG", "PNG")
MAX_SIDE = 3000
#: Where go-librespot's config.yml is often kept, after the folder of a running go-librespot
#: (and go-librespot's own default, ``~/.config/go-librespot``).
CONFIG_FOLDERS = (Path("/var/lib/go-librespot"),)
#: Addresses at which go-librespot's API server can be reached as ``localhost``.
LOCAL = ("", "localhost", "127.0.0.1", "::1", "0.0.0.0", "::")
SAMPLE = Path(__file__).parent / "sample" / "cover.png"


class Settings(PluginSettings):
    port: int = setting(
        PORT,
        ge=1,
        le=65535,
        helper="find",
        description="Port of go-librespot's API server: server.port in its config.yml",
    )
    idle_timeout: float = Field(
        10,
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


class LibrespotError(RuntimeError):
    pass


def fetch(context: Context, clock: Callable[[], float] = time.time):
    """The song that is playing, or that was paused less than ``idle_timeout`` seconds ago.
    Nothing when go-librespot plays nothing. ``clock`` is for tests."""
    port = context.settings.port
    try:
        answer = webrequest.get(f"http://{HOST}:{port}/status")
    except webrequest.WebError as error:
        raise LibrespotError(f"go-librespot does not answer on port {port}: {error}") from None
    status = answer.json() if answer.status == 200 else None  # 204: nobody is connected
    track = status.get("track") if isinstance(status, dict) else None
    if not isinstance(track, dict) or status.get("stopped"):
        _forget_pause(context.storage)
        return NOTHING
    if status.get("paused") and _paused_too_long(context, str(track.get("uri")), clock()):
        return NOTHING
    if not status.get("paused"):
        _forget_pause(context.storage)
    artists = track.get("artist_names") or []
    return ready(
        Song(
            title=str(track.get("name") or ""),
            artist=", ".join(str(name) for name in artists),
            album=str(track.get("album_name") or ""),
            cover=cover_for(track.get("album_cover_url"), context),
        )
    )


def _paused_too_long(context: Context, uri: str, now: float) -> bool:
    """True when this song was paused more than ``idle_timeout`` seconds ago. The first
    update that sees it paused saves the time."""
    path = context.storage / PAUSED
    try:
        saved = json.loads(path.read_bytes())
        since = float(saved["since"]) if saved["uri"] == uri else None
    except (OSError, ValueError, TypeError, KeyError):
        since = None
    if since is None or since > now:  # not seen paused before, or the clock went back
        try:
            write_atomic(path, json.dumps({"uri": uri, "since": now}).encode(), durable=False)
        except OSError as error:
            log.warning("can't save when the song was paused: %s", error)
        return False
    return now - since > context.settings.idle_timeout


def _forget_pause(storage: Path) -> None:
    (storage / PAUSED).unlink(missing_ok=True)


def cover_for(url, context: Context) -> bytes | None:
    """The album cover, from storage or downloaded (and then saved, unless the disk is
    nearly full). ``None`` when there is none or it can't be used: the song is shown
    without it."""
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return None
    # Named after its address, so the address can't choose a path.
    path = context.storage / (hashlib.sha256(url.encode()).hexdigest()[:24] + COVER)
    try:
        image = path.read_bytes()
    except OSError:
        image = b""
    if usable(image):
        return image
    try:
        image = webrequest.get(url, max_bytes=COVER_BYTES).body
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


# --- The "Find go-librespot" helper ----------------------------------------------------------


def running_config_folders(proc: Path = Path("/proc")) -> list[Path]:
    """The ``--config_dir`` of every go-librespot program running on this device (every
    user may read a program's command line in ``/proc``)."""
    folders = []
    for cmdline in proc.glob("[0-9]*/cmdline"):
        try:
            words = [w for w in cmdline.read_bytes().decode(errors="replace").split("\0") if w]
        except OSError:  # the program ended
            continue
        if not words or not Path(words[0]).name.startswith("go-librespot"):
            continue
        for number, word in enumerate(words):
            if word.startswith(("--config_dir=", "-config_dir=")) and word.split("=", 1)[1]:
                folders.append(Path(word.split("=", 1)[1]))
            elif word in ("--config_dir", "-config_dir") and number + 1 < len(words):
                folders.append(Path(words[number + 1]))
    return folders


def config_choice(path: Path, answers: Callable[[int], bool]) -> dict | None:
    """A helper choice for one go-librespot config.yml, or ``None`` when there is no such
    file. ``answers(port)`` says whether something answers on that port now."""
    try:
        config = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        return {"show": {"Config file": str(path), "Problem": f"can't be read: {error}"}}
    config = config if isinstance(config, dict) else {}
    server = config.get("server") if isinstance(config.get("server"), dict) else {}
    show = {"Player": str(config.get("device_name") or "go-librespot"), "Config file": str(path)}
    port = server.get("port")
    if not server.get("enabled") or not isinstance(port, int) or not 0 < port < 65536:
        show["Problem"] = (
            "its API server is off: set server: enabled: true and a port (e.g. 24879) in "
            "this file, then restart go-librespot"
        )
        return {"show": show}
    show["Port"] = str(port)
    address = str(server.get("address") or "")
    if address not in LOCAL:
        show["Problem"] = f"its API server listens only on {address}, not on {HOST}"
    elif server.get("cert_file"):
        show["Problem"] = "its API server uses https (cert_file), which this plugin can't read"
    else:
        show["Answers now"] = "yes" if answers(port) else "no: is go-librespot running?"
    return {"show": show, "fill": {"port": port}}


def _answers(port: int) -> bool:
    try:
        webrequest.get(f"http://{HOST}:{port}/", connect_timeout=2, total=3)
    except webrequest.WebError:
        return False
    return True


def find(query: Query, folders: Callable[[], list[Path]] = running_config_folders) -> list:
    """The ``config.yml`` of the go-librespot programs that run now, then the usual places."""
    try:
        home = [Path.home() / ".config" / "go-librespot"]
    except RuntimeError:  # no home folder, e.g. for some service users
        home = []
    paths = []
    for folder in [*folders(), *CONFIG_FOLDERS, *home]:
        path = folder / "config.yml"
        if path not in paths:
            paths.append(path)
    choices = [choice for path in paths if (choice := config_choice(path, _answers))]
    if not choices:
        raise HelperProblem(
            "No go-librespot config.yml found on this device. Is go-librespot installed and "
            "running? You can also type its port (server.port in its config.yml)."
        )
    return choices


PLUGIN = Plugin(
    type="librespot_client",
    title="Spotify",
    network="internet",
    description="The song Spotify is playing on this device, with its album cover. "
    "Shown only while music plays (interrupt); the other plugins are shown when it stops.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=Song(
        "Morning Light Over the Harbour", "The Sample Band", "Songs for Paper Screens", SAMPLE
    ),
    refresh=10,
    level="interrupt",
    helpers={
        "find": Helper(
            find,
            prompt="Read the port from go-librespot's config.yml on this device",
            button="Find go-librespot",
            typed=False,
        )
    },
)
