"""Read the system's numbers straight from the files Linux provides.

Every reader takes ``root``, the folder that stands for ``/``, so tests can point it at a
folder of made-up files. A reader that can't get its number returns ``None``; the plugin
then shows "?" for it instead of failing.
"""

from __future__ import annotations

import os
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

ROOT = Path("/")


@dataclass(frozen=True)
class Info:
    """Everything system_info shows. Percentages are 0-100."""

    hostname: str | None
    ip: str | None
    wifi: int | None  # link quality in %, None when not on Wi-Fi
    disk_used: int | None  # bytes
    disk_total: int | None  # bytes
    temperature: float | None  # °C
    load: tuple[float, float, float] | None  # 1, 5, 15 minutes, % of all cores together
    memory: float | None  # % used
    uptime: float | None  # seconds
    version: str
    time: str  # "09:04"


def _text(root: Path, path: str) -> str | None:
    try:
        return (root / path).read_text()
    except (OSError, UnicodeDecodeError):
        return None


def hostname() -> str | None:
    try:
        return socket.gethostname() or None
    except OSError:
        return None


def ip_address() -> str | None:
    """The address other computers on the network reach this one at.

    Asks the system which address it would use to reach an outside address. No data is
    sent: "connecting" a UDP socket only picks the route.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # an address set aside for examples
            address = sock.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith("0.") else address


def wifi(root: Path = ROOT) -> int | None:
    """Wi-Fi link quality in % (0-100) from /proc/net/wireless, or None without Wi-Fi."""
    text = _text(root, "proc/net/wireless")
    if not text:
        return None
    for line in text.splitlines()[2:]:
        fields = line.split()
        if len(fields) >= 3 and fields[0].endswith(":"):
            try:
                quality = float(fields[2].rstrip("."))
            except ValueError:
                continue
            return max(0, min(100, round(quality / 70 * 100)))  # Linux counts up to 70
    return None


def disk(root: Path = ROOT) -> tuple[int, int] | tuple[None, None]:
    """Used and total bytes of the disk ``root`` is on. Space the system keeps back for
    itself counts as used, so used + free = total."""
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return None, None
    return usage.total - usage.free, usage.total


def temperature(root: Path = ROOT) -> float | None:
    """The processor's temperature in °C (Linux gives thousandths of a degree)."""
    text = _text(root, "sys/class/thermal/thermal_zone0/temp")
    try:
        return int(text.strip()) / 1000
    except (AttributeError, ValueError):
        return None


def load(root: Path = ROOT, cores: int | None = None) -> tuple[float, float, float] | None:
    """Average load over 1, 5 and 15 minutes, as % of all processor cores together."""
    text = _text(root, "proc/loadavg")
    cores = cores or os.cpu_count() or 1
    try:
        one, five, fifteen = (float(x) for x in text.split()[:3])
    except (AttributeError, ValueError):
        return None
    return one / cores * 100, five / cores * 100, fifteen / cores * 100


def memory(root: Path = ROOT) -> float | None:
    """Memory in use, in %: everything except what programs could still get."""
    text = _text(root, "proc/meminfo")
    values = {}
    for line in (text or "").splitlines():
        name, _, rest = line.partition(":")
        try:
            values[name] = int(rest.split()[0])
        except (IndexError, ValueError):
            continue
    total, available = values.get("MemTotal"), values.get("MemAvailable")
    if not total or available is None:
        return None
    return (total - available) / total * 100


def uptime(root: Path = ROOT) -> float | None:
    """Seconds since the Pi started."""
    text = _text(root, "proc/uptime")
    try:
        return float(text.split()[0])
    except (AttributeError, IndexError, ValueError):
        return None
