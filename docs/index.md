# PaperPi

PaperPi is a lovely, quiet, slow internet e-Paper radio. No loud colors, no busy animations, just a lovely selection of the information you want without buzz and distraction. PaperPi rotates through your choice of plugin screens at the pace you choose.

![The Home page of PaperPi's web interface](images/web/home-light.png)

## Plugins

PaperPi supports a growing library of [plugins](plugins/index.md) that are configurable and customizable.

<div class="grid cards" markdown>

- [![Word clock](plugins/files/tests/images/word_clock-words_time-9in7.png)](plugins/word_clock.md)
  [Word clock](plugins/word_clock.md)

- [![Weather](plugins/files/tests/images/met_no-hours_12-9in7.png)](plugins/met_no.md)
  [Weather](plugins/met_no.md)

- [![Moon phase](plugins/files/tests/images/moon_phase-moon_data-9in7.png)](plugins/moon_phase.md)
  [Moon phase](plugins/moon_phase.md)

- [![xkcd](plugins/files/tests/images/xkcd_comic-comic_title_alttext-9in7.png)](plugins/xkcd_comic.md)
  [xkcd](plugins/xkcd_comic.md)

</div>

See [all plugins](plugins/index.md).

## Install

PaperPi runs great on a Raspberry Pi 3 or better!

**Minimum requirements:**

- Pi 3 or better with Raspberry Pi OS Trixie
- E-Paper screen - nearly all of Waveshare's screens work and many have been tested

Optional:

- Internet connectivity for some plugins

### Quick Start

One command on the Pi installs PaperPi and starts it with prompts to guide you through the install.

```bash
curl -fsSL https://raw.githubusercontent.com/txoof/PaperPi/main/install/paperpi-install | sudo bash
```

Then open the web interface at the address the screen shows: [First Setup](first-setup.md).

## What's in this manual

**Getting started**

- [Hardware](hardware.md): Parts, pins and connections
- [Install](install.md): Step by step build instructions
- [First Setup](first-setup.md): Setting a password and configuring plugins
- [Web Interface](web-interface.md): Getting around the interface
- [Update and Uninstall](update.md): Updating, rolling back and uninstalling PaperPi
- [Understanding Plugin Schedules](take-turns.md): Display time, refresh, and the levels rotation, interrupt and alert
- [Troubleshooting](troubleshooting.md): Basic troubleshooting steps
- [What's New](changelog.md): Changelog!

**Plugins**

- [Plugins](plugins/index.md): Gallery of the plugins and their settings

**Reference**

- [Settings reference](settings.md): Config file reference
- [Supported screens](screens.md): Complete list of Waveshare Screens and known issues
- [How the service works](install-systemd.md): where the files are, the commands to check on PaperPi, and how systemd keeps it running

**For developers**

- [Running from source](development.md): working on PaperPi's code, or trying it without installing it.
- [Writing a plugin](writing-plugins.md), step by step from `paperpi new-plugin`, and the [Plugin reference](plugin-reference.md) with the exact rules.
- [Making a release](releasing.md).

## Version 1

This manual is for PaperPi version 2, a rewrite from scratch. **Version 1 is no longer maintained:** and is no longer supported. Version 2 does not read V1 config files. V1 code remains on the [`v1` branch](https://github.com/txoof/PaperPi/tree/v1), with the last state marked by the tag [`v1-final`](https://github.com/txoof/PaperPi/tree/v1-final).

## Help and source code

PaperPi is free software (GPL 3.0 or later). The code, and the place to report problems, is [txoof/PaperPi on GitHub](https://github.com/txoof/PaperPi). The screens are driven by [epdlib](https://github.com/txoof/epdlib), a separate library on [PyPI](https://pypi.org/project/epdlib/).
