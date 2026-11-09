# Plugins and setting helpers

A plugin is what puts something on the screen: a clock, the weather, the song that is playing. PaperPi runs every update of a plugin in its own short-lived process, so a plugin that hangs or crashes can't stop PaperPi or the other plugins. A plugin never talks to the screen: it hands in a finished picture, and the [scheduler](scheduling.md) decides when it is shown. Setting helpers are searches a plugin offers on its settings page, such as finding a place by name.

How to write a plugin is on [Writing a plugin](../writing-plugins.md), and the exact rules are on [Plugin reference](../plugin-reference.md). This page describes how PaperPi runs plugins.

## What a plugin is

A plugin is a folder `src/paperpi/plugins/<type>/` with:

| Part           | What it is                                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------------------------ |
| settings       | each setting with its type, default and help text; used for the config check, the web forms and the docs    |
| `fetch`        | gets the data and says whether the plugin has something to show                                              |
| `draw`         | turns the data into what the layout shows                                                                    |
| layouts        | one or more named layouts; the user picks one                                                                |
| sample data    | fixed example data, so the plugin can draw without network access, for tests and the pictures in the manual |
| suggestions    | its `refresh`, its `level`, and optionally its storage limits; the user's settings always win                |
| helpers        | optional searches for its settings page (see [Setting helpers](#setting-helpers))                            |
| README         | what it shows and how to set it up; the web interface and this manual show it                                |

## One update

1. **`fetch`** gets the data and returns one of three states:
    - **nothing:** nothing to show right now (e.g. the music is stopped);
    - **ready:** here is the data;
    - **alert:** here is the data, and it is an alert.
2. **`draw`** turns the data into values for the blocks of the chosen layout.
3. **PaperPi draws the layout** with epdlib, in the plugin's process, and hands the finished picture to the scheduler.

For the sample pictures and the tests, `fetch` is skipped and the sample data goes straight to `draw`.

Note: a plugin can mark a setting as **required**, for settings it can't work without, such as an API key or `email`. A plugin that is missing a required setting is not shown and not counted as failing; the web interface shows "Needs settings: ...".

## How an update runs

- **Every update runs in a new process.** When the update is done, the process exits and its memory is given back. A plugin that hangs or crashes is stopped at its time limit, without affecting PaperPi or other plugins.
- **Starts are quick:** PaperPi keeps one ready copy of Python with epdlib, Pillow and pydantic already loaded, and starts each update as a copy of it. A start takes a fraction of a second, even on a Pi 3.
- **Nothing is kept in memory between updates.** Each plugin has its own storage folder, `/var/lib/paperpi/plugins/<folder>/`, named after its `id`, for saved files such as downloaded data or the time a song was paused.
- **The plugin's log lines** are sent to PaperPi with the result and written to PaperPi's log, with secret settings replaced by `****`.
- **Web requests** go through `paperpi.webrequest`, which sets the time limits and size limits for every plugin.

When each plugin is updated, and what happens after failures, is on [Which plugin is shown, and when](scheduling.md).

## Setting helpers

Some settings are hard to fill in by hand: latitude and longitude, a stop code, the address of a music server. A plugin can offer a **helper**: a search on its settings page that finds the values and fills them in.

**What the user sees:**

1. Just before the setting's field: a short text, a search box and a button (some helpers, such as **Find players**, only have a button).
2. The search starts with the button or the Enter key, not while typing.
3. A list of choices appears, each with a **Use** button. **Use** fills in the form's fields; nothing is saved until the user presses **Save**.
4. Under the list: where the answers come from, with a link (e.g. "Search by Open-Meteo, place data from GeoNames").

**How it works:**

- **PaperPi owns the page:** the search box, the list and putting the chosen values into the form. It doesn't need to know what a place, a stop or a server is.
- **The plugin owns its settings:** a helper is a plain function of the plugin. It gets what the user typed, the form's current settings and the browser's language, and returns a list of choices.
- **Each choice is a dictionary** whose keys say what PaperPi does with each value:

| Key    | What PaperPi does with it                                                                                   |
| ------ | ----------------------------------------------------------------------------------------------------------- |
| `fill` | settings put into the form when the user presses **Use**, checked as **Save** checks them                   |
| `show` | information to help the user pick, shown in order; the first entry is the heading of the choice             |
| `link` | web addresses the user can open, e.g. "See on map"; only `http` and `https`                                 |
| `note` | a message for the whole result, e.g. "Only the first 10 matches are shown" (on the result, not a choice)     |

- **A helper runs like an update:** in a new process with a time limit, so a helper that hangs can't stop the web interface. One search runs at a time.
- **All texts are shown as plain text,** on one line and cut to 200 characters, so odd characters can't change the page.
- **A key PaperPi doesn't know is ignored** and logged, so a plugin written for a newer PaperPi still works on an older one.

PaperPi also offers a **place search** that many plugins can share: it finds towns and cities by name with [Open-Meteo](https://open-meteo.com/en/docs/geocoding-api), with latitude, longitude and altitude. The Weather and Moon phase plugins use it through a ready-made `location` helper.

## Numbers

| What                                    | Value                         |
| --------------------------------------- | ----------------------------- |
| longest time for one update             | 60 seconds (at most 600), set with `time_limit` |
| longest time for one helper search      | 30 seconds                    |
| longest typed search text               | 100 characters                |
| most choices shown                      | 10                            |
| longest text in a choice                | 200 characters                |
| storage folder limits, unless changed   | 500 MB and 30 days (`storage_mb`, `storage_days`) |

## Not built yet

- **Plugins from an outside folder,** each with its own packages, so they don't have to be in PaperPi's code. Planned for 2.1.
- **Several plugins on the screen at once:** `draw` already gets the size of the area it draws in, which is now always the whole screen.
- **Custom layouts** without writing code, for example a layout editor in the web interface.
- **More helper keys,** each built with the first plugin that needs it: `add` (add an item to a list setting), `next` (choosing starts a second search), `disabled` (a choice shown but not usable, with the reason), `picture` (a small picture next to a choice) and `wait` (logging in to an outside account with a code).
- **Helpers on the command line:** `paperpi helper met_no.location "Morrison, Colorado"`.

## Why it works this way

- **A new process for each update:** PaperPi v1 ran plugins inside the main program, where one that hung could stop everything. A process that runs all the time for each plugin would use 30–50 MB of memory per plugin; a short-lived one gives its memory back.
- **`fetch` and `draw` are separate:** every plugin can draw its sample data without the network, so the tests and the manual's pictures always show what the plugin draws now.
- **Helpers return data, not HTML:** a plugin's own HTML or script would run inside the logged-in page, where it could read every setting, and it would look different for each plugin. A map to search on was too much work for a search done once.
- **The full story** is in the old design notes [`plugin-interface.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/plugin-interface.md) and [`setting-helpers.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/setting-helpers.md).

## In the code

- `src/paperpi/plugin.py`: what a plugin is (`Plugin`, `setting`), the settings every plugin has, and drawing a layout.
- `src/paperpi/plugins/__init__.py`: finding and loading plugins.
- `src/paperpi/runner.py`: running one update or helper search in its own process.
- `src/paperpi/helper.py`: helpers, choices and the `location` helper; `src/paperpi/places.py`: the place search.
- `src/paperpi/web/helpers.py`: the search box and the list of choices on the settings page.
- `src/paperpi/storage.py`: the storage folders and their limits; `src/paperpi/webrequest.py`: web requests.
