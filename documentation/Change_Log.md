# Change Log

## 0.5.5.0

* Deprecated `Crypto` plugin. 
* Improved install experience for Bookworm (64 Bit)

## 0.5.4.1

### Update installer scripts

Check the OS version and refuse to install on non-32 bit systems. This can be overridden with `install.sh -s`, but requires several manual steps. 


## 0.5.4.0

### Plugin Timeout feature implemented

Plugins will time out and not be displayed if they fail to return within a set time. Timeout is managed through config variable `plugin_timeout` in `[main]` section and defaults to 30 seconds. Valid values are integers > 0. A minimum of 30 (default if left unset in config) seconds is recommended for most plugins.

It is advised to update your config files to include this option.

This change prevents plugins from hanging indefinitely in some situations such as extremely slow network performance. This adds an extra layer of protection when plugins fail to handle such issues appropriately.

This may need to be adjusted to 60+ seconds when debugging as some plugins (e.g. Met Weather) produce *huge* amounts of debug output that can take many tens of seconds to complete on top of the normal plugin execution time.

```
[main]
...
# plugin timeout - amount of time in seconds to wait for a hung plugin to complete execution
plugin_timeout = 30
```

### Do not wipe screen on shutdown

Leave the last image on the screen when shutting down instead of setting to blank. Note: [according to WaveShare](https://www.waveshare.com/wiki/2.13inch_Touch_e-Paper_HAT_Manual), leaving a static image for more than 24 hours can damage the screen.

This option is controlled through config variable `no_wipe` in the `[main]` section.

```
[main]
...
# do not wipe screen when shutting down. True: leave image; False: wipe screen (default)
no_wipe = False
```

### Config file version updated

`CONFIG_VERSION` file is now at V1.2 and includes the new variable `plugin_timeout`.

Adding options:
* `no_wipe` - Boolean: Do not wipe screen during shutdown 
  - Default: `False`
* `plugin_timeout` - Integer: time in seconds before terminating a plugin update
  - Default: `30`

### Various Installer Issues Resolved

Changes to pipenv resulted in installers failing for a variety of reasons. Changes have been made to make the installers more robust and resolve the pipenv issues.

## 0.5.3.0

* System_Info Plugin:
  * Add plugin
* Utilities
  * ignore local library imports that are not needed

## 0.5.2.0

* Moon_phase:
 * update to met.no API Sunrise V3
 * improve error logging and user notifications
  
## 0.5.0.1

* Add RGB Support for RGB WaveShare Screens
  * Must be enabled in `paperpi.ini`
* Update Plugins for RGB Support
  * LMS Client, LibreSpot, met_no, reddit_quote, slideshow, word_clock
* LMS Client now supports now-playing information for radio stations via QueryLMS v0.2


## 0.4.1.0

* Add mirror option
* Move to version 0.5.2.1 of epdlib

## 0.4.0.0

* Add [Slideshow](../paperpi/plugins/slideshow/README.md) plugin
* Update documentation

## 0.3.1.0

* Add mirror display support
* increase stability of Reddit, New Yorker and Moon Phases plugin when network connectivity is limited

## 0.3.0.0

* Remove dependency on PyInstaller -- PaperPi is no longer distributed as a frozen PyInstaller
* Update installer and offer web-based install

## 0.2.14.5

* add crypto currency plugin
* add xkcd comic plugin
* adjust build and packaging scripts to handle external datas better

## 0.2.14.3

* update model paperpi.ini with latest configurations
* automatically update model paperpi.ini on build/release

## 0.2.14.2

* Add option to add plugin configuration to user or daemon configuration files:
  * `paperip --add_config plugin_name user|daemon`

## 0.2.14.1

* Add reddit_quote plugin

## 0.2.14.0

* Add moon_phase plugin

## 0.2.13.0

* Fix [issue #20](https://github.com/ysadamt/epd_display/issues/20) -- max_refresh from config file ignored
* Update systemd unit file to improve handling of systemd signals  [issue #19](https://github.com/ysadamt/epd_display/issues/19)
* Update interrupt handler to improve handling of systemd signals [issue #19](https://github.com/ysadamt/epd_display/issues/19)
