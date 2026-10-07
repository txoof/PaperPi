# Applying config changes without a restart

Status: proposed (M1, issue #189). Decided with txoof.

## Problem

In v1, every config change needs a restart of PaperPi (old issue #62). v2 should apply most changes while it keeps running, both from the web interface and from hand edits to `/etc/paperpi/paperpi.toml`.

Already decided in `config-format.md`: a broken file falls back to the last good copy, with the wrong line shown in the web interface, and an error in one plugin block switches off only that plugin. This note adds when and how a change takes effect.

## Options considered

**How hand edits are noticed**
1. PaperPi watches the file and applies it on its own a few seconds after it stops changing. Quick, but a change can take effect before the user is done, and it is harder to tell what happened.
2. **The user says when: an "Apply changes" button in the web interface, or a command.** Chosen. Predictable, and the user knows when the change happened.

**How much is reloaded**
1. Restart everything (stop all plugins, reopen the screen) on every change. Simple, but slow, and every plugin loses its place.
2. **Reload only what changed.** Chosen. It is not much harder, because each part of the config is checked on its own anyway.

## Decision (proposed)

### When a change is applied

| Change made | When it applies |
|---|---|
| Saved in the web interface | At once. The web interface has already checked the values. |
| Edited by hand | When the user presses **Apply changes** in the web interface, or runs `paperpi reload` (or `sudo systemctl reload paperpi`, the standard Linux way to tell a service to reread its settings). |

- The web interface notices when the file was changed outside it and shows: "The config file was changed outside the web interface. Apply changes?"
- Before applying, the new file is checked as in `config-format.md`. If it is broken, nothing changes, the old settings keep running, and the web interface (or the command's output) names the wrong line.
- The change is handed to the scheduler, the one part of PaperPi that decides what is shown (see `plugin-scheduling.md`). It applies the change between two screen writes, never during one.

### Plugins

What is on screen only lasts until the next cycle anyway, so this is kept simple:
- Plugins whose settings did not change keep their saved data and their place in the rotation.
- A changed plugin that is on screen is updated and redrawn right away, so the user sees the result.
- A plugin that is removed or switched off while on screen: rotation moves on to the next plugin.
- A new plugin joins the end of the rotation.
- *(M5 part 2a)* A plugin that is missing a required setting is treated as switched off: filling the setting in and reloading starts it (at its place in the file), and emptying it takes the plugin out of the rotation.

**Update 2026-10-05 (M4, issue #205):** plugins take turns in the order of the config file, so a new plugin takes the place where it is in the file (the end, when it is added at the end). Until reloading screen settings is built (M4 issue #222, part 5b), changed screen settings take effect at the next start, with a warning in the log. *(Built in part 5b; see the table below.)*

### Screen settings

| Setting | When it applies |
|---|---|
| `max_refresh` (fast refreshes before a full one), `vcom` | At once. The screen helper process (see `display-driver-interface.md`) starts again with the new values; the next write is full. |
| Rotation, colour on/off | At once. Every plugin draws again at its new size; the screen keeps its picture until the new images are ready. Colour is only offered for screens that can show colour. There is no mirror setting (yet). |
| Cleaning interval (`clean_every`), what happens on exit (`on_exit`), the fallback clock | At once. |
| `splash_time` | Only matters at start: a change during the start splash sets when it ends; a reload never shows the splash again. (With no plugin ready to show the splash is shown whatever it says.) |
| `type`, `model` (virtual screen: `width`, `height`, `mode`) | At the next start of PaperPi. |

*Update (M5 part 1, issue #238):* `[web]` settings. `login` and `password_hash` apply at a reload (so `paperpi reset-password` followed by a reload works without a restart); `enabled`, `address` and `port` apply at the next start, and a reload says so in the log.

*Update (M4 part 5b, agreed with txoof on 2026-10-06):* this table first said vcom applies at the next start.
- Everything about the screen itself (`type`, `model`, and for the virtual screen `width`, `height` and `mode`) applies **only at the next start**. On a reload the log says "[display] model changed: this applies at the next start of PaperPi", and the old values keep running.
- `vcom` applies **at once**: the new helper process's `init` sends the new value to the screen. This makes fixing a typo possible without a restart. The driver only accepts values from −3.0 to −0.5 V and checks that the screen took it; a wrong value in that range gives weaker contrast, nothing worse.
- While screen writes are paused (see `errors-and-time-limits.md`), any reload of a file that can be used tries the screen again at once.

- vcom is a voltage value that belongs to one panel and is printed on its ribbon cable. It changes only when the panel changes, so the web interface asks for it together with the screen model. It is not offered as a separate setting to adjust.
- Screens can't be swapped while the Pi is running. After a model change, the web interface says: "Shut down the Pi, connect the new screen, then start it again." If the new screen doesn't answer at start, the start-up check shows the error in the web interface.

### Web interface settings

- A new password applies at once.
- A new port restarts only the web server. The web interface shows the new address before it switches.

## Open questions

None. All points above were agreed with txoof on 2026-10-04.
