# PaperPi V3
[![Spellcheck](https://github.com/txoof/PaperPi/actions/workflows/spellcheck.yml/badge.svg)](https://github.com/txoof/PaperPi/actions/workflows/spellcheck.yml)

## NOTE

**This version of PaperPi is under heavy development and is not ready for the average user.** We are working on adding more screen compatibility, possibly adding color screen support for inkyPHAT and WaveShare 3 color screens. There are also plans to make plugins easier to install and update.

See our [Milestones here](https://github.com/txoof/PaperPi/milestones). PRs, but reports, contributions, and testers are welcome.

**The stable version of [PaperPi can be found here](https://github.com/txoof/epd_display).**


|     |     |
|:---:|:---:|
|<img src=./paperpi/plugins/splash_screen/splash_screen.layout-sample.png alt="Splash Screen" width=400/> Splash Screen| <img src=./documentation/images/PaperPi_Demo_frame.gif alt="PaperPi" width=400 /> PaperPi Weather Plugin|


PaperPi is an e-Paper display with multiple rotating display plugins that contain dynamic content.

PaperPi is a quiet and clean portal to the internet. No loud colors, no busy animations, just a lovely selection of the information you want without buzz and distraction. PaperPi rotates through your choice of plugin screens at the pace you choose.

PaperPi is written to work with almost all of the [WaveShare](https://www.waveshare.com/product/displays/e-paper.htm) SPI displays out of the box. PaperPi will work with the tiny 2" displays all the way up to the 10" HD displays with minimal configuration. Check the complete list of [supported screens](#supportedScreens) below.

For information on building a frame, case and custom cable, see [these instructions](./documentation/Frame_Cable_Case.md).

To get started, jump to the **[Setup Instructions](#setup_install)**

## Plugins

PaperPi supports many different plugins and layouts for each plugin.

### [Complete Plugins List](./documentation/Plugins.md)

| | | |
|:-------------------------:|:-------------------------:|:-------------------------:|
|<img src=./paperpi/plugins/librespot_client/librespot_client.layout-sample.png alt="librespot plugin" width=300 />[LibreSpot (spotify) Plugin](./paperpi/plugins/librespot_client/README.md)|<img src=./paperpi/plugins/word_clock/word_clock.layout-sample.png alt="word clock plugin" width=300 />[Word Clock](./paperpi/plugins/word_clock/README.md)|<img src=./paperpi/plugins/lms_client/lms_client.layout-sample.png alt="lms client plugin" width=300 />[Logitech Media Server Plugin](./paperpi/plugins/lms_client/README.md)|
|<img src=./paperpi/plugins/moon_phase/moon_phase.layout-sample.png alt="decimal binary clock" width=300 />[Moon Phase](./paperpi/plugins/moon_phase/README.md)|<img src=./paperpi/plugins/met_no/met_no.layout-sample.png alt="met_no plugin" width=300 />[Met.no Weather](./paperpi/plugins/met_no/README.md)|<img src=./paperpi/plugins/crypto/crypto.layout-sample.png alt="Crypto Currency Ticker" width=300 />[Crypto Currency](./paperpi/plugins/crypto/README.md)|
|<img src=./paperpi/plugins/reddit_quote/reddit_quote.layout-sample.png alt="reddit/r/quotes" width=300 />[Reddit Quotes](./paperpi/plugins/reddit_quote/README.md)|<img src=./paperpi/plugins/xkcd_comic/xkcd_comic.layout-sample.png alt="XKCD Comic" width=300 />[XKCD Comic](./paperpi/plugins/xkcd_comic/README.md)|<img src=./paperpi/plugins/basic_clock/basic_clock.layout-sample.png alt="Basic Clock" width=300 />[Basic Clock](./paperpi/plugins/basic_clock/README.md)| |

See the [Developing Plugins](./documentation/developing_plugins.md) guide for more information on creating your own plugins.
## Changes

See the [Change Log](./documentation/Change_Log.md) for a complete list of updates

**V 0.3.0**

* PaperPi is no longer distributed as a PyInstaller frozen blob and now installs into `/usr/local/paperpi` and places an executable entry script in `/usr/local/bin/`.
* Plugins can now be edited easily in `/usr/local/paperpi/plugins/`
* Additional plugins can be placed in `/usr/local/paperpi/plugins` without rebuilding

<a name="requirements"></a>

## PaperPi Requirements

### Required Hardware

* Raspberry Pi (Pi 4, Pi 3, and Pi Zero)
* Raspberry Pi OS Buster or later (64-bit supported)
* [WaveShare EPD SPI-only Screen](https://www.waveshare.com/product/displays/e-paper.htm) with PiHat
  * see the full list of currently [supported screens](#supportedScreens)
  * UART, SPI/USB/I80 screens are **not supported** as there is no python library for diving these boards

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

### Install

To get started, copy and paste the following command into a terminal window to download the latest stable version of PaperPi and automatically start the install and setup process.

`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/txoof/PaperPi/main/install/remote_install.sh)"`

If you would rather install PaperPi yourself, [clone this repo](https://github.com/txoof/PaperPi.git) and run `./install/install.sh`

### Setup

**Daemon Mode**

The installer should prompt you to edit `/etc/defaults/paperpi.ini`. At minimum you must add your EPD Screen and enable several plugins. A complete list of supported EPD Screens are [listed below](#supportedScreens).

Any changes to the PaperPi configuration require a restart of the service:

`sudo systemctl restart paperpi-daemon.service`

To disable the service from starting on boot, run the command:

`sudo systemctl disable paperpi-daemon.service`

**On Demand**

If you would rather run PaperPi on-demand rather than a daemon service you can run it as regular user (e.g. pi) by running `/usr/local/bin/paperpi`. A new configuration file will be created in your user's directory. Make sure to edit this file and add, at minimum, your EPD Screen.

PaperPi can be run on demand in daemon mode using `paperpi -d`

### Uninstall

To uninstall PaperPi, run `./install/install.sh` with either `-u` to uninstall or `-p` to uninstall and remove all configuration files.

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

If you would like to develop [plugins](./documentation/Plugins.md) for PaperPi, you will likely need a working build environment.

### Requirements

* python 3.7+
* pipenv

**Create a Build Environment**

1. Clone the repo: `https://github.com/txoof/PaperPi`
2. Run `$ ./utilities/create_devel_environment.sh` to create a build environment
    * This will check for all necessary libraries and python modules and create a local venv for development

## Contributing

Plugins can be pure python, but should follow the [guide provided](./documentation/Plugins.md).

<a name="supportedScreens"> </a>

## Supported Screens

Most NON-IT8951 screens are only supported in 1 bit (black and white) mode. Color output is not supported at this time. Some waveshare drivers do not provide 'standard' `display` and `Clear` methods; these displays are not supported at this time.

All IT8951 Screens now support 8 bit grayscale output.

Some WaveShare screens that support color output will also work with with the non-colored driver. Using the 1 bit driver can yield significantly better update speeds. For example: the `epd2in7b` screen takes around 15 seconds to update even when refreshing a 1 bit image, but can be run using the `epd2in7` module in 1-bit mode which takes less than 2 seconds to update.

**WaveShare Screen**

NN. Board        Supported:
--  -----        ----------

01. epd1in02     False
    * Issues:
        * AttributeError: module does not support `EPD.display()`
01. epd1in54     True
02. epd1in54_V2  True
03. epd1in54b    True
04. epd1in54b_V2 True
05. epd1in54c    True
06. epd2in13     True
07. epd2in13_V2  True
08. epd2in13_V3  True
09. epd2in13b_V3 True
10. epd2in13bc   True
11. epd2in13d    True
12. epd2in66     True
13. epd2in66b    True
14. epd2in7      True
15. epd2in7b     True
16. epd2in7b_V2  True
17. epd2in9      True
18. epd2in9_V2   True
19. epd2in9b_V3  True
20. epd2in9bc    True
21. epd2in9d     True
22. epd3in7      False
     * Issues:
         * Non-standard, unsupported `EPD.Clear()` function
         * AttributeError: module does not support `EPD.display()`
23. epd4in01f    True
24. epd4in2      True
25. epd4in2b_V2  True
26. epd4in2bc    True
27. epd5in65f    True
28. epd5in83     True
29. epd5in83_V2  True
30. epd5in83b_V2 True
31. epd5in83bc   True
32. epd7in5      True
33. epd7in5_HD   True
34. epd7in5_V2   True
35. epd7in5b_HD  True
36. epd7in5b_V2  True
37. epd7in5bc    True
39. HD IT8951 Based Screens True

<a name="knownIssues"> </a>
## Issues

**Hardware Issues**
See the [troubleshooting guide](./documentation/Troubleshooting.md)

**Software Bugs**
Please [open tickets at GitHub](https://github.com/txoof/epd_display/issues).

Document updated 2022.02.17
=======
# PaperPi (Development)
**This is a development version of PaperPi that's not fit for prime-time yet.**

The official version can be found [here](https://github.com/txoof/epd_display).

## Helping Out
If you're interested in helping out, check out the [issues](https://github.com/txoof/PaperPi/issues) and jump in. Collaborators are always welcome
