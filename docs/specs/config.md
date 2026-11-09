# The config file, and applying changes

All of PaperPi's settings are in one file, `/etc/paperpi/paperpi.toml`: the screen, the web interface and every plugin. The web interface reads and writes it, and people can also edit it by hand. PaperPi checks the file every time it reads it, keeps running on the last good copy when the file is broken, and applies most changes without a restart.

The list of every setting is on [Settings reference](../settings.md). This page describes how the file works.

## The file

The file is in [TOML](https://toml.io), a plain text format with sections, numbers, text and lists.

```toml
config_version = 1

[display]
type = "it8951"
model = "9.7"
vcom = -1.90

[[plugin]]
id = "met_no-3a91d2f4"
name = "Weather Berlin"
type = "met_no"
lat = 52.52
lon = 13.40
email = "you@example.com"

[[plugin]]
id = "word_clock-6f02b8d1"
type = "word_clock"
display_time = 255
```

- **One file** holds everything, so there is only one place to look when something breaks.
- **Each plugin has its own `[[plugin]]` block.** The same plugin can be added more than once, for example the weather for two cities. Plugins take turns in the order of their blocks.
- **Only changed values are stored.** A setting that is left out uses its default. The web interface shows every setting with its default filled in, and when a later version improves a default, you get it.
- **`config_version = 1`** at the top says which file layout it is.

### `id` and `name`

Every `[[plugin]]` block has an `id` and may have a `name`.

| Key    | Rules                                                                                                                  |
| ------ | ---------------------------------------------------------------------------------------------------------------------- |
| `id`   | required and unique; letters, digits, `_` and `-`, at most 40 characters; names the plugin's storage folder, so it is not meant to change |
| `name` | optional; what the web interface shows, e.g. "Weather Berlin"; any text up to 100 characters, without control characters; without it, the `id` is shown |

The web interface makes an `id` when it adds a plugin: the type and 8 random letters and digits, for example `met_no-3f9a1c2e`. By hand you may choose a readable one, such as `weather_berlin`.

Note: capitals don't count in an `id`, and `-` is the same as `_`, so `Weather-Berlin` and `weather_berlin` are the same `id`.

### Where PaperPi keeps its files

| What                                      | Where                                 |
| ----------------------------------------- | ------------------------------------- |
| the config file                           | `/etc/paperpi/paperpi.toml`           |
| an example with every setting             | `/etc/paperpi/paperpi.example.toml`   |
| saved data, the last good copy of the config | `/var/lib/paperpi/`                |
| logs                                      | the system log: `journalctl -u paperpi` |

Updates and reinstalls keep these folders.

## Checking the file

Every part of the config (the screen, the web interface, each plugin) is described in the code as a list of settings, each with a type, a default and a help text. The same description gives the check when the file is read, the forms in the web interface, the example file and the [Settings reference](../settings.md).

| Problem                                                                 | What PaperPi does                                                                                  |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| the file can't be read, or `config_version`, `[display]` or `[web]` is wrong | runs on the last good copy; the web interface names the wrong line                           |
| ...and there is no last good copy                                      | stops with an error that names the wrong line                                                      |
| one `[[plugin]]` block is wrong (a missing `id`, text where a number belongs) | only that plugin is switched off; the web interface shows which setting is wrong            |
| a plugin is missing a required setting (e.g. `email`)                   | the plugin is not shown and not counted as failing; `paperpi list` shows "needs ..."               |
| an unknown setting, e.g. `lattitude`                                    | a warning only: "unknown setting, did you mean `latitude`?"                                        |
| a newer `config_version` than this PaperPi knows                        | an error: the file was written by a newer PaperPi                                                  |

Each time the file is read without errors, a copy is saved as the last good copy.

Note: the web interface only accepts valid values, so most of these mistakes can only happen through hand edits.

## Writing the file

- **Hand-written comments are kept.** The web interface changes the file's text one `[[plugin]]` block at a time. Comments just above a block belong to that block and move or are removed with it.
- **Every change is read back** and compared before it is saved. A file written in a way this code doesn't understand is not changed; the web interface then says to change it by hand.
- **The file is written safely:** first to a temporary file, which then replaces the old one in one step. A power cut during a save can't leave a half-written file.

## Secrets

The web password and plugin keys are in the same file.

- Only root and the PaperPi service can read the file.
- The web password is stored as a hash: a scrambled form that can be checked but not turned back into the password. A forgotten password is reset with `sudo paperpi reset-password`, then a reload.
- The web interface never shows a saved secret again: it shows a password field.

## Applying changes

| Change made                   | When it applies                                                                                          |
| ----------------------------- | -------------------------------------------------------------------------------------------------------- |
| saved in the web interface    | at once                                                                                                  |
| edited by hand                | when you press **Apply changes** on the web interface's **Review changes** page, or run `paperpi reload` |

After a hand edit, a bar on every page of the web interface says that PaperPi does not use the changes yet. The **Review changes** page lists them (old and new value, per plugin).

`paperpi reload` checks the file first and prints the changes; a file with a mistake is not applied, and the old settings keep running. `paperpi reload --check` only prints the mistakes and the changes. `sudo systemctl reload paperpi` runs `paperpi reload`.

Changes are applied between two screen writes, never during one. What happens to the plugins is on [Which plugin is shown, and when](scheduling.md#start-the-fallback-clock-and-reloads).

### What applies at once, and what at the next start

| Setting                                                                         | When it applies                                                                 |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| every `[[plugin]]` setting                                                      | at once                                                                         |
| `vcom`, `max_refresh`                                                           | at once; the next screen write is a full one                                    |
| `rotation`, `color`                                                             | at once; every plugin draws again at its new size                               |
| `clean_every`, `on_exit`, `fallback_clock`                                      | at once                                                                         |
| `splash_time`                                                                   | only matters at start; a reload never shows the splash screen again            |
| `[web]` `login`, `password_hash`                                                | at once                                                                         |
| `type`, `model` (for the virtual screen also `width`, `height`, `mode`)         | at the next start of PaperPi; until then the old screen keeps running          |
| `[web]` `enabled`, `address`, `port`                                            | at the next start of PaperPi                                                    |

Note: a new web address or port is on trial after the restart. Every page shows **Keep these settings**; if nobody presses it within 5 minutes, PaperPi goes back to the old address and port by itself.

## Numbers

| What                                          | Value          |
| --------------------------------------------- | -------------- |
| largest config file PaperPi reads             | 256,000 bytes  |
| longest time to read and check it on a reload | 10 seconds     |
| longest `id`                                  | 40 characters  |
| longest `name`                                | 100 characters |
| time to press **Keep these settings**         | 5 minutes      |

## Not built yet

- **New versions of the file layout:** there is only version 1. When a later PaperPi changes the layout, it will save a backup (e.g. `paperpi.toml.v1.bak`), rewrite the file to the new layout with its comments, and report what it changed.
- **Moving a v1 `paperpi.ini`:** PaperPi v2 does not read v1 config files. A tool to help move one is a low-priority idea.

## Why it works this way

- **TOML:** readable and close to v1's INI format, but with numbers and lists. YAML changes meaning silently after small indentation mistakes, and JSON has no comments.
- **One file:** one place to look when something breaks, also for secrets.
- **Only changed values:** the file stays short and easy to fix by hand.
- **A fixed `id`:** the plugin's storage folder is named after it, so renaming a plugin never moves its files.
- **Hand edits wait for Apply changes:** a change can't take effect while you are still typing, and you know when it happened.
- **The full story** of these choices is in the old design notes [`config-format.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/config-format.md) and [`live-config-reload.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/live-config-reload.md).

## In the code

- `src/paperpi/config.py`: reading and checking the file, the last good copy, the `[display]` and `[web]` settings.
- `src/paperpi/plugin.py`: the settings every `[[plugin]]` block has.
- `src/paperpi/example.py`: the example file (`paperpi example-config`) and new plugin blocks.
- `src/paperpi/web/config_file.py`: writing `[[plugin]]` blocks while keeping comments.
- `src/paperpi/web/changes.py`: the **Review changes** page.
- `src/paperpi/web/keep.py`: **Keep these settings** after a new web address or port.
