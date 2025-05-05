
# PaperPi V0.5<!-- omit in toc -->

[![Spellcheck](https://github.com/ysadamt/PaperPi/actions/workflows/spellcheck.yml/badge.svg)](https://github.com/ysadamt/PaperPi/actions/workflows/spellcheck.yml)


**This version is compatible with Raspberry Pi OS Bullseye and does not work properly with Buster.**


|     |     |
|:---:|:---:|
|<img src=./paperpi/plugins/splash_screen/splash_screen.layout-L-sample.png alt="Splash Screen" width=400/> | <img src=./documentation/images/paperpiV3.gif alt="PaperPi" width=400 />|


## About PaperPi

PaperPi is a lovely, quiet, *slow internet* e-Paper radio. No loud colors, no busy animations, just a lovely selection of the information you want without buzz and distraction. PaperPi rotates through your choice of plugin screens at the pace you choose.

To get started, jump to the **[Setup Instructions](#setup_install)**.

### Why it's great

* Works with almost all of the [WaveShare](https://www.waveshare.com/product/displays/e-paper.htm) SPI displays out of the box with minimal setup or configuration
* Supports RGB screens
* Scales plugin output to match your display size from tiny 2" 1 bit displays all the way to 10" HD 8 bit displays
* Supports an open and hackable plugin architecture
* Easy install and configuration
* Quiet, low distraction display with just the content you want
* Looks great on your desk or in your living room

For information on building a frame, case and custom cable, see [these instructions](./documentation/Frame_Cable_Case.md).


## Plugins

PaperPi supports many different plugins and multiple layouts for each plugin that can provide different data. 
|     |     |
|:---:|:---:|
|<img src=./paperpi/plugins/lms_client/lms_client.two_column_three_row-RGB-sample.png alt="two_column_three_row layout" width=400/><br />LMS Client: `two_column_three_row` | <img src=paperpi/plugins/lms_client/lms_client.two_rows_text_only-L-sample.png alt="two_rows_text_only layout" width=400 /><br />LMS Client: `two_rows_text_only`|

Some plugins, marked with <font color="red">R</font><font color="green">G</font><font color="blue">B</font>, also support 7-Color Screens. 


### [Complete Plugins List](./documentation/Plugins.md)

**Plugin Samples**

| | | |
|:-------------------------:|:-------------------------:|:-------------------------:|
|<img src=./paperpi/plugins/librespot_client/librespot_client.layout-L-sample.png alt="librespot plugin" width=300 /><br />[LibreSpot (spotify) Plugin](./paperpi/plugins/librespot_client/README.md) <font color="red">R</font><font color="green">G</font><font color="blue">B</font>|<img src=./paperpi/plugins/word_clock/word_clock.layout-L-sample.png alt="word clock plugin" width=300 /><br />[Word Clock](./paperpi/plugins/word_clock/README.md) <font color="red">R</font><font color="green">G</font><font color="blue">B</font>|<img src=./paperpi/plugins/slideshow/slideshow.layout-L-sample.png alt="lms client plugin" width=300 /><br />[Slideshow](./paperpi/plugins/slideshow/README.md) <font color="red">R</font><font color="green">G</font><font color="blue">B</font>|
|<img src=./paperpi/plugins/moon_phase/moon_phase.layout-L-sample.png alt="decimal binary clock" width=300 /><br />[Moon Phase](./paperpi/plugins/moon_phase/README.md)|<img src=./paperpi/plugins/met_no/met_no.layout-L-sample.png alt="met_no plugin" width=300 /><br />[Met.no Weather](./paperpi/plugins/met_no/README.md) <font color="red">R</font><font color="green">G</font><font color="blue">B</font>|<img src=./paperpi/plugins/crypto/crypto.layout-L-sample.png alt="Crypto Currency Ticker" width=300 /><br />[Crypto Currency](./paperpi/plugins/crypto/README.md)|
|<img src=./paperpi/plugins/reddit_quote/reddit_quote.layout-L-sample.png alt="reddit/r/quotes" width=300 /><br />[Reddit Quotes](./paperpi/plugins/reddit_quote/README.md) <font color="red">R</font><font color="green">G</font><font color="blue">B</font>|<img src=./paperpi/plugins/xkcd_comic/xkcd_comic.layout-L-sample.png alt="XKCD Comic" width=300 /><br />[XKCD Comic](./paperpi/plugins/xkcd_comic/README.md)|<img src=./paperpi/plugins/basic_clock/basic_clock.layout-L-sample.png alt="Basic Clock" width=300 /><br />[Basic Clock](./paperpi/plugins/basic_clock/README.md)| |

See the [Developing Plugins](./documentation/developing_plugins.md) guide for more information on creating your own plugins.
## Changes

See the [Change Log](./documentation/Change_Log.md) for a complete list of updates

**V 0.5**

* PaperPi migrated to EPD Lib V0.6
* 7 Color, <font color="red">R</font><font color="green">G</font><font color="blue">B</font> screens now supported. **NB!** 2/3 Color screens are only supported in 1 bit black/white mode
* Stalled plugins now timeout after a configurable time


**V 0.4.1**

* PaperPi is no longer distributed as a PyInstaller frozen blob and now installs into `/usr/local/paperpi` and places an executable entry script in `/usr/local/bin/`.
* Plugins can now be edited easily in `/usr/local/paperpi/plugins/`
* Additional plugins can be placed in `/usr/local/paperpi/plugins` without rebuilding
* Add support for mirroring output 
* Add additional plugins
* Add mirror option

<a name="requirements"></a>

## PaperPi Requirements

PaperPi is compatible Raspberry Pi OS Bookworm. 

### Required Hardware

* Raspberry Pi (Pi 4, Pi 3, and Pi Zero)
* Raspberry Pi OS Bookworm
* [WaveShare EPD Screen](https://www.waveshare.com/product/displays/e-paper.htm) with PiHat
  * see the full list of currently [supported screens](#supportedScreens)
  * Note: HDMI screens are not supported

### Optional Hardware

* [HiFiBerry hat](https://www.hifiberry.com/shop/#boards) (*optional*)
  * The HiFiBerry DAC+ PRO and similar boards add high-quality audio output to the Pi so it can act as a display and also work as a LMS client player using squeezelite
  * GPIO 2x20 headers **must be added** to the HiFiBerry HAT to provide an interface for the WaveShare HAT.
  * HiFiBerry's [DAC+ Bundle](https://www.hifiberry.com/shop/bundles/hifiberry-dac-bundle-4/) with the following configuration is a good choice:
    * DAC+ Pro
    * Acrylic Case for (RCA) AND DIGI+
    * Raspberry Pi 4B 2GB (1GB should be sufficient as well)
    * 16GB SD Card
    * PowerSupply (USB C 5.1V/3A)
    * 2x20 Pin Male Header (required for WaveShare HAT)

### Optional Software

PaperPi plugins work with a variety of other software such as Logitech Media Server and Spotify. Check the [Plugin documentation](./documentation/Plugins.md) for further instructions

<a name="setup_install"> </a>

## Install & Setup

PaperPi requires only small amount of setup and is packaged with amateurs in mind. By default PaperPi will install as a daemon service that will start at boot.

Check here if you'd like a [step-by-step guide](./documentation/step_by_step_instructions.md).

### Install

To get started, copy and paste the following command into a terminal window on your Raspberry Pi to download the latest stable version of PaperPi and automatically start the install and setup process.

**Stable**

`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/ysadamt/PaperPi/main/install/remote_install.sh)"`


**Development**

`curl -fsSL https://raw.githubusercontent.com/ysadamt/PaperPi/main/install/remote_install.sh | /bin/bash -s -- -b development`

**Self Install**

If you would rather install PaperPi yourself without running a remote script, [clone this repo](https://github.com/ysadamt/PaperPi.git) and run `./install/install.sh` from within the repo root.

**Other Branches**

If you would like to remote install from a different remote branch, use:

`curl -fsSL https://raw.githubusercontent.com/ysadamt/PaperPi/main/install/remote_install.sh | bash -s -- -b REPLACE_WITH_BRANCH_NAME`


### Setup

**Daemon Mode**

The installer should prompt you to edit `/etc/default/paperpi.ini`. At minimum you must add your EPD Screen and enable several plugins. A complete list of supported EPD Screens are [listed below](#supportedScreens).

Any changes to the PaperPi configuration require a restart of the service:

`sudo systemctl restart paperpi-daemon.service`

To disable the service from starting on boot, run the command:

`sudo systemctl disable paperpi-daemon.service`

**On Demand**

If you would rather run PaperPi on-demand rather than a daemon service you can run it as regular user (e.g. pi) by running `/usr/local/bin/paperpi`. A new configuration file will be created in your user's directory. Make sure to edit this file and add, at minimum, your EPD Screen.

PaperPi can be run on demand in daemon mode using `paperpi -d`

### Configuration

The configuration file is kept in `/etc/default/paperpi.ini` for the daemon and `~/.config/com.ysadamt.paperpi/paperpi.ini` when run as a user. 

The configuration file is written as a `ini` style file. Each section is defined by square brackets `[Section Name]`. White space and comments are ignored. Variables are formatted one-per-line: `variable_name = value`. Strings should not be quoted.

The configuration file has sample values for each plugin that should work for most installations. Plugins such as the LMS and Spotify plugins require configuration.

**Configuration Structure**

`[main]`: The global configuration variables

* `display_type` (string): Name of [display](#supported-screens)
* `vcom` (float): negative floating point value printed on the ribbon cable of HD screens (e.g. -1.93)
* `max_refresh` (integer): maximum number of screen refreshes before a total (flashing) wipe (only applies to HD screens)
* `splash` (boolean): True to display the splash screen on boot; False to launch directly into the display loop
* `rotation` (integer): rotate the screen 0, 90, 180, 270 degrees. Most screens are oriented with the ribbon cable at the bottom.
* `mirror` (boolean): True to flip the content. This is useful if everything appears backwards on your screen

`[Plugin: Human Readable Plugin Name]`: Per-plugin configuration

Plugins configurations are always in square brackets and **must** start with the string `Plugin: `. Plugins that have leading characters are ignored and treated as disabled.

The same plugin can be configured multiple times in the same instance. For example, you may want to track multiple LMS players, or display weather for multiple locations.

Each plugin has the following required values and *may* have values specific to the configuration of the plugin. For example your location. Check the [Plugin Documentation](./documentation/Plugins.md) for more information.

* `plugin` (string): plugin_name - this is the exact name of the plugin and can be found on the plugin documentation page
* `layout` (string): name of layout to use. See the plugin page for an example of every supported layout for each plugin. Every plugin should have a default layout called `layout`.
* `refresh_rate` (integer): time in seconds before refreshing the data for this plugin. Some plugins connect to external APIs that discourage high rates of requests. A value of around 30-120 seconds is probably good for most plugins.
* `min_display_time`  (integer): time in seconds that represents the minimum amount of time the plugin should be displayed before cycling to another plugin. Setting this to a value lower than the screen-clear time for your screen is a mistake. 
* `max_priority` (integer): lower value plugins take priority over higher values. This should be left alone unless you're sure you know what you are doing.

Most plugins should have a maximum priority of 2. This is the default level for plugins that passively cycle. Some plugins such as the Spotify and LMS plugin set their priority to something like 3 when there is no relevant information to display. The value of 3 excludes them from the display loop. When music starts playing, the priority moves to a value of 0 to ensure that the rest of the plugins are displayed. Check the LMS plugin documentation for a full explanation.

### Uninstall

To uninstall PaperPi, run `/usr/bin/local/paperpi/install.sh` with either `-u` to uninstall or `-p` to uninstall and remove all configuration files.

## Command Reference

```
usage: paperpi.py [-h] [--add_config plugin user|daemon] [-c CONFIG_FILE.ini]
                  [-l LOG_LEVEL] [-d] [--list_plugins]
                  [--plugin_info [plugin|plugin.function]]
                  [--run_plugin_func plugin.function [optional_arg1 arg2 argN ...]]
                  [-V]

optional arguments:
  -h, --help            show this help message and exit
  --add_config plugin user|daemon
                        copy sample config to the user or daemon configuration
                        file
  -c CONFIG_FILE.ini, --config CONFIG_FILE.ini
                        use the specified configuration file
  -l LOG_LEVEL, --log_level LOG_LEVEL
                        change the log output level
  -d, --daemon          run in daemon mode (ignore user configuration if
                        found)
  --list_plugins        list all available plugins
  --plugin_info [plugin|plugin.function]
                        get information for plugins and user-facing functions
                        provided by a plugin
  --run_plugin_func plugin.function [optional_arg1 arg2 argN ...]
                        run a user-facing function for a plugin
  -V, --version         display version and exit
```

`--add_config plugin user|daemon`: add a configuration file for *plugin* to the *user* configuration  or *daemon* configuration files

`-c/--config CONFIG_FILE.ini`: Use the specified *CONFIG_FILE* instead of the default

`-l/--log_level DEBUG|INFO|WARNING|ERROR`: Specify the logging level from the command line

`--list_plugins`: List all plugins that have been found.

`--plugin_info plugin|plugin.function`: Print help information for a *plugin* and all of it's helper functions or a specific *plugin.function*

`--run_plugin_func plugin.function` Some plugins provide helper functions such as determining the LAT/LON of a location (met_no, moon_phases) or finding local Logitech Media Servers (lms_client). `--run_plugin_func` runs a plugin helper function. Use `--plugin_info` to learn more.

`-V/--version`: Display version information and exit

## Developing PaperPi

If you would like to develop for PaperPi or create [plugins](./documentation/Plugins.md) for PaperPi, you will likely need a working build environment. You can also hack on fonts and layouts directly on an existing install. 

### Development Requirements

* python 3.11+

**Create a Build Environment**

1. Clone the repo: `https://github.com/ysadamt/PaperPi`
2. Run `$ ./utilities/init_devel_environment.sh` to create a build environment
    * This will check for all necessary libraries and python modules and create a local venv for development

## Contributing

PRs are always welcome! Plugins can be pure python, but should follow the [guide provided](./documentation/developing_plugins.md).

<a name="supportedScreens"> </a>

## Supported Screens

Virtually all WaveShare E-Paper screens are now supported!

* **WaveShare 7-Color displays are now fully supported**
* HD IT8951 Screens support partial refresh, fast update and 8 bit gray scale
* 2 and 3 Color screens (b/c variants) are only supported in Black/White mode

Most of the WaveShare screens that support 2/3 color output will also work with with the non-colored driver. Using the 1 bit driver can yield significantly better update speeds. For example: the `waveshare_epd.epd2in7b` screen takes around 15 seconds to update even when refreshing a 1 bit image, but can be run using the `waveshare_epd.epd2in7` module in 1-bit mode which takes less than 2 seconds to update.


|Screen            |Supported      |Mode          |
|:-----------------|:--------------|:-------------|
|00. epd13in3k     |True           |"1" 1 bit     |
|01. epd1in02      |True           |"1" 1 bit     |
|02. epd1in54      |True           |"1" 1 bit     |
|03. epd1in54_V2   |True           |"1" 1 bit     |
|04. epd1in54b     |True           |"1" 1 bit     |
|05. epd1in54b_V2  |True           |"1" 1 bit     |
|06. epd1in54c     |True           |"1" 1 bit     |
|07. epd1in64g     |True           |"1" 1 bit     |
|08. epd2in13      |True           |"1" 1 bit     |
|09. epd2in13_V2   |True           |"1" 1 bit     |
|10. epd2in13_V3   |True           |"1" 1 bit     |
|11. epd2in13_V4   |True           |"1" 1 bit     |
|12. epd2in13b_V3  |True           |"1" 1 bit     |
|13. epd2in13b_V4  |True           |"1" 1 bit     |
|14. epd2in13bc    |True           |"1" 1 bit     |
|15. epd2in13d     |False          |Unsupported   |
|16. epd2in13g     |True           |"1" 1 bit     |
|17. epd2in36g     |True           |"1" 1 bit     |
|18. epd2in66      |True           |"1" 1 bit     |
|19. epd2in66b     |True           |"1" 1 bit     |
|20. epd2in66g     |True           |"1" 1 bit     |
|21. epd2in7       |True           |"1" 1 bit     |
|22. epd2in7_V2    |True           |"1" 1 bit     |
|23. epd2in7b      |True           |"1" 1 bit     |
|24. epd2in7b_V2   |True           |"1" 1 bit     |
|25. epd2in9       |True           |"1" 1 bit     |
|26. epd2in9_V2    |True           |"1" 1 bit     |
|27. epd2in9b_V3   |True           |"1" 1 bit     |
|28. epd2in9b_V4   |True           |"1" 1 bit     |
|29. epd2in9bc     |True           |"1" 1 bit     |
|30. epd2in9d      |False          |Unsupported   |
|31. epd3in0g      |True           |"1" 1 bit     |
|32. epd3in52      |True           |"1" 1 bit     |
|33. epd3in7       |False          |Unsupported   |
|34. epd4in01f     |True           |"RGB" 7 Color |
|35. epd4in2       |False          |Unsupported   |
|36. epd4in26      |True           |"1" 1 bit     |
|37. epd4in2_V2    |False          |Unsupported   |
|38. epd4in2b_V2   |True           |"1" 1 bit     |
|39. epd4in2bc     |True           |"1" 1 bit     |
|40. epd4in37g     |True           |"1" 1 bit     |
|41. epd5in65f     |True           |"RGB" 7 Color |
|42. epd5in83      |True           |"1" 1 bit     |
|43. epd5in83_V2   |True           |"1" 1 bit     |
|44. epd5in83b_V2  |True           |"1" 1 bit     |
|45. epd5in83bc    |True           |"1" 1 bit     |
|46. epd7in3f      |True           |"RGB" 7 Color |
|47. epd7in3g      |True           |"1" 1 bit     |
|48. epd7in5       |True           |"1" 1 bit     |
|49. epd7in5_HD    |True           |"1" 1 bit     |
|50. epd7in5_V2    |True           |"1" 1 bit     |
|51. epd7in5_V2_old|True           |"1" 1 bit     |
|52. epd7in5b_HD   |True           |"1" 1 bit     |
|53. epd7in5b_V2   |True           |"1" 1 bit     |
|54. epd7in5bc     |True           |"1" 1 bit     |
|55. All HD IT8951 |True           |"L" 8 bit     |

<a name="knownIssues"> </a>
## Issues

**Hardware Issues**
See the [troubleshooting guide](./documentation/Troubleshooting.md)

**Software Bugs**
Please [open tickets at GitHub](https://github.com/ysadamt/PaperPi/issues).

## Helping Out
If you're interested in helping out, check out the [issues](https://github.com/ysadamt/PaperPi/issues) and jump in. Collaborators are always welcome

## Thanks

* @blbal - typos
* @aaronr8684 - writing installer, catching hundreds of errors and generally be a great person
* @veebch - inspiration for Reddit and Crypto plugins
* @PaperCloud10 - testing of new versions and debugging slideshow plugin
* @VaporwareII, @harperreed  - diagnosing remote installation failures
