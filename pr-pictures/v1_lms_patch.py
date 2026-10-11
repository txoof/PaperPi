"""Gives v1's lms_client the v2 sample song, without an LMS server or QueryLMS."""
import importlib
import sys
import types

sys.modules.setdefault("QueryLMS", types.ModuleType("QueryLMS"))  # not in the v1 render kit
COVER = "/home/pi/src/wt/PaperPi-278-lms-client/src/paperpi/plugins/lms_client/sample/cover.png"
mod = importlib.import_module("plugins.lms_client.lms_client")


def update_function(self):
    data = {"title": "Night Train to the Coast", "artist": "The Paper Orchestra",
            "album": "Late Signals", "coverart": COVER, "mode": "play"}
    return True, data, 0


mod.update_function = update_function
