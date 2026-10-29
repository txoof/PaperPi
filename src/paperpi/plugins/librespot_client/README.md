# librespot_client

Shows the currently playing song, artist and album art from Spotify, played on this Pi through [go-librespot](https://github.com/devgianlu/go-librespot).

This plugin typically remains dormant and invisible on PaperPi until music starts playing. When music starts, the plugin will jump to the foreground using the `interrupt` display level and keep control of the screen until the music stops.

![The plugin's default layout on the 9.7" screen: the cover, with the artist and album next to it and the title below](../../../../tests/images/librespot_client-two_column_three_row-9in7.png)

## What you need

- **go-librespot** running on the same Pi as PaperPi. go-librespot is a program that turns the Pi into a Spotify speaker: in the Spotify app, pick the Pi (go-librespot's `device_name`) as the speaker.
- **go-librespot's API server** switched on. This is the part of go-librespot that tells other programs what is playing. Switch it on in go-librespot's `config.yml`, then restart go-librespot:

```yaml
server:
  enabled: true
  port: 24879
```

Note: the API server only answers programs on the same Pi, so PaperPi and go-librespot must run on the same Pi.

## Set it up

1. In the PaperPi web interface, open the **Plugin Library** and add **Spotify**.
2. On its settings page, press **Find go-librespot**. The plugin looks for go-librespot's `config.yml` on this Pi and shows the player's name, its port, and whether go-librespot answers.
3. Press **Use** next to your player. That fills in the `port` setting.
4. Save, and play a song from the Spotify app.

Note: if the API server is switched off, **Find go-librespot** says what to change in `config.yml`.

## When it is shown

While actively playing, the plugin takes over the screen. When the music stops, the other plugins are shown again. A paused song stays on the screen for `idle_timeout`, a default of 10 seconds, so a short pause doesn't change the screen. This is called an interrupt plugin; [Understanding Plugin Schedules](https://txoof.github.io/PaperPi/take-turns/) explains the levels.

## Layouts

| Layout                           | Shows                                                           |
| -------------------------------- | --------------------------------------------------------------- |
| `two_column_three_row` (default) | the cover with the artist and album next to it, the title below |
| `album_art_title`                | a large cover with the title below it                           |
| `cover_art_only`                 | only the cover                                                  |
| `two_rows_text_only`             | the title and the artist                                        |
| `three_rows_text_only`           | the title, the artist and the album                             |

| `two_column_three_row` | `album_art_title` | `cover_art_only` |
|---|---|---|
| ![two_column_three_row](../../../../tests/images/librespot_client-two_column_three_row-9in7.png) | ![album_art_title](../../../../tests/images/librespot_client-album_art_title-9in7.png) | ![cover_art_only](../../../../tests/images/librespot_client-cover_art_only-9in7.png) |

| `two_rows_text_only` | `three_rows_text_only` | `two_column_three_row` on a color screen |
|---|---|---|
| ![two_rows_text_only](../../../../tests/images/librespot_client-two_rows_text_only-9in7.png) | ![three_rows_text_only](../../../../tests/images/librespot_client-three_rows_text_only-9in7.png) | ![color](../../../../tests/images/librespot_client-two_column_three_row-5in65.png) |

Long titles are drawn smaller; text that still doesn't fit ends with "…". Titles are in [Oswald](https://fonts.google.com/specimen/Oswald), the artist and album in [Montserrat](https://fonts.google.com/specimen/Montserrat) SemiBold, as in PaperPi v1. The layouts are the same as the [Music server (LMS)](../lms_client/README.md) plugin's.

## Covers

Each album cover is downloaded once and kept in the plugin's storage folder (at most 2 MB, JPEG or PNG; on a nearly full disk it is not kept), so a song played again doesn't download it again. A song without a cover shows a plain picture of a record.

## When something is wrong

When go-librespot doesn't answer (it is not running, or the port is wrong), the plugin's card on the web interface's home page shows the error, and PaperPi tries again at the next update. After 3 failures in a row the plugin is paused for 30 minutes and the Warnings page shows it too ([Troubleshooting](https://txoof.github.io/PaperPi/troubleshooting/)). When nothing is playing, the plugin just waits: that is not an error.

## Settings

| Setting        | Default | Meaning                                                                  |
| -------------- | ------- | ------------------------------------------------------------------------ |
| `port`         | `24879` | port of go-librespot's API server: `server.port` in its `config.yml`     |
| `idle_timeout` | `10`    | seconds a paused song stays on the screen before other plugins are shown |

The plugin asks for a new picture every 10 seconds unless you change `refresh`.

PaperPi v1's `player_name` setting is gone: go-librespot only reports on its own player.

### Configuration Keys

```toml
[[plugin]]
id = "librespot_client-e17e8f3c"
name = "Spotify"
type = "librespot_client"
port = 24879
idle_timeout = 30
```

## For developers

At each update the plugin reads go-librespot's status from `http://localhost:<port>/status`. Each update is run as a new process; the plugin saves the time a song was paused in a small file for memory. **Find go-librespot** looks for `config.yml` in the folder of each go-librespot program that runs now (its `--config_dir`), then in `/var/lib/go-librespot/` and `~/.config/go-librespot/`.

Try it without a screen: `uv run paperpi render librespot_client` (sample song), or with the song playing now: `uv run paperpi render librespot_client --live`. The sample cover, [`sample/cover.png`](sample/cover.png), was drawn for PaperPi; the sample song is made up. The fonts are under the SIL Open Font License ([`fonts/Oswald-OFL.txt`](../../fonts/Oswald-OFL.txt), [`fonts/Montserrat-OFL.txt`](../../fonts/Montserrat-OFL.txt)).
