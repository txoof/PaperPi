# Change Log

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

* Fix [issue #20](https://github.com/txoof/epd_display/issues/20) -- max_refresh from config file ignored
* Update systemd unit file to improve handling of systemd signals  [issue #19](https://github.com/txoof/epd_display/issues/19)
* Update interrupt handler to improve handling of systemd signals [issue #19](https://github.com/txoof/epd_display/issues/19)
