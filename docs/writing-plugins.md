# Writing a plugin

A plugin puts something on the screen: a clock, the weather, the song that is playing. This page shows how to write one. The reasons behind the rules are in [`decisions/plugin-interface.md`](decisions/plugin-interface.md). The simplest complete example is [`basic_clock`](../src/paperpi/plugins/basic_clock/).

## What a plugin is

A folder `src/paperpi/plugins/<type>/`. `<type>` is the plugin's name in the config file: it starts with a lowercase letter, followed by lowercase letters, digits and `_`.

| File | What it holds |
|---|---|
| `__init__.py` | the settings, `fetch`, `draw`, the sample data, and `PLUGIN` |
| `layouts.py` | the layouts: what goes where on the screen |
| `README.md` | what it shows, where the data comes from, its settings |

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
    description="The time, and optionally the date, in large text.",
    settings=Settings,
    layouts=LAYOUTS,
    fetch=fetch,
    draw=draw,
    sample=datetime(2026, 10, 5, 10, 42),
    refresh=60,
    refresh_on_minute=True,
)
```

## One update, step by step

1. PaperPi starts a new process for the update. A process is a running program with its own memory; when it ends, its memory is given back (see "Rules" below).
2. `fetch(context)` gets the data and says whether there is something to show:
   - `return NOTHING`: nothing to show right now (for example the music is stopped)
   - `return ready(data)`: here is data to show
   - `return alert(data)`: here is data, and it is an alert
3. `draw(data, context)` returns a dictionary with a value for each block of the layout, for example `{"time": "10:42"}`. PaperPi draws the layout with epdlib.
4. The image goes back to PaperPi and the process exits.

For tests and sample images, step 2 is skipped and `sample` is drawn instead. So every plugin can draw an image without network access, and `draw` must work with the sample data.

`context` holds:

| Field | What it is |
|---|---|
| `settings` | the plugin's own settings, already checked |
| `width`, `height` | the size of the area to draw, in pixels |
| `mode` | what the screen can show (an epdlib `ScreenMode`: black and white, gray levels or colours) |
| `storage` | the plugin's own folder for saved files, e.g. downloaded data |
| `layout` | the name of the layout to draw |
| `status` | only for the `default` plugin: how many plugins are not working (`failing`, `total`) |

## Settings

Each setting is a field of the plugin's `Settings` class, with a type, a default and a short help text (`description`). From this one description PaperPi checks the config file, and later builds the web interface's form and the docs.

- Every setting needs a default.
- Don't use the names of the shared settings, which every `[[plugin]]` block already has: `name`, `type`, `enabled`, `level`, `display_time`, `refresh`, `time_limit`, `layout`, `alert_reminder`, `alert_max_time`.
- Use `pydantic.SecretStr` as the type for API keys and passwords. PaperPi then never shows their values in error messages or logs.

In the config file, the plugin's settings go in its `[[plugin]]` block:

```toml
[[plugin]]
name = "Clock"
type = "basic_clock"
hours = 12
```

## Layouts

`LAYOUTS` maps names to epdlib layouts (see [epdlib's layout guide](https://github.com/txoof/epdlib/blob/main/docs/layouts.md)). The first one is the default; the user can pick another with `layout = "..."`. A layout is a dictionary, or a function that makes one from the settings, for layouts that depend on a setting.

Give every text block a `sample`: the widest text it normally shows (`"88:88"` for a clock). The font size is then chosen once, so it doesn't change between updates.

## Web requests

Use PaperPi's helper `paperpi.webrequest` for every download. It applies the time and size limits (10 s to connect, 30 s in total, at most 20 MB), retries once after 5 s when the server can't be reached or is busy, and unpacks gzip.

```python
from paperpi import webrequest

answer = webrequest.get(url, contact=context.settings.email)
data = answer.json()
```

- `contact`: an email or web address, sent to the server so it knows whom to ask about problems. Some services, like met.no, require it.
- `if_modified_since=`: the `last_modified` of an earlier answer. If nothing changed since, the answer is `not_modified` and has no content. Save `last_modified` and the data in `context.storage`, so the next update can ask.
- When the request fails, `webrequest.WebError` is raised with a plain message, for example "api.met.no/weatherapi/locationforecast/2.0/complete answered 404 Not Found". The message leaves out the part after `?`, because it may hold an API key. Let it pass up unless the plugin can show something without the data.

## Refresh

`refresh` is the suggested number of seconds between updates, at least 5; the user can change it. Set `refresh_on_minute=True` for clocks, so updates start just after the minute changes.

## Rules

- **Each update runs in its own short-lived process.** Nothing stays in memory between updates. Save what you need to keep in `context.storage`.
- **Each update has a time limit** (60 seconds unless the user changes it). A plugin that takes longer is stopped, together with any programs it started. Errors and crashes are reported and don't affect PaperPi or other plugins.
- **Don't start programs that detach themselves** from the plugin (for example with `start_new_session=True`): PaperPi can't stop those. A plugin also can't use Python's `multiprocessing` to start its own worker processes.
- **Make `__init__.py` quick to import.** PaperPi imports it in its main program to check the config file. Import large packages inside `fetch` or `draw`.
- **Never use the screen or its driver.** Only PaperPi does that.

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
