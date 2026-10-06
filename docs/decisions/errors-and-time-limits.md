# Errors and time limits

Status: proposed (M1, issue #190). Decided with txoof.

## Problem

`freeze-prevention.md` sets the rules: every wait has a time limit, plugins run with a deadline, errors are handled or end the program, logs and caches have size limits, and a watchdog restarts PaperPi when it stops reporting "healthy". This note fills in the numbers and definitions, so every part of PaperPi follows the same rules.

## Options considered

**What "healthy" means for the watchdog**
1. Healthy only if the screen was updated recently. Rejected: an unplugged or broken screen would make PaperPi restart again and again, and the web interface, which shows the error, would keep disappearing.
2. **Healthy if the scheduler is still running its loop.** Chosen. Screen failures are handled on their own (below).

**When screen writes keep failing**
1. Exit after a number of failures and let systemd restart PaperPi. Rejected: with a broken screen this becomes a restart loop.
2. **Retry, then reset the display, then wait and retry, without exiting.** Chosen. Exit only when a write is stuck in a way only a full restart can fix.

## Decision (proposed)

### Watchdog and health check

- The scheduler (the one part of PaperPi that decides what is shown) reports "healthy" every 30 seconds.
- If no report arrives for 2 minutes, the watchdog restarts PaperPi: systemd's watchdog outside Docker, Docker's health check inside it. Both use the same report.
- Healthy does **not** require a recent screen update.

How it is built (`src/paperpi/health.py`, M4):
- Only the scheduler loop reports, so if the loop itself gets stuck, the reports stop. Screen writes run outside the loop (see "When screen writes fail" below), so a slow write does not stop them; the screen watchdog handles a write that never ends. The loop wakes up for a report even when nothing else is due.
- To systemd: the first report says `READY=1`, every report `WATCHDOG=1`, and stopping on purpose says `STOPPING=1`. PaperPi sends the messages itself with Python's standard library, in the way systemd documents for this (a few lines; a package for it, `cysystemd`, was tried and dropped because it carries its own copies of system libraries that get no security updates). They are sent only when systemd asked for them (the `NOTIFY_SOCKET` variable is set); PaperPi removes that variable before plugin processes start. The service (M6) needs `Type=notify` (systemd counts PaperPi as started only after `READY=1`), `WatchdogSec=120` (systemd restarts PaperPi when no `WATCHDOG=1` arrives for 120 seconds), `RuntimeDirectory=paperpi` (systemd makes `/run/paperpi` for PaperPi's user; only root can make it otherwise) and the default `NotifyAccess=main` (only messages from the main process count, so a plugin process can't say "still running" for a stuck loop).
- For Docker: each report replaces the file `/run/paperpi/health` (on Raspberry Pi OS `/run` is in memory and emptied at every start of the Pi). It holds one line: the time of the report, and the health data of `freeze-prevention.md` rule 8 (time since the last screen write, the screen state `ok`, `failing` or `paused` (see "When screen writes fail"), memory use and open files of the main PaperPi process, not of the plugin processes, and free space on the disk that holds `--state-dir`). It is replaced, never added to, so it can't grow. The file is written before systemd is told, so "ready" means the file is there. `paperpi health` fails (exit status 1, the number a program returns to say it failed) when the report is missing or older than 2 minutes; Docker's health check runs it. Stopping on purpose removes the file.
- The same values go to the log at the first report and then once an hour (agreed with txoof on 2026-10-06), so slow growth of memory or open files can be seen over weeks, also in the long run on this Pi (`freeze-prevention.md`). That is 24 lines a day.
- A failed report (no file can be written, systemd not answering) is logged once, and again only if it comes back after working. It does not stop PaperPi. `READY=1` is tried again with every report until it works.

### When screen writes fail

| Situation | What PaperPi does |
|---|---|
| 1 failed write | Try again at the next update. |
| 3 failures in a row | Reset the display: restart the screen helper process (see `display-driver-interface.md`) and pulse the screen's reset pin. |
| 3 resets in a row that don't help | Stop writing. Show "screen not answering" in the web interface and try again every 10 minutes. PaperPi keeps running. |
| A write is stuck and stopping the helper process doesn't end it | Exit, so systemd/Docker restarts PaperPi. At most once per hour, so this can't become a loop. |

How it is built (`src/paperpi/screen.py`, M4 issue #222):
- The screen driver lives in a helper process. The scheduler sends each image there from a thread of its own, so its loop keeps reporting "healthy" during a slow write, and decides nothing new until the write has finished.
- A write that runs over its time limit stops the helper process. The next write starts a new one, and the driver's `init` resets the screen (the IT8951 driver pulses its reset pin). A helper process that crashes is noticed at once.
- Every 3rd failed write in a row restarts the helper process (a reset). When the write after the 3rd reset fails too, writes pause and are tried once every 10 minutes; the helper process is not running during the pause, so the pins are free. One good write ends the pause and resets the counts.
- The health report has a `screen` value: `ok`, `failing` or `paused` (none before the first write).
- The helper process is a direct child of PaperPi (started with Python's "spawn" method, not by the forkserver that starts plugin processes), so PaperPi can always stop it. It ignores Ctrl+C and systemd's stop signal; PaperPi closes it, and kills it if needed.
- When a helper process can't be stopped, PaperPi exits at once with status 1 (without Python's normal exit steps, which would wait for that process), and systemd or Docker starts it again. The time of that exit is kept in `screen-stuck` in the state folder; within an hour of the last one, or when that file can't be written, PaperPi pauses writes instead of exiting. No new helper process starts while a stuck one still runs.
- There is no planned restart of the helper process (see `it8951-driver.md`).

### When plugins fail

As in `plugin-scheduling.md`: a failed update is skipped and retried at the plugin's next turn. After 3 failures in a row, the plugin is left out for 30 minutes and the web interface shows a warning. If all plugins fail, the default plugin shows "X of Y plugins are not working" with a QR code to the web interface.

### Time limits

| What | Default time limit |
|---|---|
| One plugin update (fetch data and draw) | 60 s; can be changed per plugin in the web interface |
| One web request by a plugin | 10 s to connect, 30 s in total, including one retry after 5 s (so a plugin still has time to draw). At most 5 MB in the answer after unpacking; a plugin can ask for more, e.g. for images. All plugins use one shared helper for web requests: `paperpi.webrequest`. |
| One screen write | 3 × the measured redraw time, at least 30 s, at most 5 min. Before the first measurement: 2 min (5 min for colour screens). |
| Reading or writing a file | 10 s |

- All defaults are set in one place in the code.
- Only the plugin time limit is in the web interface. The others can be changed in the config file for unusual cases (not yet for web requests).
- All durations use the monotonic clock (a clock that only counts forward and does not jump when the time is corrected).

### Logs

- Logs go to the system log (`journalctl -u paperpi`), which has its own size limit. In Docker, logs are kept in at most 3 files of 10 MB.
- Default level: WARNING, as in v1.
- An error that repeats is logged once. After that a summary line is written every 10 minutes, e.g. "same error repeated 40 times".
- The web interface shows the last 100 warnings and errors.

### Saved files (cache)

- Each plugin has its own folder in `/var/lib/paperpi/plugins/` (see `plugin-interface.md`).
- Limits: 50 MB per plugin, 200 MB for all plugins together. When a limit is reached, the oldest files are removed first.
- Files older than 30 days are always removed.

## Open questions

- For M6 (Docker):
  - Docker itself only marks a container "unhealthy"; it does not restart it. The install must choose how an unhealthy PaperPi is restarted (for example, the health check command also ends the container, which `restart: always` then starts again).
  - Inside a container `/run` is not kept in memory. The container must keep `/run/paperpi` in memory (a "tmpfs" mount), so the report causes no SD card writes and is gone after a restart.
  - There is no report until the scheduler loop has started, so the health check needs a start period (a time at the start when failures don't count).

All other points above were agreed with txoof on 2026-10-04.
