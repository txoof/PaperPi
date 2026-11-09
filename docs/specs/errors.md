# Errors, time limits and freezes

PaperPi must keep running for months without anyone looking after it. PaperPi v1 stopped updating the screen after 3 to 6 months without crashing, so nothing restarted it. v2 follows a few strict rules to prevent that: every wait has a time limit, plugins and screen writes run in separate processes, logs and saved files have size limits, and a watchdog restarts PaperPi when it stops reporting that it is still running.

What to do when something goes wrong is on [Troubleshooting](../troubleshooting.md). This page describes the rules inside PaperPi.

## The rules

1. **Every wait has a time limit:** for the screen, the network, a plugin and a file.
2. **All durations use the monotonic clock,** a clock that only counts forward and does not jump when the time of day is corrected.
3. **The screen's data line and pins are opened once and always closed,** also after an error.
4. **An error is handled, with a limit on retries, or it ends PaperPi.** No loop logs the same error forever.
5. **Plugins run in their own process** with a time limit they can't get around ([Plugins](plugins.md)).
6. **Logs and saved files have size limits.**
7. **A watchdog restarts PaperPi** when it stops reporting "still running".
8. **PaperPi records** the time since the last screen write, its memory use, its open files and the free disk space.

## The watchdog

- **The scheduler's loop reports "still running" every 30 seconds.** Only the loop reports, so if the loop gets stuck, the reports stop.
- **If no report arrives for 2 minutes,** systemd restarts PaperPi.
- **"Still running" does not need a recent screen write.** A broken or unplugged screen would otherwise make PaperPi restart over and over, and the web interface, which shows the error, would keep disappearing. A screen that keeps failing has its own rules ([A screen that keeps failing](screens.md#a-screen-that-keeps-failing)).

Each report also replaces the file `/run/paperpi/health` (in memory, emptied at every start of the Pi) with one line: the time, the time since the last screen write, the screen's state (`ok`, `failing` or `paused`), memory use, open files and free disk. `paperpi health` fails when the report is missing or older than 2 minutes. The same values go to the log once an hour, so slow growth can be seen over weeks.

Note: the systemd service needs `Type=notify`, `WatchdogSec=120` and `RuntimeDirectory=paperpi` for this; the installer sets them up ([How the service works](../install-systemd.md)).

## When things fail

| What fails                                    | What PaperPi does                                                                          |
| --------------------------------------------- | ------------------------------------------------------------------------------------------ |
| a plugin update                               | skips it and tries again at the next refresh; after 3 failures in a row, leaves the plugin out for 30 minutes ([Which plugin is shown](scheduling.md#failures)) |
| a web request of a plugin                     | tries once more after 5 seconds; then the plugin's update fails                            |
| a screen write                                | tries again, resets the screen, then pauses writes ([A screen that keeps failing](screens.md#a-screen-that-keeps-failing)) |
| a screen helper process that can't be stopped | exits, so systemd restarts PaperPi; at most once an hour                                   |
| the config file                               | runs on the last good copy ([The config file](config.md#checking-the-file))                |
| an error nobody catches                       | logs it with its details, then exits; systemd restarts PaperPi                             |

## Time limits

| What                         | Time limit                                                                                     |
| ---------------------------- | ---------------------------------------------------------------------------------------------- |
| one plugin update            | 60 seconds (at most 600), set per plugin with `time_limit`                                     |
| one web request of a plugin  | 10 seconds to connect, 30 seconds in all, including one retry after 5 seconds                  |
| one screen write             | 3 times the last redraw, at least 30 seconds, at most 5 minutes; before the first one: 2 minutes (color screens: 5) |
| reading the config file on a reload | 10 seconds; a file that takes longer is not applied                                     |

Note: only `time_limit` is a setting. The other limits are set in one place in the code, `src/paperpi/limits.py`.

A web answer may be at most 5 MB after unpacking; a plugin that downloads pictures can ask for more. All plugins use one helper for web requests, `paperpi.webrequest`, so the same limits apply to all of them.

## Logs

- **The system log** (`journalctl -u paperpi`) gets warnings and errors, the start and stop lines and the hourly health line; everything with `--verbose`. Raspberry Pi OS keeps the system log in memory only, so it is gone after a restart of the Pi.
- **PaperPi's own log file**, `paperpi.log` in `/var/lib/paperpi`, keeps the warnings, errors, starts, stops, crashes and the health line, so they survive a restart of the Pi. At 1 MB it becomes `paperpi.log.1` and a new file starts, so both together stay under about 2 MB.
- **The web interface** shows the last 5,000 lines (INFO and up) on its Full log page, and what needs attention on its Warnings page.
- **Plugins' log lines** are sent to PaperPi with their result, at most 100 per update, with secret settings replaced by `****`.
- **An error that repeats** is logged once; after that, a summary line every 10 minutes, e.g. "same error repeated 40 times".

## Saved files

Each plugin has its own storage folder in `/var/lib/paperpi/plugins/`.

| Limit          | Default  | What happens                                                                   |
| -------------- | -------- | ------------------------------------------------------------------------------ |
| `storage_mb`   | 500 MB   | over it, the files changed longest ago are removed until the folder fits       |
| `storage_days` | 30 days  | files not changed for this long are removed; `0` keeps them                    |

- A plugin may suggest its own values (a photo album may need much more); the setting in the config file always wins. `paperpi list` shows the values used.
- PaperPi cleans the folders at start and after a plugin's update (at most once every 5 minutes per plugin).
- **Nothing outside the plugin's folder is ever removed.** Links are not followed, and a drive mounted inside the folder is skipped.
- Folders that no `[[plugin]]` block uses any more (for example after an `id` was changed) are not cleaned, because they may hold photos. They are named in the log at start, to be removed by hand.
- **PaperPi keeps at least 2 GB free** on the disk. Below that, plugins are told the disk is low, so they don't save more, and the log says so. PaperPi removes nothing else, because the space may be used by something outside PaperPi.

Note: a file that is only read keeps getting older. A plugin that must keep a file (for example a login token) writes it again within `storage_days`, or suggests `storage_days = 0`.

## Files on the SD card

A frozen PaperPi v1 was not fixed by restarting PaperPi or the Pi, only by wiping the SD card and installing everything again. So v2 keeps everything it stores small and replaceable:

- the config file has a last good copy;
- files are replaced in one step (first written to a temporary file), so a power cut can't leave half a file;
- logs and plugin folders have size limits, and PaperPi keeps 2 GB free;
- the health file is in `/run/paperpi`, in memory, so it causes no SD card writes.

## Numbers

| What                                         | Value                       |
| -------------------------------------------- | --------------------------- |
| "still running" report                       | every 30 seconds            |
| watchdog restarts PaperPi after              | 2 minutes without a report  |
| health values in the log                     | once an hour                |
| log lines kept for the web interface         | 5,000                       |
| log file size before a new one starts        | 1 MB (two files: about 2 MB) |
| longest log line                             | 10,000 characters           |
| log lines per plugin update                  | 100                         |
| summary of a repeated error                  | every 10 minutes            |
| free disk PaperPi keeps                      | 2 GB                        |
| longest clean-up of one storage folder       | 10 seconds                  |
| most files looked at in one clean-up         | 100,000                     |

## Not built yet

- **A memory limit for PaperPi** in its systemd service (`MemoryMax=`), as a safety net if it ever used too much memory.
- **The screen helper process's own log lines** (epdlib's) are not sent to PaperPi's log yet.
- **Changing the web request limits** in the config file.

## Why it works this way

- **"Still running" means the loop runs, not that the screen works:** otherwise a broken screen would cause a restart loop, and the web interface that shows the error would keep going away.
- **A screen that keeps failing pauses instead of exiting:** with a broken screen, exiting would also become a restart loop.
- **Size limits per plugin, not for all plugins together:** SD cards are large, and a photo plugin needs much more than a weather plugin. The 2 GB of free space protects the rest of the system.
- **The full story** is in the old design notes [`errors-and-time-limits.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/errors-and-time-limits.md) and [`freeze-prevention.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/freeze-prevention.md).

## In the code

- `src/paperpi/limits.py`: every time limit and size limit.
- `src/paperpi/health.py`: the "still running" reports to systemd and the health file.
- `src/paperpi/logbook.py`: the log file, the lines for the web interface and repeated errors.
- `src/paperpi/storage.py`: the storage folders, their limits and the free disk check.
- `src/paperpi/webrequest.py`: web requests with their time and size limits.
- `src/paperpi/screen.py`: the screen's time limits and watchdog ([Screens and drivers](screens.md)).
- `src/paperpi/files.py`: writing a file in one step.
