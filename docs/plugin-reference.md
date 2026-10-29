# Plugin reference

The exact rules for each part of a plugin. To start a plugin, follow [Writing a plugin](writing-plugins.md) first.

## The folder

A plugin is a folder `src/paperpi/plugins/<type>/`. `<type>` is the plugin's name in the config file: lowercase letters, digits and `_`, starting with a letter. The folder holds `__init__.py` (which defines `PLUGIN`), `layouts.py` and `README.md`. `paperpi new-plugin <type>` makes all three from a template.

The README is shown in two places. The web interface links to it from the Plugin Library; there its first heading, its pictures and its "Sample images" section are left out (the pictures are not installed), links to other plugins' READMEs open their page, and other links that are not web addresses become plain text. This manual makes a page for each plugin from it, with its settings and sample pictures.

## `PLUGIN`

`PLUGIN = Plugin(...)` describes the plugin to PaperPi.

| Argument | What it is |
|---|---|
| `type` | the type, the same as the folder's name |
| `title` | the plain name in the web interface, at most 40 characters ("Clock"). A plugin added twice gets "Clock 2". |
| `description` | one or two sentences for the Plugin Library, written for someone at home |
| `settings` | the `Settings` class (see [Settings](#settings)) |
| `layouts` | the layouts, by name; the first is the default (see [Layouts](#layouts)) |
| `layout_titles` | a plain name for each layout, at most 40 characters. Every plugin that comes with PaperPi has one for each layout (a test checks). |
| `fetch`, `draw` | the two functions of an update (see [One update](#one-update)) |
| `sample` | made-up data in the form `fetch` returns, drawn for tests and example pictures |
| `refresh` | the suggested seconds between updates, at least 5 (see [Refresh and level](#refresh-and-level)) |
| `refresh_on_minute` | `True` for clocks: updates start just after the minute changes |
| `level` | the suggested level: `"rotation"` (the default), `"interrupt"` or `"alert"` |
| `network` | `"internet"` (a website or online service) or `"home"` (a device on the home network, such as a music server). The Library shows "Requires internet" or "Uses home network". |
| `setup` | one sentence, at most 200 characters, when something must be set up outside PaperPi first, such as another program. The Library then shows "Requires setup", the sentence and a link to the README. A plugin with required settings gets "Requires setup" by itself. |
| `helpers` | search boxes for the settings page (see [Setting helpers](#setting-helpers)) |
| `storage_mb`, `storage_days` | suggested limits for its storage folder (see [Storage](#storage)) |

## One update

At every update:

1. PaperPi starts a new process for the update: a separate running program with its own memory, which is given back when it ends.
2. `fetch(context)` gets the data and says whether there is something to show. It returns one of:
    - `NOTHING`: nothing to show right now (for example, the music is stopped);
    - `ready(data)`: here is data to show;
    - `alert(data)`: here is data, and it is an alert.
3. `draw(data, context)` returns a dictionary with a text (or picture) for each block of the layout, for example `{"time": "10:42"}`. It may also return a `Drawn` (see [Moving blocks and colours](#moving-blocks-and-colours)).
4. PaperPi draws the layout, the picture goes back to PaperPi, and the process ends.

For tests, example pictures and the preview, step 2 is skipped and `sample` is drawn instead. So `draw` must work with the sample data, and the sample should look like real data: the web interface's preview also shows it when the real data fails, takes too long, has nothing to show or still needs settings.

`context` has:

| Field | What it is |
|---|---|
| `settings` | the plugin's own settings, already checked |
| `width`, `height` | the size of the picture to draw, in pixels |
| `mode` | what the screen can show: black and white, gray levels or colours (an epdlib `ScreenMode`) |
| `layout` | the name of the layout to draw |
| `storage` | the plugin's own folder for saved files (see [Storage](#storage)) |
| `low_disk` | `True` when less than 2 GB is free on PaperPi's disk: don't save more files then. Replacing a file you already have is fine. |
| `status` | only for the `default` plugin: how many plugins are not working |

## Settings

Each setting is a field of the plugin's `Settings` class, with a type, a default and a help text (`description`):

```python
from pydantic import Field
from paperpi.plugin import PluginSettings, setting


class Settings(PluginSettings):
    hours: Literal[12, 24] = Field(24, description="12-hour (3:45 PM) or 24-hour (15:45) clock")
    lat: float | None = setting(None, required=True, ge=-90, le=90, description="Latitude")
```

From this one description PaperPi checks the config file, writes the plugin's block in the example config, builds the settings page of the web interface, and makes the plugin's page in this manual.

**The rules:**

- Every setting needs a default, and the default must be a valid value: a test writes every setting of every plugin into a config file and loads it.
- Don't use the names of the settings every plugin already has: `id`, `name`, `type`, `enabled`, `level`, `display_time`, `refresh`, `time_limit`, `layout`, `alert_reminder`, `alert_max_time`, `storage_mb`, `storage_days`.
- Use `pydantic.SecretStr` for API keys and passwords. PaperPi then never shows them in error messages or logs.
- Write the help text for someone at home who is not a programmer.

**Required settings.** A setting the plugin can't work without (a place, an email address, an API key) is made with `setting(..., required=True)` instead of `Field`. It takes the same arguments. Its default must be "not set": `None`, empty text or an empty `SecretStr`. Until every required setting is filled in, the plugin is not shown and not counted as broken; the web interface and `paperpi list` say which settings are missing.

**Groups.** A plugin with many settings can put them in groups with `setting(..., group="Stop 1")`. The settings page shows each group as a section that opens and closes, in the order its first setting comes in the code. Settings without a group come first. `nl_openbaar_vervoer` has a group for each stop.

**How each type is shown** on the settings page:

| Type | Field |
|---|---|
| `Literal["a", "b"]` | a choice list |
| `bool` | a check box |
| `int`, `float` | a number field, with the `ge`, `gt`, `le` and `lt` limits |
| `str` | a text field, with `max_length` |
| `SecretStr` | a password field |
| a tuple or list of a `Literal` | a list to tick |
| anything else | shown as it is in the file, to be changed there |

**Links in help texts.** A help text may link to the plugin's README or a web page: `[the README](readme)` or `[text](https://...)`. The settings page shows a link; the config file shows only the text.

In the config file, the plugin's settings go in its `[[plugin]]` block:

```toml
[[plugin]]
id = "basic_clock-5c1e0a7b"   # made by PaperPi: the type and 8 random letters and digits
type = "basic_clock"
hours = 12
```

## Setting helpers

Some settings are hard to fill in by hand, such as a place's latitude and longitude or a stop's code. A **helper** is a search box on the settings page, just before the setting it fills. The user types something, PaperPi shows a list of choices, and **Use** fills in the form (nothing is saved until **Save**).

**For a place**, use the ready-made helper: `paperpi.places.location_helper()` finds places by name and fills in `lat` and `lon`. Pass the names of your settings if they are called something else, and the names of optional settings for the height and the name shown on the screen, e.g. `location_helper(altitude="altitude", name="place")` as in `met_no`.

**Your own helper** is a `Helper` in `PLUGIN`'s `helpers`, by name; the first setting it fills names it with `setting(..., helper="<name>")`:

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

**What `find(query)` gets:** `query.text` (what the user typed, at most 100 characters), `query.settings` (the settings in the form, checked as Save checks them) and `query.language` (the language the user's browser asks for first, e.g. `nl`).

**What it returns:** a list of choices, or `{"choices": [...], "note": "..."}` with a message for the whole result. Each choice is a dictionary with:

- `fill`: settings and the values **Use** puts in the form. Not secret settings, and not settings that are changed in the file.
- `show`: labels and texts that help the user choose; the first one is the heading.
- `link`: labels and web addresses (`http` or `https`), e.g. "See on map".

At most 10 choices are shown, each text on one line of at most 200 characters.

**Problems:** `raise HelperProblem("The API key was not accepted")` shows that message. Any other error shows "The search failed", with the details in PaperPi's log.

**More options** of `Helper`: `prompt` (the text above the box), `button`, `typed=False` (a button without a box), `needs` (settings that must be filled in first, e.g. an API key), and `source` and `source_link` (where the answers come from; say so when the typed text goes to an outside service).

**Safety:** each search runs in its own process with a time limit of 30 seconds. Secret settings are replaced with `****` in what a search returns. A search uses the form's values before they are saved, so never send a saved secret to a web address taken from the settings: someone could type their own address and get the key.

The `debugging` plugin has a helper to try this out.

## Layouts

`LAYOUTS` maps names to layouts (see [epdlib's layout guide](https://github.com/txoof/epdlib/blob/main/docs/layouts.md)). A layout is a dictionary, or a function that makes one from the settings, for layouts that depend on a setting. The first one is the default.

Give every text block a `sample`: the widest text it normally shows (`"88:88"` for a clock). The font size is then chosen once and stays the same.

### Fonts

Without a `font`, a text block uses DejaVu Sans. More fonts, each with its licence, are in `src/paperpi/fonts/`:

```python
from paperpi import fonts

{"name": "title", "type": "text", "font": fonts.LATO_BOLD}  # also fonts.LATO_ITALIC, fonts.ANTON
```

To add a font for every plugin, put the file and its licence in `src/paperpi/fonts/` and add a name for it in `src/paperpi/fonts/__init__.py`. A font only one plugin uses can stay in the plugin's folder, with its licence.

### Pictures the plugin draws itself

Draw bars, dots or icons at exactly the size they are shown. Resized pictures get blurred edges, which show as dots on black-and-white screens. This gives the size of a block:

```python
layout = PLUGIN.layout(context.layout, context.settings)
prepared = layout.prepare(context.width, context.height, context.mode)
width, height = prepared.content_size("bar")
```

A picture of that size is shown pixel for pixel. See `system_info` and `dec_binary_clock`.

### Moving blocks and colours

`draw` may return a `Drawn` instead of a dictionary:

```python
from paperpi.plugin import Drawn

return Drawn(values, seed=int(f"{now:%Y%m%d%H%M}"), colors=("yellow", "blue"))
```

- `seed`: blocks with `align` or `valign` set to `"random"` are placed somewhere else at each update. The same seed always gives the same place, so sample pictures and tests stay the same. Make it from the data: `word_clock` uses the time.
- `colors`: the text and background colour for blocks with `rgb_support: True`. For colour settings, use `paperpi.colors`: `ColorName` as the setting's type and `screen_colors(...)` to turn the choice into colours this screen can show. See `word_clock`.

## Web requests

Use `paperpi.webrequest` for every download:

```python
from paperpi import webrequest

answer = webrequest.get(url, contact=context.settings.email)
data = answer.json()
```

**Limits:** 10 seconds to connect, 30 seconds in all, at most 5 MB (more with `max_bytes=`).

**Options of `get`:**

- `contact`: an email or web address sent along, so the service knows whom to ask about problems. Some services, like met.no, require it: give the plugin a required setting for it, as `met_no` does with `email`.
- `headers`: more headers, for example an API key. They are only sent to the server of `url`, not to another server it redirects to.
- `if_modified_since`: the `last_modified` of an earlier answer. If nothing changed, `answer.not_modified` is `True` and the body is empty. Save `last_modified` and the data in `context.storage` for the next update.

**The answer** has `status`, `body` (the content as bytes), `headers` (with lowercase names), `url` (after redirects), `not_modified`, `last_modified` and `json()`.

**When something goes wrong:**

- It tries once more after 5 seconds when the server can't be reached, doesn't answer in time, breaks off, or answers 429 (too many requests) or 500, 502, 503 or 504 (server errors). Not for other answers, such as 404 (not found).
- It follows up to 3 redirects, never from `https` to `http`.
- It raises `webrequest.WebError` with a plain message that names only the server, for example "api.met.no answered 404 Not Found": the rest of the address may hold an API key or a location.
- Don't catch `WebError`, unless the plugin can show something without new data (for example a saved forecast). PaperPi logs the message and tries again at the next update.

## Refresh and level

`refresh` is the suggested number of seconds between updates, at least 5. Don't make it equal to the default display time (120 seconds): the new picture could then arrive just as the plugin's turn ends (a test checks). The user's own `refresh` setting always wins.

`level` is the suggested level: `"rotation"` takes turns with the other plugins, `"interrupt"` takes over the screen while it has something to show, `"alert"` takes over until the alert is over (see [Understanding Plugin Schedules](take-turns.md)). A plugin that only has something now and then, such as a music player, suggests `"interrupt"` and says so in its description. The user's `level` setting always wins.

## Storage

`context.storage` is the plugin's own folder, for files it keeps between updates (such as a downloaded forecast). PaperPi applies two limits to it, at start and after updates:

- files not changed for `storage_days` days (default 30) are removed; 0 keeps them;
- when the folder holds more than `storage_mb` megabytes (default 500), the oldest files are removed until it fits.

A plugin that needs more, such as a photo album, suggests its own values in `PLUGIN`, for example `storage_mb=20_000, storage_days=0`. The user's settings always win.

A file that is written again at every update never gets old. A file that is only read (such as a login token) does: write it again within `storage_days`, or suggest `storage_days=0`. Any file may have been removed since the last update, so handle a missing file like a first run.

## Rules

- **Each update runs in its own short-lived process.** Nothing stays in memory between updates: save what you need in `context.storage`.
- **Each update has a time limit** (60 seconds unless the user changes it). A plugin that takes longer is stopped, together with any programs it started. Its errors and crashes don't affect PaperPi or other plugins.
- **Don't start programs that detach themselves** (for example with `start_new_session=True`): PaperPi can't stop those. A plugin can't use Python's `multiprocessing` either.
- **Make `__init__.py` quick to import.** PaperPi imports it to check the config file. Import large packages inside `fetch` or `draw`.
- **Never use the screen.** Only PaperPi does that.
- **Log with `logging.getLogger(__name__)`.** The lines go to PaperPi's log, with secret settings replaced by `****`. At most 100 lines per update are kept, so don't log in a loop.

## Testing

Try a plugin without a screen:

```bash
uv run paperpi render <type>                 # sample data, writes <type>.png
uv run paperpi render <type> --live          # real data
uv run paperpi render <type> --set key=value --layout <name> --size 800x480 --mode bw
```

Each `render` gives the plugin a new, empty storage folder, and removes it afterwards.

The tests check every plugin automatically:

- `tests/test_all_plugins.py`: it loads, has a README and help texts, and its sample draws in every layout on several screen sizes and kinds, without text cut off.
- `tests/test_images.py`: its sample pictures match the reference pictures in `tests/images/`.
    - For a new plugin, the first run saves its reference pictures and fails once on purpose, so you look at them. Check them, then run the tests again.
    - After a change on purpose, make new references with `PAPERPI_UPDATE_IMAGES=1 uv run pytest tests/test_images.py`, and check them.
    - To also test settings other than the defaults, add them to `VARIANTS` in `tests/test_images.py`, e.g. `{"basic_clock": {"12h": {"hours": 12}}}`.
