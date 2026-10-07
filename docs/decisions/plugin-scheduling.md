# Choosing which plugin is shown, and when

Status: proposed (M1, issue #194). Decided with txoof.

## Problem

PaperPi shows one plugin at a time. Something has to decide which plugin is on screen and for how long.

In v1, each plugin reports a priority number every time it updates (lower number means more important). Only the plugins with the lowest current number take turns. This works, but it is hard to set up: users have to pick numbers that only make sense compared with other plugins' numbers, and the only way to switch a plugin off is to rename its config section to `[xPlugin: …]`.

What txoof's screen does today, and what v2 must still do:
- Normally, word clock, weather and moon phase take turns.
- When music plays (Spotify or Logitech Media Server), the music plugin takes over. When the music stops, the screen goes back to taking turns.

Other users must be able to set up their own behaviour.

## Options considered

1. **Keep priority numbers** (v1). Flexible, but hard to understand and easy to get wrong.
2. **A few named levels.** Each plugin is given one level in the config. Covers every real use found in v1 with no numbers. **Chosen.**
3. **Time-of-day schedules** (e.g. weather only from 6:00 to 22:00). Not needed now.

## Decision (proposed)

### Three levels

Each plugin in the config has one level, and an on/off setting.

| Level | When it shows | How it ends |
|---|---|---|
| **alert** | As soon as the plugin reports an alert. Nothing can interrupt it. Several alerts at once take turns. | The plugin says the alert is over, or someone dismisses it in the web interface. |
| **interrupt** | As soon as the plugin reports it has something (e.g. a song is playing). Takes over at once, even if the current rotation plugin has just started. Several at once take turns. | The plugin says it is done. The rotation then continues with the **next** plugin in the queue. |
| **rotation** | When no alert or interrupt is active. Plugins take turns in the order set in the config / web interface, each for its own display time. | Its display time is over. |

Examples: word clock, weather and moon phase are `rotation`. Music players are `interrupt`. A future civil-defence warning or a Home Assistant leak alarm would be `alert`.

### Alerts in detail

- **Dismissed by someone, but the plugin still reports the same alert:** it comes back as a reminder after a set time. Setting: `alert_reminder` (default 1 hour).
- **Safety limit:** an alert held longer than `alert_max_time` (default 24 hours) is dismissed automatically, in case the plugin is stuck. After that there are no reminders until the plugin reports a *new* alert, and the web interface shows a warning, e.g. "Leak alert was active for 24 hours and was dismissed".

### Refreshes near the end of a turn

A rotation plugin keeps updating at its refresh rate while it is on screen (see `plugin-interface.md`). A refresh that starts just before the plugin's turn ends wastes a screen redraw, and on a slow screen the redraw may still be running when the next plugin wants the screen.

- **Rule:** if a refresh would start within the last part of a plugin's turn, it is not written to the screen, because the next plugin is about to take over. The margin is the screen's measured redraw time (see `errors-and-time-limits.md`), so it also fits slow colour screens. This covers every timing, also ones that only line up now and then (display time 300 s with a refresh every 60 s: the 5th refresh would land exactly at the end of the turn).
- **Hint:** when a plugin's `refresh` equals its `display_time`, the config check and the web interface show a hint, not an error: "refresh equals display time: the plugin may redraw just as it is swapped out; make refresh slightly longer, or a fraction of the display time". The config still loads.
- Good choices: a refresh slightly longer than the display time (the plugin updates just before its turn and not during it), or a fraction of it. Defaults and examples follow this.

Added 2026-10-05 (M4, issue #203), agreed with txoof.

### Updates on the minute

A clock must update right after the minute changes. If it updates every 60 seconds counted from some random moment, it can show the wrong minute for most of a minute.

- A plugin can declare that its refreshes line up with the clock, e.g. "on the minute". This is part of the plugin's description, not a user setting.
- The scheduler then starts the update just after the minute changes (1 second after second 0), instead of counting from the last update.
- The other rules still apply: a refresh near the end of a turn is still not written to the screen, and the update still has its time limit.

Added 2026-10-05 (M4, issue #203), agreed with txoof.

### One decision-maker, so no race conditions

A race condition is when two parts of a program try to change the same thing at the same moment and the result depends on which one is first.

To avoid it, one single part of PaperPi (the scheduler) decides what is shown and is the only part that writes to the screen. Plugins never draw on the screen. They only report their state: "nothing", "I have something", or "alert". The scheduler reads all states and makes each decision in one step, so two plugins cannot both win.

### Failures

- A plugin that fails (crash, time limit reached, data source down) is skipped. The rotation moves to the next plugin, and the failed one is tried again at its next refresh.
- After 3 failures in a row, the plugin is left out for 30 minutes and the web interface shows a warning. If its first update after that fails too, it is left out for another 30 minutes at once; one good update ends this.
- If nothing else can be shown because plugins are failing, or no plugin is switched on and the splash screen fails (see "First start" below), the `default` plugin is shown. The scheduler tells it how many plugins are failing, and it shows e.g. "3 of 4 plugins are not working. See the web interface for more information." with a QR code (a square barcode a phone camera can scan) that opens the web interface.
- `default` and `splash_screen` are normal plugins. The scheduler passes the failure status to `default`, starts it only when it is needed, and never puts it in the rotation.

The numbers 3 and 30 minutes are defaults. Time limits and watchdog rules are decided in the error-handling note (#190).

### Testing

The `debugging` plugin is used to test this: it can be set to crash, time out, and switch between "nothing", "I have something" and "alert" at set rates. Tests run the scheduler with a fake clock, so hours of switching can be checked in seconds.

### How it is built

Added 2026-10-05 (M4, issue #205), agreed with txoof. Code: `src/paperpi/scheduler.py`.

- **Every plugin updates at its own refresh rate all the time**, on screen or not (see `plugin-interface.md`). A turn change shows the next plugin's newest image at once.
- **At most 3 updates at the same time**, each in its own process. A music plugin's check then never waits behind a slow weather download. Plugins update rarely, so 3 is enough, and memory use stays low on a Pi 3.
- Built from standard Python parts: a pool of 3 worker threads (`ThreadPoolExecutor`; a thread is a part of a program that runs at the same time as the rest) that start the plugin processes, and one queue (a list where messages wait until they are read, oldest first) that carries finished updates, "reload", "stop" and "dismiss" to the scheduler's loop. The loop sleeps until the next event or the next moment something is due; it does not wake up every few seconds to check. The clock is passed in, so tests use a fake clock.
- **The level decides.** A plugin's state only says whether it has something: for alert and interrupt plugins, "ready" and "alert" mean the same, and a rotation plugin that reports "alert" is shown in its normal turn. A warning that should take over the screen is a separate `[[plugin]]` block with level `alert`.
- **The screen is written only when the picture changed.** The new image is compared with the last one sent to the screen, pixel by pixel (a few milliseconds for the 9.7" screen). A refresh that brings the same picture is not written.
- **Refresh limits:** `refresh` is at least 5 seconds, both the user's setting and a plugin's suggestion. Faster is never wanted: slow screens take tens of seconds to minutes to redraw, and on fast screens it would flicker. At most 7 days, like `display_time`, `alert_reminder` and `alert_max_time`.
- **Taking turns:** several alerts, or several interrupts, take turns for their `display_time` each.
- **Alert settings per plugin:** `alert_reminder` and `alert_max_time` are in each `[[plugin]]` block, like `display_time`. They only matter for level `alert`.
- **Failures:** a failed update is tried again at the plugin's next refresh. One good update sets the count of failures back to 0. A plugin that has nothing to show ("nothing") is skipped, which is not a failure.
- **`default`:** shown when nothing else can be shown and at least one plugin is failing, or when no plugin is switched on and the splash screen fails. If `default` itself fails, the screen also keeps its picture, and the error goes to the log. The QR code comes with the web interface (M5). PaperPi always has a `default` plugin, also when the config has no block for it.
- **Fallback clock:** when no plugin has anything to show and none is failing (e.g. only a music plugin, and no music, or an alert has just ended), a small clock is shown: `basic_clock` with its `small` layout, time and date on one line at the bottom, updated every minute. An empty or unchanging screen can't be told apart from a broken one; a clock that changes every minute shows that PaperPi works. It waits until every plugin has reported once, so it doesn't flash up at start, and it never shows an out-of-date time. It can be switched off with `fallback_clock = false` in `[display]`, which is strongly discouraged: the config check shows a hint, and the screen then keeps its last picture. Agreed with txoof 2026-10-05, after the code review.
- **On the minute:** the update starts 1 second after the minute changes. This is the only place where the wall-clock time (the time of day, which can jump when it is corrected) is used; every duration uses the monotonic clock (a clock that only counts forward).
- **Start:** the screen is not touched until the first image is ready.
- **Splash screen at start:** the `splash_screen` plugin is updated first and shown for `[display] splash_time` seconds (default 60; `0`: not at all; v1 had `splash = True`) with PaperPi's name, version, web address and a QR code, while the other plugins update in the background; then the normal choice starts. Alerts and interrupts wait until it ends. If its update fails, the normal choice starts at once. A config reload does not show it again. It is a normal plugin, so start-up needs no drawing code of its own.
- **First start (no plugin switched on):** the first start after installing has only the default config, with no plugins; the user sets PaperPi up in the web interface. Whenever no plugin is switched on, the splash screen stays on screen (whatever `splash_time` says), with a new picture every hour, until a config reload switches one on. If it fails, `default` says that no plugin is switched on. So the default config written by the installer (M6) has no `[[plugin]]` blocks. Agreed with txoof 2026-10-07.
- **Config reload** (see `live-config-reload.md`): on the reload signal the config file is read again. Plugins whose settings did not change keep their place and image. A changed plugin keeps its old image on screen until its new one is ready. A broken file is not applied. Which screen settings apply at once and which at the next start: see the table in `live-config-reload.md` (built in M4 part 5b). Plugins take turns in the order of the new file. When the plugin on screen is removed, the rotation goes on with the one after it.
- **Stopping:** updates that have not started are dropped, and running ones are stopped at once, so stopping never waits for a hanging plugin's time limit.
- **Screen write fails:** it is tried again at the next update of the plugin on screen; when the screen watchdog pauses writes (`errors-and-time-limits.md`), at the end of the pause. The error is logged once, and a line is logged when writes work again.

### Later: several plugins on screen at once (M9)

The scheduler picks plugins for a screen region. In v2.0 there is one region, the whole screen. In M9 each region gets its own scheduler with the same rules.

### Example config

The file format is decided in #186. Whatever the format, a plugin entry has these scheduling settings:

```
plugin:       word_clock
enabled:      true
level:        rotation      # alert | interrupt | rotation
display_time: 255           # seconds per turn, when plugins take turns
```

## Open questions

None. All points above were agreed with txoof on 2026-10-04.
