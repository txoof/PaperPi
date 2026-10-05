# Writing a plugin

A plugin puts something on the screen: a clock, the weather, the song that is playing. This page shows how to write one. The reasons behind the rules are in [`decisions/plugin-interface.md`](decisions/plugin-interface.md). The simplest complete example is [`basic_clock`](../src/paperpi/plugins/basic_clock/).

## What a plugin is

A folder `src/paperpi/plugins/<type>/`, where `<type>` is lowercase letters, digits and `_`:

| File | What it holds |
|---|---|
| `__init__.py` | the settings, `fetch`, `draw`, the sample data, and `PLUGIN` |
| `layouts.py` | the layouts: what goes where on the screen |
| `README.md` | what it shows, where the data comes from, its settings |

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
)
```

## One update, step by step

1. PaperPi starts a new process for the update (see "Rules" below).
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

## Settings

Each setting is a field of the plugin's `Settings` class, with a type, a default and a short help text (`description`). From this one description PaperPi checks the config file, and later builds the web interface's form and the docs.

- Every setting needs a default.
- Don't use the names of the shared settings, which every `[[plugin]]` block already has: `name`, `type`, `enabled`, `level`, `display_time`, `refresh`, `time_limit`, `layout`.

In the config file, the plugin's settings sit in its `[[plugin]]` block:

```toml
[[plugin]]
name = "Clock"
type = "basic_clock"
hours = 12
```

## Layouts

`LAYOUTS` maps names to epdlib layouts (see [epdlib's layout guide](https://github.com/txoof/epdlib/blob/main/docs/layouts.md)). The first one is the default; the user can pick another with `layout = "..."`. A layout is a dictionary, or a function that makes one from the settings, for layouts that depend on a setting.

Give every text block a `sample`: the widest text it normally shows (`"88:88"` for a clock). The font size is then chosen once, so it doesn't change between updates.

## Refresh

`refresh` is the suggested number of seconds between updates; the user can change it. Set `refresh_on_minute=True` for clocks, so updates start just after the minute changes (used by the scheduler, M4 part 2).

## Rules

- **Each update runs in its own short-lived process.** Nothing stays in memory between updates. Save what you need to keep in `context.storage`.
- **Each update has a time limit** (60 seconds unless the user changes it). A plugin that takes longer is stopped, together with any programs it started. Errors and crashes are reported and don't affect PaperPi or other plugins.
- **Keep `__init__.py` light.** PaperPi imports it to check the config. Import large packages inside `fetch` or `draw`.
- **Never talk to the screen.** Only PaperPi does that.

## Try it and test it

```bash
uv run paperpi render <type>                 # sample data, writes <type>.png
uv run paperpi render <type> --live          # real data
uv run paperpi render <type> --set key=value --layout <name> --size 800x480 --mode bw
```

The tests check every plugin automatically:
- `tests/test_all_plugins.py`: it loads, has a README and help texts, and its sample draws in every layout on several screen sizes and modes.
- `tests/test_images.py`: its sample images match the reference images in `tests/images/`. For a new plugin, or after an intended change, make new references with `PAPERPI_UPDATE_IMAGES=1 uv run pytest tests/test_images.py` and check them by eye.
