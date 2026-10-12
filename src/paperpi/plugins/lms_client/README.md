# lms_client

The song a [Lyrion Music Server](https://lyrion.org/) (LMS, formerly Logitech Media Server) player is playing: its title, artist, album and cover. The player can be any LMS player, such as a Squeezebox or Squeezelite on a Raspberry Pi, on this device or anywhere on the network. For several players, add one `[[plugin]]` block per player.

Use it with `level = "interrupt"`: while the player plays, it takes over the screen; when it stops (or is switched off), the other plugins are shown again. A paused song stays on the screen for `idle_timeout` seconds (default 15), so a short pause doesn't change the screen.

At each update the plugin asks the LMS server, through its JSON-RPC interface (`http://<server>/jsonrpc.js`), for its players, finds the one with the name in `player` (upper and lower case don't matter), and asks for its status. When the server has a password, the `user` and `password` settings are sent with every request (HTTP basic auth), and only to the LMS server.

Songs from the LMS library get their cover from the server (`/music/<coverid>/cover_500x500_m.jpg`). Internet radio shows the station's name as the artist and the station's picture, when LMS has one. A cover is downloaded once (at most 2 MB, JPEG or PNG) and saved in the plugin's storage folder; on a nearly full disk it is not saved. A song without a usable cover is shown with a plain picture of a record. The plugin also saves a small file with the time the song was paused, because each update is a new program that can't remember it.

When the server doesn't answer, asks for a password, or has no player with that name, the update fails with a message that says so, and PaperPi tries again at the next update. When the player plays nothing, the plugin has nothing to show, which is not a failure.

## Layouts

The same as `librespot_client`'s:

| Layout | Shows |
|---|---|
| `two_column_three_row` (default) | the cover with the artist and album next to it, the title below |
| `album_art_title` | a large cover with the title below it |
| `cover_art_only` | only the cover |
| `two_rows_text_only` | the title and the artist |
| `three_rows_text_only` | the title, the artist and the album |

Titles are in Oswald, the artist and album in Montserrat SemiBold, as in PaperPi v1. Long texts are drawn smaller; text that still doesn't fit ends with "…". The fonts are [Oswald](https://fonts.google.com/specimen/Oswald) by The Oswald Project Authors and [Montserrat](https://fonts.google.com/specimen/Montserrat) by The Montserrat Project Authors, under the SIL Open Font License ([`fonts/Oswald-OFL.txt`](../../fonts/Oswald-OFL.txt), [`fonts/Montserrat-OFL.txt`](../../fonts/Montserrat-OFL.txt)).

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `server` | (required) | address of the LMS server with its web port, e.g. `192.168.1.9:9000` (without a port: 9000) |
| `player` | (required) | name of the player, as LMS shows it, e.g. `Kitchen` |
| `user` | `""` | user name, only when the LMS server has a password |
| `password` | `""` | password, only when the LMS server has one (a secret: not shown on the settings page) |
| `idle_timeout` | `15` | seconds a paused song stays on the screen before other plugins are shown |

It suggests a refresh every 5 seconds.

On the settings page, the **Find players** button looks for LMS servers on the local network (the way LMS players find them: a broadcast message on UDP port 3483) and lists every player of every server, with its model and whether it is playing, on or switched off. Use fills in `server` and `player`. A server in another network can't hear the broadcast: type its address in `server` and press the button again to list its players. When the server has a password, fill in `user` and `password` first.

In the config file (the rest of the file is shown in the main [README](../../../../README.md)):

```toml
[[plugin]]
id = "kitchen"
name = "Kitchen music"
type = "lms_client"
level = "interrupt"
server = "192.168.1.9:9000"
player = "Kitchen"
```

Try it without a screen: `uv run paperpi render lms_client` (sample song), or with the song playing now: `uv run paperpi render lms_client --live --set server=192.168.1.9:9000 --set player=Kitchen`.

## Sample images

The sample cover, [`sample/cover.png`](sample/cover.png), was drawn for PaperPi; the sample song is made up. All sample images are in [`tests/images/`](../../../../tests/images/), named `lms_client-<layout>-<screen>.png`, where `<screen>` is `9in7` (9.7", 1200x825, 16 grays), `7in5` (7.5", 800x480, black and white) or `5in65` (5.65", 600x448, 7 colours).

| `two_column_three_row`, 9.7" | `album_art_title`, 9.7" | `cover_art_only`, 9.7" |
|---|---|---|
| ![two_column_three_row](../../../../tests/images/lms_client-two_column_three_row-9in7.png) | ![album_art_title](../../../../tests/images/lms_client-album_art_title-9in7.png) | ![cover_art_only](../../../../tests/images/lms_client-cover_art_only-9in7.png) |

| `two_rows_text_only`, 9.7" | `three_rows_text_only`, 9.7" | `album_art_title`, 5.65" colour |
|---|---|---|
| ![two_rows_text_only](../../../../tests/images/lms_client-two_rows_text_only-9in7.png) | ![three_rows_text_only](../../../../tests/images/lms_client-three_rows_text_only-9in7.png) | ![colour](../../../../tests/images/lms_client-album_art_title-5in65.png) |
