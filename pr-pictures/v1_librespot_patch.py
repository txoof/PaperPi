"""Gives v1's librespot_client the v2 sample song, without go-librespot."""
import importlib

COVER = "/home/pi/src/wt/PaperPi-273-librespot-client/src/paperpi/plugins/librespot_client/sample/cover.png"
mod = importlib.import_module("plugins.librespot_client.librespot_client")


def update_function(self):
    data = {"title": "Morning Light Over the Harbour", "artist": "The Sample Band",
            "album": "Songs for Paper Screens", "coverart": COVER}
    return True, data, 0


mod.update_function = update_function
