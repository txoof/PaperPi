# Install PaperPi as a systemd service

This installs PaperPi on a Raspberry Pi with Raspberry Pi OS "trixie", so it starts at every start of the Pi and is started again after a crash. systemd is the part of Linux that starts and watches programs like this one (a "service"). This comes before the Docker install of milestone M6; the Docker install will use the same config and state folders, so settings carry over.

## Install

1. Turn on SPI, the data line to the screen: `sudo raspi-config nonint do_spi 0` (the same as raspi-config's menu Interface Options, SPI), then restart the Pi.
2. Install what the install needs: `sudo apt install git python3-venv gcc python3-dev` (the compiler and header files build `spidev`, the SPI library).
3. Get the install script and run it. For the 9.7" IT8951 screen (`vcom` is printed on the screen's ribbon cable; each screen has its own):
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/txoof/PaperPi/main/install/paperpi-install
   sudo bash paperpi-install install --display it8951 --model 9.7 --vcom -1.90
   ```
   Without `--display`, the first config uses the virtual screen, which only saves pictures in `/var/lib/paperpi/screen/`; set the screen in the web interface later.

The script prints each step before it does it. At the end the screen shows a clock and the set-up screen in turn. The set-up screen has the address of the web interface and a QR code for it: open it, set a password and choose which plugins to display. Until a password is set, anyone on your home network can set it.

## Update

```bash
sudo paperpi-install update
```

It gets the newest `main` from GitHub, installs its Python packages and restarts PaperPi. Nothing updates by itself. `--ref <branch, tag or commit>` installs that one instead, for example to go back to an older commit or to try a branch. The config and the saved files stay as they are.

## Remove

```bash
sudo paperpi-install uninstall           # keeps /etc/paperpi and /var/lib/paperpi
sudo paperpi-install uninstall --purge   # also removes them and the paperpi user
```

Stopping clears the screen first, which can take up to 30 seconds.

## Use

| To | Run |
|---|---|
| see whether it runs | `systemctl status paperpi` |
| follow the log | `journalctl -u paperpi -f` |
| apply a change to the config file made by hand | `sudo systemctl reload paperpi` |
| restart / stop / start | `sudo systemctl restart paperpi` (or `stop`, `start`) |
| forget the web password | `sudo paperpi reset-password`, then `sudo systemctl reload paperpi` |
| check the health report | `paperpi health` |

When PaperPi crashes 5 times within 10 minutes, systemd stops trying (`systemctl status paperpi` says so). Fix the cause (see the log), then `sudo systemctl reset-failed paperpi` and `sudo systemctl start paperpi`.

## Where the files are

| Path | What | Owner |
|---|---|---|
| `/opt/paperpi/code` | PaperPi's code, a copy of the GitHub repository | root |
| `/opt/paperpi/venv` | Python and its packages for PaperPi (the system's Python 3.13, the package versions of `uv.lock`) | root |
| `/opt/paperpi/tools` | `uv`, which installs the packages | root |
| `/etc/paperpi/paperpi.toml` | the config file; the web interface changes it | paperpi |
| `/var/lib/paperpi` | plugin files, the last good config, the log, `screen-stuck` | paperpi |
| `/run/paperpi/health` | the health report, in memory | paperpi |
| `/etc/systemd/system/paperpi.service` | the service file (from `install/paperpi.service`) | root |
| `/usr/local/bin/paperpi` | the `paperpi` command | root |
| `/usr/local/sbin/paperpi-install` | this install script | root |

The code belongs to root, so PaperPi itself (and a plugin) can't change it. PaperPi runs as the user `paperpi`, which can't log in, has no password and is only in the `spi` and `gpio` groups. A plugin that goes wrong can't read your own files or use `sudo`.

## The service file

`install/paperpi.service`; the reasons are in [decisions/errors-and-time-limits.md](decisions/errors-and-time-limits.md).

- `Type=notify`, `WatchdogSec=120`: systemd counts PaperPi as started only after it says `READY=1`, and restarts it when no "still running" message (`WATCHDOG=1`) arrives for 2 minutes. Only the main process may send them (`NotifyAccess=main`, the default), so a plugin process can't hide a stuck loop.
- `TimeoutStopSec=45`: longer than the screen clear at exit (30 s) and its check (2 s).
- `KillMode` stays at its default, `control-group`: stopping the service ends **every** PaperPi process (plugin processes, the process that starts them, Python's resource tracker), also when the main process was killed with `kill -9` ([#209](https://github.com/txoof/PaperPi/issues/209)). Never set it to `process` or `none`.
- `Restart=on-failure`, `RestartSec=10`, at most 5 starts in 10 minutes. `SuccessExitStatus=75` and `RestartForceExitStatus=75`: "Restart PaperPi" in the web interface ends PaperPi with exit status 75, which counts as a clean stop and starts it again (the `paperpi` user can't run `systemctl`).
- `RuntimeDirectory` and `StateDirectory`: systemd makes `/run/paperpi` and `/var/lib/paperpi` for the `paperpi` user.
- Protection settings: PaperPi can write only `/etc/paperpi`, `/var/lib/paperpi`, `/run/paperpi` and its own `/tmp`, can't see `/home`, and can use no devices but SPI and GPIO.

## Check it on the Pi

`sudo install/check-service` (in a copy of the repository, with the service running) kills the main process with `kill -9`, checks that systemd starts PaperPi again and that no old process is left, then checks that `systemctl stop` ends within the time limit. It starts the service again at the end.
