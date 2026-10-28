# PaperPi

PaperPi shows information on an e-paper screen attached to a Raspberry Pi: clocks, the weather, your calendar, what music is playing, comics, public transport departures and more. Each source of information is a **plugin**. The plugins take turns on the screen, and you set them up in a web page on your phone or computer.

![The Home page of PaperPi's web interface](images/web/home-light.png)

## What you need

- A Raspberry Pi 3 or 4 with Raspberry Pi OS "trixie".
- An e-paper screen: a screen with Waveshare's IT8951 board (such as the Waveshare 9.7"), or one of Waveshare's small screens on their e-Paper HAT (see [Waveshare screens](waveshare-screens.md)).

## Install

One command on the Pi installs PaperPi and starts it. It asks which screen is connected:

```bash
curl -fsSL https://raw.githubusercontent.com/txoof/PaperPi/main/install/paperpi-install | sudo bash
```

Then open the web interface at the address the screen shows. What the command does, and how to update and remove PaperPi: [Install on a Raspberry Pi](install-systemd.md).

## Version 1

This manual is for PaperPi version 2, a rewrite from scratch. **Version 1 is no longer maintained:** it gets no fixes, and version 2 does not read its config files. Its code stays on the [`v1` branch](https://github.com/txoof/PaperPi/tree/v1), with the last state marked by the tag [`v1-final`](https://github.com/txoof/PaperPi/tree/v1-final).

## Help and source code

PaperPi is free software (GPL 3.0 or later). The code, and the place to report problems, is [txoof/PaperPi on GitHub](https://github.com/txoof/PaperPi). The screens are driven by [epdlib](https://github.com/txoof/epdlib), a separate library on [PyPI](https://pypi.org/project/epdlib/).
