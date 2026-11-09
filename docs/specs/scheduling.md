# Which plugin is shown, and when

The scheduler is the part of PaperPi that decides which plugin is on the screen and for how long. It is also the only part that writes to the screen: plugins never draw on the screen themselves, they only hand in pictures. Every plugin updates on its own timer all the time, so when a turn changes, the next plugin's picture is already there and is shown at once.

How this looks to a user is on [Understanding Plugin Schedules](../take-turns.md). This page describes the exact rules.

## Levels

Every plugin has a level. The level decides when the plugin may take the screen.

| Level       | When it is shown                                                                 | How its turn ends                                                       |
| ----------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `alert`     | as soon as the plugin has something; nothing interrupts it                       | the plugin has nothing any more, or someone dismisses the alert         |
| `interrupt` | as soon as the plugin has something (e.g. a song is playing), at once           | the plugin has nothing any more; the rotation goes on with the next one |
| `rotation`  | when no alert or interrupt is shown; these plugins take turns in config order   | its `display_time` is over                                              |

Several alerts, or several interrupts, take turns for their `display_time` each.

A plugin suggests its own level (`rotation` unless it says otherwise), and a `[[plugin]]` block without `level` uses that suggestion. The music plugins suggest `interrupt`.

Note: a plugin only reports whether it has something to show. It does not choose its level. A warning that should take over the screen is a separate `[[plugin]]` block with level `alert`.

## Updates

- **Every plugin updates at its own `refresh` rate,** on screen or not. `refresh` is at least 5 seconds.
- **At most 3 updates run at the same time,** each in its own process. A music plugin's check never waits behind a slow weather download.
- **Updates on the minute:** a plugin can say that its updates line up with the clock (the clocks do). Its update then starts 1 second after the minute changes, instead of counting from the last update.
- **The screen is written only when the picture changed.** The new picture is compared with the last one on the screen, pixel by pixel.
- **Near the end of a turn:** a new picture from the plugin on screen is not written when its turn ends sooner than a screen write takes. The next plugin is about to take over anyway.

Note: when a plugin's `refresh` equals its `display_time`, the config check shows a hint (not an error): the plugin may redraw just as its turn ends. Make `refresh` a little longer, or a fraction of `display_time`.

## Alerts

- **Dismissed, but still reported:** a dismissed alert comes back as a reminder after `alert_reminder` seconds (1 hour unless changed) if the plugin still reports it.
- **Safety limit:** an alert held longer than `alert_max_time` (24 hours unless changed) is dismissed by itself, in case the plugin is stuck. There are no reminders after that until the plugin reports a new alert, and the web interface shows a warning.

## Controls

The web interface's home page has these buttons. Buttons on the frame will use the same controls later.

| Control           | What happens                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------- |
| **Show now**      | the plugin gets one extra turn of its full `display_time`, also over an alert or interrupt; then the order goes on as planned |
| **Skip to next**  | the turn on screen ends; an alert is dismissed; an interrupt stays away until its picture changes (e.g. the next song) |
| **Refresh**       | the plugin on screen is updated at once, and its picture is drawn in full after a clear, also when it did not change |
| **Try again now** | a failing plugin is updated at once; a paused screen is tried again at once                                   |
| **Dismiss alert** | the alert is dismissed; see [Alerts](#alerts)                                                                 |

Note: **Show now** on a plugin without a picture (paused after failures, or its first update not done yet) updates it at once. Its turn starts when the picture is ready. If that update fails, nothing changes on the screen and the error is shown with the plugin.

## Failures

- **A failed update** (a crash, the time limit, a data source that doesn't answer) is skipped, and the plugin is tried again at its next refresh. One good update sets its failure count back to 0.
- **After 3 failures in a row** the plugin is left out for 30 minutes, and the web interface shows a warning. If its first update after that fails too, it is left out for another 30 minutes.
- **A plugin with nothing to show** is skipped. That is not a failure.
- **When nothing can be shown because plugins are failing,** the [`default`](../plugins/default.md) plugin shows how many are not working.
- **A failed screen write** is tried again at the next update of the plugin on screen.

## Start, the fallback clock and reloads

- **Start:** the screen is not touched until the first picture is ready. The [splash screen](../plugins/splash_screen.md) is updated first and shown for `splash_time` seconds (60 unless changed; `0`: not at all) while the other plugins update. Alerts and interrupts wait until it ends.
- **No plugin ready to show** (for example the first start after installing): the splash screen stays on the screen until a plugin is configured, with a new picture every hour. If it fails, `default` says that no plugin is ready to show.
- **Fallback clock:** when no plugin has anything to show and none is failing (for example only a music plugin, and no music), a small clock is shown: the [Clock](../plugins/basic_clock.md) plugin's `small` layout. An empty screen can't be told apart from a broken one; a clock that changes every minute shows that PaperPi works. It waits until every plugin has reported once, so it doesn't flash up at start. `fallback_clock = false` in `[display]` switches it off; the config check then shows a hint.
- **Config reload:** plugins whose settings did not change keep their place and their picture. A changed plugin keeps its old picture on the screen until its new one is ready. Plugins take turns in the order of the new file. When the plugin on screen is removed, the rotation goes on with the one after it. A reload does not show the splash screen again.
- **Stop:** updates that have not started are dropped, and running ones are stopped at once, so stopping never waits for a hanging plugin.

## Numbers

| What                                  | Value                                     | Setting                      |
| ------------------------------------- | ----------------------------------------- | ---------------------------- |
| time on screen per turn               | 120 seconds                               | `display_time`               |
| time between updates                  | the plugin's suggestion; at least 5 seconds | `refresh`                  |
| longest time for one update           | 60 seconds (at most 600)                  | `time_limit`                 |
| updates at the same time              | 3                                         | none                         |
| update on the minute                  | 1 second after the minute changes         | none (the plugin says so)    |
| failures before a plugin is left out  | 3 in a row                                | none                         |
| time a failing plugin is left out     | 30 minutes                                | none                         |
| reminder of a dismissed alert         | 1 hour                                    | `alert_reminder`             |
| longest alert                         | 24 hours                                  | `alert_max_time`             |
| splash screen at start                | 60 seconds                                | `splash_time` in `[display]` |
| longest value of any time setting     | 7 days                                    | none                         |

## Not built yet

- **Several plugins on the screen at once:** the scheduler picks plugins for one region, the whole screen. Later, each region of the screen will get its own scheduler with the same rules.
- **Buttons on the frame** that send the same controls as the web interface.

## Why it works this way

- **Levels instead of numbers:** PaperPi v1 used priority numbers that only made sense compared with other plugins' numbers. Three named levels cover every real use found in v1.
- **One part decides:** if two parts of PaperPi could change the screen at the same moment, the result would depend on which one was first. The scheduler makes every decision in one step, in one place, so two plugins can never both win.
- **Every plugin updates all the time:** a turn change then never waits for a download.
- **The full story** of these choices, with the options that were not chosen, is in the old design note [`plugin-scheduling.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/plugin-scheduling.md).

## In the code

- `src/paperpi/scheduler.py`: the scheduler. One loop makes every decision, in one thread; finished updates, screen writes, reloads and the controls reach it as messages in one queue.
- `src/paperpi/limits.py`: the numbers above that have no setting.
- `src/paperpi/plugin.py`: the scheduling settings of a `[[plugin]]` block.
- `tests/test_scheduler.py`: the tests, which use a pretend clock so hours of switching are checked in seconds. The [`debugging`](../plugins/debugging.md) plugin can crash, hang and switch states on purpose.
