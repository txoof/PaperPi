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

### When screen writes fail

| Situation | What PaperPi does |
|---|---|
| 1 failed write | Try again at the next update. |
| 3 failures in a row | Reset the display: restart the screen helper process (see `display-driver-interface.md`) and pulse the screen's reset pin. |
| 3 resets in a row that don't help | Stop writing. Show "screen not answering" in the web interface and try again every 10 minutes. PaperPi keeps running. |
| A write is stuck and stopping the helper process doesn't end it | Exit, so systemd/Docker restarts PaperPi. At most once per hour, so this can't become a loop. |

### When plugins fail

As in `plugin-scheduling.md`: a failed update is skipped and retried at the plugin's next turn. After 3 failures in a row, the plugin is left out for 30 minutes and the web interface shows a warning. If all plugins fail, the default plugin shows "X of Y plugins are not working" with a QR code to the web interface.

### Time limits

| What | Default time limit |
|---|---|
| One plugin update (fetch data and draw) | 60 s; can be changed per plugin in the web interface |
| One web request by a plugin | 10 s to connect, 30 s in total, including one retry after 5 s (so a plugin still has time to draw). At most 20 MB in the answer. All plugins use one shared helper for web requests: `paperpi.webrequest`. |
| One screen write | 3 × the measured redraw time, at least 30 s, at most 5 min. Before the first measurement: 2 min (5 min for colour screens). |
| Reading or writing a file | 10 s |

- All defaults are set in one place in the code.
- Only the plugin time limit is in the web interface. The others can be changed in the config file for unusual cases.
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

None. All points above were agreed with txoof on 2026-10-04.
