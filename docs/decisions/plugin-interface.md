# Plugin interface v2

Status: proposed (M1, issue #187). Decided with txoof.

## Problem

A plugin is what puts something on the screen: a clock, the weather, the song that is playing. v2 needs a clear agreement between PaperPi and its plugins: what a plugin must provide, how it is run, and what happens when it misbehaves.

What v1 does well and v2 keeps:
- A plugin is a folder with its code, its layouts and sample images.
- From PaperPi's side, a plugin hands over a finished image. The plugin decides what it looks like. Usually it fetches data and draws it with one of its own layouts.
- The same plugin can be used several times with different settings (weather for two cities).

What v1 does badly:
- Plugins run inside the main program. A plugin that hangs can stop everything, and the time limit (the alarm signal) only works in some cases.
- Settings are not described anywhere, so they can't be checked and the web interface can't build forms for them.
- Priority numbers decide what is shown. This is replaced by the scheduling note (`plugin-scheduling.md`).

## Options considered

1. **Plugins in the main program** (v1). Simple, but one bad plugin can freeze PaperPi.
2. **One long-running separate program (process) per plugin.** Safe, but uses 30–50 MB of memory per plugin, all the time.
3. **A short-lived process for each update.** Start, fetch, draw, hand over the image, exit. Plugins update every few minutes and a few seconds' delay is fine, even for music. **Chosen.**

## Decision (proposed)

### What a plugin is

A folder in `src/paperpi/plugins/<name>/` with:

| Part | What it is |
|---|---|
| settings | A description of each setting: type, default, short help text. Used for config checks, web forms and docs (see `config-format.md`). Includes a **recommended refresh rate**. |
| update function | Gets the settings, the screen size and colour mode, and its own storage folder. Returns a state (below) and an image. |
| layouts | One or more named layouts (e.g. large, compact). The user picks one in the web interface. |
| sample data | Fixed example data, so the plugin can draw an image without network access. Used for tests and the sample images in the docs. |
| README | What it shows and where the data comes from. |

Each update returns one of the states from `plugin-scheduling.md`:
- **nothing**: nothing to show right now (e.g. music is stopped)
- **ready**: here is an image
- **alert**: here is an image, and it is an alert

The plugin never talks to the screen. Only the scheduler does.

### How a plugin is run

- Every update runs in a **new, short-lived process**. When the update is done, the process exits and its memory is given back. A plugin that hangs or crashes is stopped without affecting PaperPi or the other plugins.
- To keep starts quick (important for music plugins, which check every few seconds), PaperPi keeps one ready copy with the common packages already loaded and starts each update from it. A start takes a fraction of a second, even on a Pi 3.
- A plugin can't keep anything in memory between updates. It gets its own folder, `/var/lib/paperpi/plugins/<plugin name>/`, for saved files such as downloaded data or the last track played.
- Time limit per update: a default for all plugins, which can be changed per plugin. The exact numbers and what happens after repeated failures are in the error-handling note (#190) and `plugin-scheduling.md`.

### When a plugin is updated

- **Rotation plugins** (clock, weather, moon) update just before their turn, unless their last image is still fresh. While on screen, they keep updating at their refresh rate, e.g. the word clock changes every minute.
- **Interrupt and alert plugins** (music, future alarms) check in the background all the time at their refresh rate, so they can report "I have something" right away.
- Plugins that are not on screen and not about to be use no network and no processor time.

### Refresh rate and screen speed

- Each plugin suggests a refresh rate. The user can set any value in the web interface, which shows the suggestion next to the field.
- The only limit is the screen. Redraws take 30–60 seconds on most Waveshare screens and 30 seconds to 2 minutes on colour screens. The Waveshare drivers don't report this, so PaperPi measures it: a redraw is finished when the screen's busy signal (a wire that stays on while the screen is redrawing) switches off. PaperPi never sends a new image before that, and never waits without a time limit.
- The time each redraw took is shown in the web interface.

### Later: several plugins on screen at once (M9)

The update function already receives the size of the area it should draw in. In v2.0 that is always the whole screen. In M9 it can be one region of the screen, so plugins don't need to change.

### Later list

These items wait until after 2.0. Each becomes its own issue then.
- **Custom layouts:** let users make or change layouts without writing code, e.g. a layout editor in the web interface. In v2.0 users pick from each plugin's built-in layouts.
- **Plugins outside the application** (old issue #13): a configurable folder for plugins, so they don't have to be copied into PaperPi. Nothing in this design should block it.
- **Several plugins on screen at once** (M9, M10), with a graphical dashboard editor in the web interface (see `web-interface.md`).

## Open questions

None. All points above were agreed with txoof on 2026-10-04.
