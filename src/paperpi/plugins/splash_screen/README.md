# splash_screen

Shows PaperPi's name, its version and the address of its web page (https://github.com/txoof/PaperPi), in large text. It needs no network. Ported from v1.

The version is the one of the PaperPi that is running, for example `2.0.0`.

In v1 this picture was shown once when PaperPi started, before the first plugin, if `splash = True` was set. In v2 it is a plugin like any other: add a `[[plugin]]` block for it, and it takes its turn with the other plugins. v2 doesn't (yet) show it only at start.

## Layouts

| Layout | Shows |
|---|---|
| `splash` (default) | the name in large letters, the version below it, and the web address on two lines, as in v1 |

## Settings

None of its own, only the settings every plugin has (see the main [README](../../../../README.md)).

It suggests a refresh every hour: nothing it shows changes while PaperPi runs.

In the config file:

```toml
[[plugin]]
name = "Splash Screen"
type = "splash_screen"
```

Try it without a screen: `uv run paperpi render splash_screen --size 800x480 --mode bw`.

The name is in [Anton](https://fonts.google.com/specimen/Anton) by The Anton Project Authors, as in v1. v1 used Dosis for the version and the address; v2 uses [Lato](https://fonts.google.com/specimen/Lato) Bold by Łukasz Dziedzic. Both are under the SIL Open Font License ([`fonts/Anton-OFL.txt`](../../fonts/Anton-OFL.txt), [`fonts/Lato-OFL.txt`](../../fonts/Lato-OFL.txt)), in PaperPi's shared fonts folder.

## Sample images

The sample images show version 2.0.0. All sample images are in [`tests/images/`](../../../../tests/images/), named `splash_screen-splash-<screen>.png`, where `<screen>` is `9in7` (9.7", 1200x825, 16 grays), `7in5` (7.5", 800x480, black and white) or `5in65` (5.65", 600x448, 7 colours).

| 9.7" | 7.5" black and white | 5.65" 7 colours |
|---|---|---|
| ![9in7](../../../../tests/images/splash_screen-splash-9in7.png) | ![7in5](../../../../tests/images/splash_screen-splash-7in5.png) | ![5in65](../../../../tests/images/splash_screen-splash-5in65.png) |
