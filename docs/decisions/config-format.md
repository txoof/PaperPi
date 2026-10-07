# Config file format and validation

Status: proposed (M1, issue #186). Decided with txoof.

## Problem

PaperPi needs one place where all settings are kept: display, web interface and plugins. v1 uses `paperpi.ini`. Users must find the right section name, plugins are switched off by renaming them to `[xPlugin: …]`, and mistakes only show up as errors in the log.

v2 needs a config file that:
- people can read, and edit by hand in a plain text editor when something has gone wrong
- the web interface can read and write, because the web interface is the main way to change settings
- is checked when it is loaded, with clear error messages
- describes its own settings, so the web interface can build its forms from that description and each plugin can declare its own settings

The v1 `paperpi.ini` is not imported. v2 is set up from scratch in the web interface.

## Options considered

1. **INI** (v1). Readable, but it has no lists, no nesting and no types. Every value is text.
2. **YAML.** Readable, but small indentation mistakes change the meaning without any error, and values like `no` or `3.10` are quietly turned into other types.
3. **JSON.** Strict, but it has no comments and is awkward to edit by hand.
4. **TOML.** Readable and close to INI, but with types and lists. Python reads it without extra packages, and the `tomlkit` package can write it back while keeping comments. **Chosen.**

## Decision (proposed)

### One TOML file, run as a system service

PaperPi is a system service: it starts at boot and always runs as exactly one copy. A second copy that is started stops with a clear message. That way, two programs can never write to the screen at once.

| What | Where |
|---|---|
| config | `/etc/paperpi/paperpi.toml` |
| example with every setting | `/etc/paperpi/paperpi.example.toml` |
| saved data, cache, "last good" config | `/var/lib/paperpi/` |
| logs | the system log: `journalctl -u paperpi` |

Inside Docker, these folders are shared with the container, so they survive updates and reinstalls.

All settings are in **one file**, so there is only one place to look when something breaks. Each plugin has its own `[[plugin]]` block. The same plugin can be used more than once, for example weather for two cities.

```toml
config_version = 1

[display]
type = "it8951"
model = "9.7"
vcom = -1.90
rotation = 0

[[plugin]]
name = "Weather Berlin"
type = "met_no"
level = "rotation"
display_time = 50
lat = 52.52
lon = 13.40

[[plugin]]
name = "Word Clock"
type = "word_clock"
level = "rotation"
display_time = 255
```

### Only changed values are stored

The file only holds settings that differ from the default. This keeps it short and easy to fix by hand. When a later version improves a default, you get it automatically. The web interface shows every setting with its default filled in. `paperpi.example.toml` is generated from the program (`paperpi example-config`), so it is always up to date; a test checks the copy in the repository. It is short and works as it is: `[display]` with a virtual screen, a clock, and the weather in Berlin and in Rio (the same plugin type twice). Every setting it doesn't set is a comment with its default, and its help text on the line above. The first `[[plugin]]` block lists all the settings every plugin has; the other blocks list only `refresh` and `layout`, because their defaults depend on the plugin. `storage_mb` and `storage_days` can also differ per plugin, but most plugins keep the defaults, so they are only in the first block; `paperpi list` shows the values used (M4 issue #224). The copy in the repository is not edited by hand: it is made again with `paperpi example-config -o paperpi.example.toml --force`. Agreed with txoof on 2026-10-06: the example does not list every plugin. Adding and removing plugin blocks is the job of a config manager (the web interface, M5), which builds a block the same way (`paperpi.example.plugin_block`). That function refuses unknown settings and values the plugin would not accept, and checks that PaperPi reads the block back as written. Plugin names may not hold control characters (such as tab, new line or the terminal's ESC), because they can't be written back to the file reliably.

### Checking the file

Each part of the config (display, web, each plugin type) is described in code as a list of settings, each with a type, a default and a short help text. The `pydantic` package does this. From the same description we get:
- the check when the file is loaded, with error messages that name the line and the setting
- the forms in the web interface (M5)
- `paperpi.example.toml` and the config reference in the docs

Plugins declare their own settings the same way. The details are in the plugin interface note (#187).

What happens when something is wrong:

| Problem | What PaperPi does |
|---|---|
| File can't be read at all, or the `display` / `web` part is wrong | Runs on the **last good** copy, a copy that is saved each time the config loads correctly. A warning on the screen and in the web interface names the wrong line. |
| ...and there is no last good copy (first install) | Shows an error screen with a QR code (a square barcode a phone camera can scan) that opens the web interface. |
| One plugin block is wrong (missing value, text where a number belongs) | Only that plugin is switched off. Everything else runs. The web interface shows which setting is wrong. |
| Unknown setting name, e.g. `lattitude` | Warning only: "unknown setting, did you mean `latitude`?" |

The web interface only accepts valid values, so most of these mistakes can only happen through hand edits.

### Writing the file

- The web interface keeps comments that were written by hand.
- The file is written safely: first to a temporary file, then that file replaces the old one in one step. A power cut during a save can't leave a half-written config.

### Secrets

The web password and plugin API keys are in the same file, so there is still only one file to look at.
- Only root and the PaperPi service can read the file.
- The web password is stored as a hash, a scrambled form that can be checked but not turned back into the password. To reset a forgotten password: run `sudo paperpi reset-password` (or delete that line by hand), restart or reload, and set a new one in the web interface. *(Command added in M5 part 1, issue #238.)*
- The web interface never shows a saved API key again. It shows `••••` with a "replace" button.

### New versions of the file layout

The file starts with `config_version = 1`. When a newer PaperPi finds an older version number, it:
1. saves a backup, e.g. `paperpi.toml.v1.bak`
2. rewrites the file to the new layout and keeps comments
3. reports what it changed, in the log and in the web interface

Nobody has to edit the file by hand after an update.

How config changes take effect without a restart is decided in the live reload note (#189).

## Open questions

None. All points above were agreed with txoof on 2026-10-04.
