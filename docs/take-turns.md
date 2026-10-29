# Understanding Plugin Schedules

PaperPi shows one plugin at a time. This page explains how it picks which one, and the settings that change it. You find these settings in the **General** section of a plugin's settings page.

## Taking turns

Normally the plugins that are switched on take turns, in the order of the list on the Home page. Each one stays on the screen for its **display time** (2 minutes unless you change it), then the next one comes. After the last one, the first comes again.

A plugin with nothing to show at the moment is skipped. For example, a calendar plugin with no events coming up, or a music plugin while nothing is playing.

## Getting new data

Each plugin gets new data and draws a new picture every so often: its **refresh** time. A clock does it every minute, a weather plugin every half hour. Each plugin sets a sensible refresh time itself; you only need to change it if you want something else.

Plugins get new data all the time, also while they are not on the screen. So when it's a plugin's turn, its newest picture is shown straight away.

The screen only changes when the picture changed. If a plugin draws the same picture again, nothing happens on the screen.

!!! tip "Refresh and display time"
    If a plugin's refresh time is the same as its display time, the new picture can arrive just as its turn ends. Make the refresh a little longer than the display time, or a fraction of it (for example, display time 120 seconds and refresh 60 seconds).

## Levels: rotation, interrupt and alert

Each plugin has a **level**: how important it is.

**Rotation** is the normal level: the plugin takes turns with the others, as described above. Most plugins are rotation plugins.

**Interrupt** is for plugins that only have something to show now and then. The music plugins are interrupt plugins: when a song starts playing, the plugin takes over the screen at once, and keeps it while the music plays. When the music stops, the plugins go back to taking turns. If several interrupt plugins have something at the same time, they take turns with each other.

**Alert** is for warnings that must be seen, such as a leak alarm. An alert takes over the screen, also from an interrupt, and stays until the plugin says it is over or someone presses **Dismiss alert** on the Home page. If the plugin still reports the same alert after you dismiss it, it comes back as a reminder after an hour (`alert_reminder`). An alert that lasts more than a day is dismissed by itself (`alert_max_time`), in case the plugin is stuck.

Each plugin suggests its own level, so you rarely need to change it. You can: for example, set a music plugin to rotation if it should take turns like the others instead of taking over.

## The buttons on the Home page

- **Show now** gives a plugin one extra turn right away, also during an alert or interrupt. Afterwards everything goes on as before.
- **Skip to next** ends the turn of the plugin on the screen. A skipped interrupt stays away until it has something new (the next song); a skipped alert counts as dismissed.
- **Refresh** gets new data for the plugin on the screen and draws it again, with a full redraw of the screen. Use it when the screen shows faint leftovers of earlier pictures.

## When a plugin fails

A plugin can fail: the internet is down, a website doesn't answer, a setting is wrong. PaperPi then skips it and tries again at its next refresh. After 3 failures in a row, it leaves the plugin out for 30 minutes and shows a warning on the **Warnings** page. One good update puts it back.

If no plugin can be shown because plugins are failing, the screen says how many are not working, with a QR code that opens the web interface.

## When there is nothing to show

If no plugin has anything to show (for example, you only have a music plugin and no music is playing), a small clock appears at the bottom of the screen. It shows that PaperPi is still working: an e-paper screen keeps its last picture without power, so a screen that never changes looks the same as a broken one. You can switch the clock off on **Screen & system** (**Fallback clock**), but that is not recommended.

## At start

When PaperPi starts, it first shows its name, version and web address for a minute (**Splash Screen** on **Screen & system**, `0` for not at all), while the plugins get their first data. If no plugin is ready to show, for example right after installing, the address stays on the screen until one is.
