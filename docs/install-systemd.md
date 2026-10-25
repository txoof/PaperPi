# Install PaperPi as a systemd service

This installs PaperPi on a Raspberry Pi with Raspberry Pi OS "trixie", so it starts at every start of the Pi and is started again after a crash. systemd is the part of Linux that starts and watches programs like this one (a "service"). This is PaperPi's install; a Docker install was planned for milestone M6 but dropped (2026-10-25, #325).

## Install

One command on the Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/txoof/PaperPi/main/install/paperpi-install | sudo bash
```

It prints each step before it does it:

1. It asks which screen is connected: a numbered list of the sizes of Waveshare's IT8951 board, and for those the `vcom`, the number printed on the screen's ribbon cable (each screen has its own). `0` means none yet: PaperPi then uses the virtual screen, which only saves pictures in `/var/lib/paperpi/screen/`, and you choose the screen in the web interface later.
2. It installs what the install needs from Debian, after asking: `git`, `python3-venv`, and `gcc` and `python3-dev` (they build `spidev`, the SPI library).
3. For a real screen, it turns on SPI, the data line to the screen (`raspi-config nonint do_spi 0`, the same as raspi-config's menu Interface Options, SPI). When SPI only works after a restart, it asks before restarting the Pi; PaperPi then starts by itself after the restart.
4. It installs the newest PaperPi release and starts it (see "Where the files are" below). To install the newest code instead, end the command with `sudo bash -s -- --ref main`.

At the end the screen shows a clock and the set-up screen in turn. The set-up screen has the address of the web interface and a QR code for it: open it, set a password and choose which plugins to display. Until a password is set, anyone on your home network can set it.

To install without questions (for example from another script), download the script and give the answers as options; `--yes` asks nothing and uses the virtual screen unless `--display` is given:

```bash
curl -fsSLO https://raw.githubusercontent.com/txoof/PaperPi/main/install/paperpi-install
sudo bash paperpi-install install --yes --display it8951 --model 9.7 --vcom -1.90
```

`sudo bash paperpi-install --help` lists every option. With a config already in `/etc/paperpi` (from an earlier install), it is kept and nothing is asked about the screen.

## Update

```bash
sudo paperpi-install update
```

It gets the newest release from GitHub, installs what is missing from Debian and PaperPi's Python packages, and restarts PaperPi. Nothing updates by itself. `--ref <branch, tag or commit>` installs that one instead: `--ref main` for the newest code, a version tag such as `v2.0.0a1` to go back to an older release, or a branch to try it. The next `update` without `--ref` goes back to the newest release. How releases are made: [releasing.md](releasing.md). The config and the saved files stay as they are. PaperPi itself is always installed again, also when its version number hasn't changed between commits.

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
| apply a change to the config file made by hand | `sudo paperpi reload` (prints what changed, or the mistake that stops it; `--check` only checks) |
| restart / stop / start | `sudo systemctl restart paperpi` (or `stop`, `start`) |
| forget the web password | `sudo paperpi reset-password`, then `sudo paperpi reload` |
| web interface unreachable after a new port or address | `sudo paperpi web-defaults`, then `sudo systemctl restart paperpi` |
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
