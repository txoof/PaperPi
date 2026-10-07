"""--patch for render_v1.py: v1 newyorker without network, drawing the v2 sample.

v1 needs ``feedparser``, which the v1 render kit doesn't have: a small stand-in returns a
feed with one cartoon. ``cache_file`` copies the v2 sample picture instead of downloading,
and the time is fixed at 10:42, as in the v2 sample.
"""

import shutil
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path

from library.CacheFiles import CacheFiles

SAMPLE = Path.home() / "src/wt/PaperPi-234-newyorker/src/paperpi/plugins/newyorker/sample"
CAPTION = "A drawing that riffs on the latest news and happenings."


class Feed(dict):
    def has_key(self, key):
        return key in self


entry = types.SimpleNamespace(
    summary=CAPTION, id="sample", media_thumbnail=[{"url": "https://example.com/island.png"}]
)
sys.modules["feedparser"] = types.SimpleNamespace(parse=lambda url: Feed(entries=[entry]))
Feed.entries = property(lambda self: self["entries"])

import plugins.newyorker.newyorker as newyorker  # noqa: E402


class Fixed(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 5, 10, 42)


newyorker.datetime = Fixed
newyorker.randrange = lambda start, stop: 0


def cache_file(self, url, file_id, force=False):
    target = Path(tempfile.mkdtemp(prefix="v1newyorker-")) / "island.png"
    shutil.copy(SAMPLE / "island.png", target)
    return target


CacheFiles.cache_file = cache_file
CacheFiles.remove_stale = lambda self, *args, **kwargs: []
