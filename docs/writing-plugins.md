# Writing a plugin

A plugin puts something on the screen: a clock, the weather, the song that is playing. This page shows how to write one. The reasons behind the rules are in [`decisions/plugin-interface.md`](decisions/plugin-interface.md). The simplest complete example is [`basic_clock`](../src/paperpi/plugins/basic_clock/).

## What a plugin is

A folder `src/paperpi/plugins/<type>/`. `<type>` is the plugin's name in the config file: it starts with a lowercase letter, followed by lowercase letters, digits and `_`.

| File | What it holds |
|---|---|
| `__init__.py` | the settings, `fetch`, `draw`, the sample data, and `PLUGIN` |
| `layouts.py` | the layouts: what goes where on the screen |
| `README.md` | what it shows, where the data comes from, its settings; also shown in the web interface (each Plugin Library card links to it) |

A shortened version of `basic_clock/__init__.py` (the real one also formats 12-hour times and the date):

```python
from datetime import datetime
from typing import Literal

from pydantic import Field

from ...plugin import Context, Plugin, PluginSettings, ready
from .layouts import LAYOUTS


class Settings(PluginSettings):
    hours: Literal[12, 24] = Field(24, description="12-hour (3:45 PM) or 24-hour (15:45) clock")


def fetch(context: Context):
    return ready(datetime.now())


def draw(now: datetime, context: Context) -> dict:
    return {"time": f"{now:%H:%M}"}


PLUGIN = Plugin(
    type="basic_clock",
    title="Clock",
    description="The time, and optionally the date, in large text.",
    settings=Settings,
    layouts=LAYOUTS,
    layout_titles={
        "time": "Time",
        "time_date": "Time and date",
        "small": "Small line at the bottom",
    },
    fetch=fetch,
    draw=draw,
    sample=datetime(2026, 10, 5, 10, 42),
    refresh=60,
    refresh_on_minute=True,
)
```

`title` is the plain name the Plugin Library shows (at most 40 characters; the type is shown small below it), and the start of the name a new plugin gets ("Clock", "Clock 2"); the Home page and the settings page show it too. `layout_titles` gives each layout a plain name in the same way (at most 40 characters each), shown on the Library card and in the settings page's layout list, with the layout's name after it ("Time and date (time_date)"; its "Default:" hint shows the title too); every plugin that comes with PaperPi has one for each layout (a test checks), and a layout without one is shown by its name. A plugin that connects to something says so with `network="internet"` (a website or online service) or `network="home"` (a device on the home network, such as a music server); the Library shows "Requires internet" or "Uses home network". A plugin with required settings gets "Requires setup" by itself. A plugin that needs something set up outside PaperPi first, such as another program, says so in one sentence with `setup="..."` (at most 200 characters); it then gets "Requires setup" too, and the sentence is shown on its card and its Add page, with a link to its README: explain the setup there. In the web interface the README's first heading, its pictures and its "Sample images" section are left out (the pictures are not installed), links to other plugins' READMEs open their page there, links to websites stay, and other links become plain text.

## One update, step by step

1. PaperPi starts a new process for the update. A process is a running program with its own memory; when it ends, its memory is given back (see "Rules" below).
2. `fetch(context)` gets the data and says whether there is something to show:
   - `return NOTHING`: nothing to show right now (for example the music is stopped)
   - `return ready(data)`: here is data to show
   - `return alert(data)`: here is data, and it is an alert
3. `draw(data, context)` returns a dictionary with a value for each block of the layout, for example `{"time": "10:42"}` (or a `Drawn`, see "Moving blocks and colours"). PaperPi draws the layout with epdlib.
4. The image goes back to PaperPi and the process exits.

For tests and sample images, step 2 is skipped and `sample` is drawn instead. So every plugin can draw an image without network access, and `draw` must work with the sample data. The web interface's Preview also draws the sample data when the real data fails, takes too long, has nothing to show or still needs settings, so make the sample look like real data.

