# Update and remove

## Update

PaperPi does not update by itself. To get the newest release, run on the Pi:

```bash
sudo paperpi-install update
```

It downloads the newest release from GitHub, installs what is missing, and restarts PaperPi. Your settings and the plugins' saved files stay as they are. The screen is blank for a short while during the restart.

What changed in each release: [releases on GitHub](https://github.com/txoof/PaperPi/releases).

!!! note "Run it twice after a change to the install script"
    `update` runs the copy of the install script that is on the Pi, and installs the new copy for next time. So when a release changes the install script itself, the first `update` still works the old way; run `sudo paperpi-install update` a second time to finish. Running it twice does no harm when it isn't needed.

## Install another version

`--ref` installs a version other than the newest release:

| Command | Installs |
|---|---|
| `sudo paperpi-install update --ref v2.0.0` | that release, for example to go back to it after a problem with a newer one |
| `sudo paperpi-install update --ref main` | the newest code, not yet released: newer, but less tested |
| `sudo paperpi-install update` | the newest release again, also when that is older than what is installed (it says so) |

A branch name works too, to try out a change before it is released.

## Remove

```bash
sudo paperpi-install uninstall           # keeps the settings and saved files
sudo paperpi-install uninstall --purge   # removes everything
```

The first keeps the config in `/etc/paperpi` and the saved files in `/var/lib/paperpi`, so a new install later starts with your settings. `--purge` also removes those, and the `paperpi` user that PaperPi runs as. Stopping PaperPi clears the screen first, which can take up to 45 seconds.

## Without a terminal to ask in

With `--yes`, or when run by another program, `update` installs the missing programs from Raspberry Pi OS without asking.

How the install is put together, and the commands to check on PaperPi: [How the service works](install-systemd.md).
