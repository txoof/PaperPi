# How the service works

PaperPi runs as a systemd service: systemd is the part of Linux that starts and watches programs like this one (a "service"). It starts PaperPi at every start of the Pi and starts it again after a crash. This page is about how that is put together. To install PaperPi: [Install](install.md); to update or remove it: [Update and remove](update.md).

## What the install script does

`install/paperpi-install` prints each step before it does it:

1. Unless a config is already in `/etc/paperpi`, it asks which screen is connected (or takes `--display`, `--model`, `--vcom`). `0`, or `--yes` without `--display`, means the virtual screen, which only saves pictures in `/var/lib/paperpi/screen/`.
2. It installs what is missing from Debian, after asking: `git`, `python3-venv`, and `gcc` and `python3-dev` (they build `spidev`, the SPI library).
3. For a real screen, it turns on SPI with `raspi-config nonint do_spi 0` (the same as raspi-config's menu Interface Options, SPI). When SPI only works after a restart, it asks before restarting the Pi.
4. It makes the `paperpi` user, copies the newest release into `/opt/paperpi/code` (or the branch, tag or commit of `--ref`: `curl ... | sudo bash -s -- --ref main`), installs the Python packages of `uv.lock`, writes the first config (`paperpi example-config --setup`: a clock and the set-up screen), and starts the service.

`update` does steps 2 and 4 again, without the questions and with the config as it is. PaperPi itself is always installed again, also when its version number hasn't changed between commits. How releases are made: [Making a release](releasing.md).

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
| `/usr/local/sbin/paperpi-install` | the install script (`install/paperpi-install`), for `update` and `uninstall` | root |

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