`context` holds:

| Field | What it is |
|---|---|
| `settings` | the plugin's own settings, already checked |
| `width`, `height` | the size of the area to draw, in pixels |
| `mode` | what the screen can show (an epdlib `ScreenMode`: black and white, gray levels or colours) |
| `storage` | the plugin's own folder for saved files, e.g. downloaded data |
| `layout` | the name of the layout to draw |
| `status` | only for the `default` plugin: how many plugins are not working (`failing`, `total`) |
| `low_disk` | `True` when less than 2 GB is free on the disk that holds PaperPi's state folder (`/var/lib/paperpi`): don't save more files (for example, don't download new photos). Replacing a file you already have is fine. |

## Settings

Each setting is a field of the plugin's `Settings` class, with a type, a default and a short help text (`description`). From this one description PaperPi checks the config file, writes the plugin's block for the config file (each setting as a comment with its default and the help text on the line above; for a `Literal` type the allowed values are added unless the help text names each of them as a word of its own), and later builds the web interface's form and the docs. A test uncomments every setting of every plugin's block and checks that it loads, so every default must be a valid value.

- Every setting needs a default.
- Don't use the names of the shared settings, which every `[[plugin]]` block already has: `id`, `name`, `type`, `enabled`, `level`, `display_time`, `refresh`, `time_limit`, `layout`, `alert_reminder`, `alert_max_time`.
- Use `pydantic.SecretStr` as the type for API keys and passwords. PaperPi then never shows their values in error messages or logs.
- A setting the user must fill in before the plugin can work (a place, an email address, an API key) is made with `paperpi.plugin.setting(..., required=True)` instead of `Field`. It takes the same arguments as `Field`. Its default must be "not set": `None`, empty text or an empty `SecretStr` (text of only spaces also counts as not set). Until every required setting is filled in, the plugin is not shown and not counted as broken; the config check, `paperpi list` and the web interface's Home page say which settings are missing. The example block marks them "(required)". `setting` is also where other options for a single setting go, such as `helper=` (see "Setting helpers" below).
- A plugin with many settings can put them in groups with `setting(..., group="Stop 1")`. The settings page then shows each group as a section that folds open and shut, inside "Plugin settings", in the order the group's first setting comes in the code; settings without a group come first, directly under that heading. A plugin that names no group gets the plain page. `nl_openbaar_vervoer` has a group for each stop, each train route and the NS key.
- The web interface shows the plugin's `description` in its Plugin Library, and the help text (`description`) of every setting on the plugin's Settings page, next to its field. Write both for someone at home who is not a programmer. The settings page is built from the settings description: a `Literal` becomes a choice list, `bool` a check box, `int`/`float` a number field (with its `ge`, `gt`, `le` and `lt` limits), `str` a text field (with `max_length`), `SecretStr` a password field, and a tuple or list of a `Literal` a list to tick. A setting of another kind is shown as it is in the file, to be changed there.
- A help text may link to the plugin's README or a web page, written as `[text](readme)` or `[text](https://...)`, e.g. `"NS API key needed for trains. See the [README](readme) for information on obtaining a free key"`. The settings page shows a link; the config file shows only the text ("See the README for ..."). See `src/paperpi/links.py`.

  ```python
  from paperpi.plugin import PluginSettings, setting


  class Settings(PluginSettings):
      lat: float | None = setting(None, required=True, ge=-90, le=90, description="Latitude")
  ```

In the config file, the plugin's settings go in its `[[plugin]]` block:

```toml
[[plugin]]
id = "basic_clock-5c1e0a7b"   # made by PaperPi: the type and 8 random letters and digits
type = "basic_clock"
hours = 12
```

## Setting helpers

Some settings are hard to fill in by hand, such as a place's latitude and longitude or a stop's code. A plugin can offer a **helper**: a search box on its settings page, just before the setting it fills. The user types something, PaperPi shows a list of choices, and **Use** fills in the form's fields (nothing is saved until Save). The reasons are in `docs/decisions/setting-helpers.md`.

- A helper is a `paperpi.plugin.Helper` in the plugin's `helpers`, by name. A setting names it with `setting(..., helper="<name>")`; the search box is shown just before that setting, so name the first of the settings it fills. The plugin check fails for a name the plugin doesn't have.
- Its `find(query)` gets a `Query`: `query.text` (what the user typed, without spaces around it, at most 100 characters; empty for `typed=False`), `query.settings` (the form's settings, checked as Save checks them; an empty secret field gives the saved secret) and `query.language` (the language the user's browser asks for first, e.g. `nl`; `en` when not known), for services that find names only in the language they are asked in.
- It returns a list of choices, or `{"choices": [...], "note": "..."}` with a message for the whole result. Each choice is a dictionary; its keys say what PaperPi does with each value:
  - `fill`: the plugin's own settings and their values, put into the form by **Use**. Leave a setting out to leave it alone. Only settings the form shows as a field: not secrets (`SecretStr`), and not settings that are changed in the file (such as a list of numbers).
  - `show`: label and text, shown to help the user choose; the first one is the heading.
  - `link`: label and web address (`http` or `https` only), e.g. "See on map".
  A kind PaperPi doesn't know is left out and logged. At most 10 choices are shown. Each text is put on one line and cut to 200 characters.
- `raise HelperProblem("...")` stops with a message for the user (e.g. "The API key was not accepted"). Any other error shows "The search failed"; the details go to PaperPi's log.
- Each search runs in its own process with a time limit of 30 seconds, like an update. Use `paperpi.webrequest` for web requests.
- Secret settings (API keys) are replaced with `****` in everything a search returns, and a choice can't `fill` them. A search uses the form's values before they are saved, so never send a saved secret to a web address taken from the settings: someone could type their own address and get the key. Use only the plugin's own servers for that.
- `Helper` also takes the `prompt` above the box, the `button` text, `typed=False` for a helper that needs no typed text (only a button), `needs` (settings that must be filled in first, e.g. an API key) and `source` and `source_link` (where the answers come from, shown under them; say it when the typed text goes to an outside service).

```python
from paperpi.plugin import Helper, HelperProblem, PluginSettings, Query, setting


class Settings(PluginSettings):
    stop: str = setting("", helper="stops", description="Code of the stop")
    stop_name: str = setting("", description="Name shown on the screen")


def find_stops(query: Query):
    found = search_the_stop_list(query.text)  # the plugin's own code
    return [
        {
            "fill": {"stop": s.code, "stop_name": s.name},
            "show": {"Stop": s.name, "Town": s.town},
        }
        for s in found
    ]


# In PLUGIN = Plugin(...):
#     helpers={"stops": Helper(find_stops, prompt="Name of the stop, e.g. Centraal Station")},
```

For a latitude and longitude, use PaperPi's ready-made helper instead of writing one: `paperpi.places.location_helper()` searches for places by name (Open-Meteo, in the user's language and in English) and fills in `lat` and `lon`. Pass the names of your settings if they are called something else. If your plugin also has settings for the height (in whole metres) or for the name shown on the screen, pass their names too, e.g. `altitude="height", name="place"` (the name is always replaced). `met_no` uses `location_helper(altitude="altitude", name="place")`, `moon_phase` plain `location_helper()`.

