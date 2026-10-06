"""--patch for render_v1.py: v1 xkcd_comic without network, always comic 1112 (the v2 sample).

Also works around render_v1.py's cache: CacheFiles(path=Path) makes ``path`` a str, so
v1's ``self.path/file_id`` fails. Here cache_file copies the sample picture instead.
"""

import shutil
import tempfile
from pathlib import Path

from library.CacheFiles import CacheFiles

import plugins.xkcd_comic.xkcd_comic as xkcd

SAMPLE = Path.home() / "src/wt/PaperPi-228-xkcd-comic/src/paperpi/plugins/xkcd_comic/sample"
INFO = {
    "num": 1112,
    "safe_title": "Think Logically",
    "title": "Think Logically",
    "img": "https://imgs.xkcd.com/comics/think_logically.png",
    "alt": "I've developed a more logical set of rules but the people on the chess community "
    "have a bunch of stupid emotional biases and won't reply to my posts.",
}
xkcd.get_comic_json = lambda url: dict(INFO)


def cache_file(self, url, file_id, force=False):
    target = Path(tempfile.mkdtemp(prefix="v1xkcd-")) / Path(str(file_id)).name
    shutil.copy(SAMPLE / "think_logically.png", target)
    return target


CacheFiles.cache_file = cache_file
