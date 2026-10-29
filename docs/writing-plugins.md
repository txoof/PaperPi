# Writing a plugin

A plugin puts one kind of information on the screen: a clock, the weather, the song that is playing. This page walks you through making your own, from a working start to a plugin that comes with PaperPi. The exact rules for every part are on the [Plugin reference](plugin-reference.md) page.

You need a copy of PaperPi's code to work in, set up as described in [Running from source](development.md). You don't need a screen: PaperPi can draw a plugin to a picture file.

## 1. Make the plugin

Choose a **type**: the plugin's name in the code and the config file. It is lowercase letters, digits and `_`, starting with a letter, for example `bus_times`. Then run:

```bash
uv run paperpi new-plugin bus_times
```

This makes the folder `src/paperpi/plugins/bus_times/` with three files:

| File | What it holds |
|---|---|
| `__init__.py` | the plugin: its settings, how it gets its data, and what it draws |
| `layouts.py` | the layouts: where each piece of text goes on the screen |
| `README.md` | the instructions for people who use it; the web interface shows them |

It is already a complete plugin: it shows a greeting and today's date. The plugin's name in the web interface is made from the type ("Bus times"); `--title "Next buses"` gives it another one.

## 2. See it

```bash
uv run paperpi render bus_times
```

This draws the plugin and saves the picture as `bus_times.png`, at the size of the 9.7" screen. Open it to see what the plugin draws. Other sizes and kinds of screen:

```bash
uv run paperpi render bus_times --size 800x480 --mode bw         # a black-and-white 7.5" screen
uv run paperpi render bus_times --layout greeting                # another layout
uv run paperpi render bus_times --set greeting="Good morning"    # another setting
```

Run `paperpi render` again after each change below to see the result.

## 3. How it works

Open `__init__.py`. A plugin has two functions, which PaperPi calls at every update:

```python
def fetch(context: Context):
    return ready(date.today())
```

**`fetch` gets the data.** Here it is only today's date; a real plugin downloads something here, such as the next departures from a bus company's website. It ends with `return ready(data)` when there is something to show, or `return NOTHING` when there isn't (for example, no buses run at night).

```python
def draw(today: date, context: Context) -> dict:
    values = {"greeting": context.settings.greeting}
    if context.layout == "greeting_date":
        values["date"] = f"{today:%A} {today.day} {today:%B}"
    return values
```

**`draw` turns the data into text** for each block of the layout: here the greeting and the date. PaperPi then draws the layout with these texts and puts the picture on the screen.

At the end of the file, `PLUGIN = Plugin(...)` tells PaperPi about the plugin: its type, its name and description in the web interface, its settings and layouts, and how often it updates (`refresh`, in seconds).

Each update runs separately from PaperPi, with a time limit of a minute. So a plugin that crashes or hangs never stops PaperPi or the other plugins.

## 4. Add a setting

Settings are what the user can change on the plugin's settings page. They are in the `Settings` class:

```python
class Settings(PluginSettings):
    greeting: str = Field("Hello", max_length=60, description="The text shown on the screen")
    stop: str = Field("", max_length=20, description="The code of the bus stop, e.g. 7300301")
```

Each setting has a type (`str` for text, `int` for whole numbers, `bool` for on or off), a default, and a help text (`description`) that the web interface shows next to its field. Write the help text for someone at home who is not a programmer. Your code reads the setting as `context.settings.stop`.

A setting the plugin can't work without, such as the stop above, can be made **required**: then PaperPi doesn't show the plugin until it is filled in, and the web interface says it is missing. See [Settings](plugin-reference.md#settings) in the reference; there you also find search boxes that fill in a setting, such as a place by its name.

## 5. Change the layout

Open `layouts.py`. A layout is a list of blocks, each with a `name` (the key in what `draw` returns), a `type` (`"text"` or `"image"`) and how it sits on the screen:

```python
(
    {
        "name": "date",
        "type": "text",
        "size": 1,  # its share of the height: the greeting has 3
        "sample": "Wednesday 30 September",  # the widest text it shows
        "align": "center",
        "padding": PADDING,
    },
)
```

The `sample` is the widest text the block normally shows. PaperPi picks the font size so the sample fits, and keeps it, so the text doesn't change size from one update to the next. Everything a layout can do is in [epdlib's layout guide](https://github.com/txoof/epdlib/blob/main/docs/layouts.md).

`LAYOUTS` at the end lists the layouts; the first is the default. The user picks another one on the settings page. Give each layout a plain name in `layout_titles` in `__init__.py`.

## 6. Get data from the internet

Use PaperPi's `webrequest` for every download. It has sensible time limits, tries once more when a server doesn't answer, and gives a clear error message:

```python
from paperpi import webrequest


def fetch(context: Context):
    answer = webrequest.get(f"https://example.org/departures?stop={context.settings.stop}")
    return ready(answer.json())
```

Add `network="internet"` to `PLUGIN = Plugin(...)`, so the Plugin Library shows "Requires internet". If the download fails, don't catch the error: PaperPi logs it and tries again at the next update. More in [Web requests](plugin-reference.md#web-requests).

## 7. Sample data

`sample=` in `PLUGIN = Plugin(...)` is data in the same form as `fetch` returns, made up but realistic. PaperPi draws it for the tests, for the example pictures in the Plugin Library, and for the preview when the real data can't be fetched. So a plugin can always be drawn, also without a network. When your `fetch` changes what it returns, change the sample too.

## 8. Write the README

`README.md` is for the people who use the plugin: what it shows, where its data comes from, what to set up first, and each setting. The web interface links to it from the Plugin Library, and the manual makes a page for each plugin from it. Look at the README of a plugin like yours, for example [met_no](https://github.com/txoof/PaperPi/blob/main/src/paperpi/plugins/met_no/README.md) for one that downloads data.

## 9. Test it

```bash
uv run pytest tests/test_all_plugins.py tests/test_images.py
```

`test_all_plugins.py` checks that every plugin loads, has help texts and a README, and that its sample draws in every layout on several screens. `test_images.py` compares each plugin's sample pictures with saved reference pictures in `tests/images/`, so a change in how a plugin looks never goes unnoticed. The first run for a new plugin saves its reference pictures and fails once on purpose: look at the pictures, then run the tests again. More in [Testing](plugin-reference.md#testing).

## 10. Use it and share it

Once the plugin is in `src/paperpi/plugins/`, it is in the Plugin Library of every PaperPi run from that copy of the code. To try it on the screen: `uv run paperpi run` (see [Running from source](development.md)).

To have it come with PaperPi, open a pull request on [GitHub](https://github.com/txoof/PaperPi). See [CLAUDE.md](https://github.com/txoof/PaperPi/blob/main/CLAUDE.md) for how the work is organised.

## Examples to read

| Plugin | Shows how to |
|---|---|
| [`basic_clock`](https://github.com/txoof/PaperPi/tree/main/src/paperpi/plugins/basic_clock) | the simplest plugin; update on the minute |
| [`met_no`](https://github.com/txoof/PaperPi/tree/main/src/paperpi/plugins/met_no) | download data, a required email setting, a place search, draw icons |
| [`word_clock`](https://github.com/txoof/PaperPi/tree/main/src/paperpi/plugins/word_clock) | colours, blocks placed at random |
| [`lms_client`](https://github.com/txoof/PaperPi/tree/main/src/paperpi/plugins/lms_client) | an interrupt plugin: only shows something while music plays |
| [`nl_openbaar_vervoer`](https://github.com/txoof/PaperPi/tree/main/src/paperpi/plugins/nl_openbaar_vervoer) | many settings in groups, an API key, stop search |