The `debugging` plugin has a helper to try it out: `words` turns each typed word into a choice for its `text` setting.

## Layouts

`LAYOUTS` maps names to epdlib layouts (see [epdlib's layout guide](https://github.com/txoof/epdlib/blob/main/docs/layouts.md)). The first one is the default; the user can pick another with `layout = "..."`. A layout is a dictionary, or a function that makes one from the settings, for layouts that depend on a setting.

Give every text block a `sample`: the widest text it normally shows (`"88:88"` for a clock). The font size is then chosen once, so it doesn't change between updates.

### Fonts

Without a `font`, a text block uses epdlib's DejaVu Sans. PaperPi has more fonts in `src/paperpi/fonts/`, which any plugin may use, each with its licence:

```python
from ... import fonts

{"name": "title", "type": "text", "font": fonts.LATO_BOLD}  # also fonts.LATO_ITALIC, fonts.ANTON
```

To add a shared font, put the font file and its licence in `src/paperpi/fonts/`, and add a name for its path in `src/paperpi/fonts/__init__.py`. A font only one plugin uses can also stay in the plugin's own folder, with its licence.

### Pictures the plugin draws itself

Draw pictures such as bars, dots or icons at the exact size they are shown, never larger: resizing blurs their edges, and blurred edges show as dots on black-and-white screens. epdlib gives that size, inside the block's border and padding:

```python
layout = PLUGIN.layout(context.layout, context.settings)
prepared = layout.prepare(context.width, context.height, context.mode)
width, height = prepared.content_size("bar")
```

A picture of this size is shown pixel for pixel, whatever the block's `fit`. See `system_info` and `dec_binary_clock`.

### Moving blocks and colours

`draw` may return a `Drawn` instead of a dictionary, to set two more things:

```python
from ...plugin import Drawn

return Drawn(values, seed=int(f"{now:%Y%m%d%H%M}"), colors=("yellow", "blue"))
```

- `seed`: blocks with `align` or `valign` set to `"random"` are placed somewhere else at each update. The same seed always gives the same place, so sample images and tests stay the same. Make it from the data: `word_clock` uses the time to the minute; a plugin that shows no time can use a number made from its data, so new data moves the blocks and the same data doesn't.
- `colors`: text and background colour for every block with `rgb_support: True`, in place of the colours written in the layout (swapped for blocks with `inverse: True`, so the text still gets the text colour). For settings that let the user pick colours, use `paperpi.colors`: `ColorName` as the setting's type (the colour names plus `random`) and `screen_colors(...)` to turn the choice into colours this screen can show. See `word_clock`.

## Web requests

Use PaperPi's helper `paperpi.webrequest` for every download. It keeps to the limits (10 s to connect, 30 s in total, at most 5 MB), and unpacks gzip (the usual way servers pack an answer so fewer bytes are sent; other ways of packing are refused).

```python
from paperpi import webrequest

answer = webrequest.get(url, contact=context.settings.email)  # the plugin's own "email" setting
data = answer.json()
```

`get` takes:
- `contact`: an email or web address, added to the User-Agent header (the line in every request that names the program), so the service knows whom to ask about problems. Some services, like met.no, require it. Give your plugin a setting for it, as `met_no` does with `email`, and make it required with `setting(..., required=True)`.
- `headers=`: more headers to send, for example an API key. They are sent only to the server of `url`: if that server redirects to another one, they are left out.
- `if_modified_since=`: the `last_modified` of an earlier answer. If nothing changed since, `answer.not_modified` is `True` and `answer.body` is empty. Save `last_modified` (it can be `None` when the server didn't send one) and the data in `context.storage`, so the next update can ask.
- `max_bytes=`: a higher size limit, for example for large images.

The answer has `status`, `body` (the content as bytes, for example an image), `headers` (with lowercase names), `url` (the address that answered, after redirects), `not_modified`, `last_modified` and `json()`.

What it does when something goes wrong:
- **Retries once, after 5 s,** when the server can't be reached, doesn't answer in time, breaks off the connection, or answers "too many requests" (429) or "server error" (500, 502, 503, 504). Not when there is too little time left for a second try within the 30 s, and not for other answers such as "not found" (404).
- Follows up to 3 redirects (answers that say "this moved to ..."), but never from `https` to `http`.
- Raises `webrequest.WebError` with a plain message that names only the server, for example "api.met.no answered 404 Not Found". The rest of the address is left out, because it may hold an API key or a location.
- Don't catch `WebError` unless the plugin can show something without new data (for example a saved forecast). PaperPi then writes the message to the log and tries again at the plugin's next update.
- Looking up the server's address (DNS) has no time limit of its own; the plugin's time limit covers it.

## Refresh

`refresh` is the suggested number of seconds between updates, at least 5; the user can change it. Set `refresh_on_minute=True` for clocks, so updates start just after the minute changes.

## Level

`level` is the suggested level: `"rotation"` (the default: it takes turns with the other plugins), `"interrupt"` (it takes over the screen while it has something to show) or `"alert"` (see `docs/decisions/plugin-scheduling.md`). A plugin that only has something now and then, such as a music player, suggests `level="interrupt"` and says so in its `description`. The user's `level` setting always wins.

## Storage

`context.storage` has two limits, which PaperPi applies at start and after an update (at most once every 5 minutes):
- files not changed for `storage_days` days (default 30) are removed; 0 keeps them;
- when the folder holds more than `storage_mb` megabytes (default 500), the files changed longest ago are removed until it fits.

A plugin that needs more, such as a photo album, suggests its own values in its `Plugin(...)`, for example `storage_mb=20_000, storage_days=0`. The user's `storage_mb` and `storage_days` settings always win. A file written again at every update (such as a saved forecast) never counts as old. A file that is only read (such as a login token) does get old: write it again within `storage_days`, or suggest `storage_days=0`. Links in the folder are not followed and not removed.

Any file may have been removed since the last update (over a limit, or by hand): handle a missing file like a first run. When `context.low_disk` is `True` (less than 2 GB free), don't save new files. PaperPi does not stop you, but the disk is shared with the rest of the system.

## Rules

- **Each update runs in its own short-lived process.** Nothing stays in memory between updates. Save what you need to keep in `context.storage`.
- **Each update has a time limit** (60 seconds unless the user changes it). A plugin that takes longer is stopped, together with any programs it started. Errors and crashes are reported and don't affect PaperPi or other plugins.
- **Don't start programs that detach themselves** from the plugin (for example with `start_new_session=True`): PaperPi can't stop those. A plugin also can't use Python's `multiprocessing` to start its own worker processes.
- **Make `__init__.py` quick to import.** PaperPi imports it in its main program to check the config file. Import large packages inside `fetch` or `draw`.
- **Never use the screen or its driver.** Only PaperPi does that.
- **Log with `logging.getLogger(__name__)`.** The lines go to PaperPi's log (the web interface's Full log) under that logger's name, e.g. `paperpi.plugins.met_no`, with secret settings replaced by `****`. Info lines and up are kept in memory (debug lines only when PaperPi runs with `-v`), warnings and errors also in PaperPi's log file. Lines of the libraries the plugin uses come too. At most 100 lines per update or helper search are kept (then one line says the rest were left out), so don't log in a loop.

## Try it and test it

```bash
uv run paperpi render <type>                 # sample data, writes <type>.png
uv run paperpi render <type> --live          # real data
uv run paperpi render <type> --set key=value --layout <name> --size 800x480 --mode bw
```

Each `paperpi render` gives the plugin a new, empty `storage` folder and deletes it afterwards, so files saved by earlier updates are not there.

The tests check every plugin automatically:
- `tests/test_all_plugins.py`: it loads, has a README and help texts, and its sample draws in every layout on several screen sizes and modes.
- `tests/test_images.py`: its sample images match the reference images in `tests/images/`.
  - For a new plugin, the first run saves its reference images and fails once on purpose, so you look at them. Check them by eye and run the tests again.
  - After an intended change, make new references with `PAPERPI_UPDATE_IMAGES=1 uv run pytest tests/test_images.py` and check them by eye.
  - To also test settings other than the defaults, add them to `VARIANTS` in `tests/test_images.py`, e.g. `{"basic_clock": {"12h": {"hours": 12}}}`.
