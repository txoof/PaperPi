# ical_calendar

Shows the next events from one, two or three calendars in one list sorted by time.

This plugin takes its turn with the other plugins using the `rotation` display level. It needs the internet and the secret iCal address of each calendar.

![The plugin's default layout on the 9.7" screen: today's date at the top, then one row per event with its day, time and title](../../../../tests/images/ical_calendar-list-9in7.png)

## What you need

- **A calendar with an iCal address:** Google Calendar, Outlook.com, iCloud, Nextcloud, Fastmail and others. iCal is the standard file format for calendars. No login is needed.
- **The calendar's secret address:** a web address that gives its events to anyone who has it. Treat it like a password. See [Getting the address](#getting-the-address).

## Set it up

1. Copy the secret address of your calendar (see below).
2. In the PaperPi web interface, open the **Plugin Library** and add **Calendar**.
3. On its settings page, paste the address in `calendar_1`.
4. Optionally, add a second and third calendar in `calendar_2` and `calendar_3`, and give each a short name in `name_1` to `name_3` (e.g. `Family`).
5. Save.

Note: addresses must start with `https://` or `webcal://`. `http://` only works for a server on your home network (such as `http://192.168.1.5/...`).

## Getting the address

**Google Calendar** (on a computer, at calendar.google.com):

1. Click the gear icon at the top right, then **Settings**.
2. On the left, under "Settings for my calendars", click the calendar.
3. Scroll to **Integrate calendar** and copy **Secret address in iCal format** (it ends in `/basic.ics`).

Note: only the owner of a calendar, and people who may "make changes and manage sharing", see this address. Work and school accounts may have it switched off by their administrator. If the address ever gets out, click **Reset** next to it: the old address stops working.

**Outlook.com:** Settings (gear icon), **Calendar**, **Shared calendars**. Under **Publish a calendar**, choose the calendar and "Can view all details", click **Publish**, and copy the **ICS** link. **Unpublish** stops the old link.

**iCloud** (on an iPhone or iPad): in the Calendar app tap **Calendars**, tap (i) next to an iCloud calendar, turn on **Public Calendar** and tap **Share Link** to copy it. Turning **Public Calendar** off stops the link.

## What it shows

Each day is named once ("Today", "Tomorrow", "Sat 3 Oct"); all-day events come first on their day. With two or three calendars, each event has its calendar's mark before the title (a filled circle, an open circle or a filled square), and the top right shows each mark with the calendar's name.

The time column shows the start time, "all day", or when a longer event ends ("until Sun 4", "ends today"). When there are more events than rows, the last row says how many more ("+ 3 more"). With no events: "Nothing planned for the next 7 days". Times are shown in the Pi's own time zone.

## Layouts

| Layout           | Shows                                                                     |
| ---------------- | ------------------------------------------------------------------------- |
| `list` (default) | today's date and the calendars' names, then the next 8 events             |
| `small`          | for tiny screens (2" to 3"): the next 3 events, with the marks but no names |

| `list`, 9.7" | `list`, 7.5" | `small`, 2.13" |
|---|---|---|
| ![list](../../../../tests/images/ical_calendar-list-9in7.png) | ![list 7.5](../../../../tests/images/ical_calendar-list-7in5.png) | ![small](../../../../tests/images/ical_calendar-small-2in13.png) |

## When something is wrong

When a calendar can't be downloaded, its saved events are shown instead, for up to one day. Without saved events, the other calendars are still shown and the last row says so ("Family: not updated"). When every calendar fails, the plugin's card on the web interface's home page shows the error, and PaperPi tries again at the next update ([Troubleshooting](https://txoof.github.io/PaperPi/troubleshooting/)).

Note: an error "404 Not Found" usually means the address was reset. Copy the new one into the settings.

Note: on a Pi 3, three large calendars can take longer than one update may take. Raise `time_limit` (60 seconds unless changed) if updates are stopped.

## Settings

| Setting                      | Default        | Meaning                                                                                |
| ---------------------------- | -------------- | -------------------------------------------------------------------------------------- |
| `calendar_1`                 | none, required | secret iCal address of a calendar, starting with `https://` or `webcal://`             |
| `calendar_2`                 | none           | secret iCal address of a second calendar, shown in the same list                       |
| `calendar_3`                 | none           | secret iCal address of a third calendar, shown in the same list                        |
| `name_1`, `name_2`, `name_3` | `""`           | short name of each calendar, shown next to its mark, e.g. `"Family"` (at most 20 characters) |
| `days`                       | `7`            | how many days to show, starting today (1 to 31)                                        |
| `hours`                      | `24`           | `24` (15:45) or `12` (3:45 PM)                                                         |

The addresses are secret settings: the web interface shows them as password fields, and PaperPi never writes them in its log.

The plugin asks for new events every 30 minutes unless you change `refresh`, so a new event can take up to half an hour to show.

### Configuration Keys

```toml
[[plugin]]
id = "ical_calendar-47398d0f"
name = "Calendar"
type = "ical_calendar"
calendar_1 = "https://calendar.google.com/calendar/ical/.../basic.ics"
calendar_2 = "https://calendar.google.com/calendar/ical/.../basic.ics"
name_1 = "Personal"
name_2 = "Family"
days = 5
```

## For developers

The plugin downloads each calendar at every update. Google sends the whole calendar, back to its first event, so a calendar used for some years is about 1 MB, and reading it takes about 5 seconds on a Pi 4. A calendar file larger than 8 MB is refused. After each download, the plugin saves that calendar's events of the coming days in its storage folder; saved events are not used for another address, or after a change of `days`.

Some events are left out to keep the Pi working, because anyone can send an invitation and Google adds invitations to the calendar: events without a start time or with impossible times, and events that repeat every hour or more often. Cancelled events are left out too. An event without a title shows "(no title)"; titles are cut at 200 characters. Error messages name only the server ("calendar.google.com answered 404 Not Found"), never the address.

Why not a normal Google login? Google doesn't allow the "enter a code on your phone" login for calendars, and a login made for a single household stops working every 7 days. The secret address avoids both.

Try it without a screen: `uv run paperpi render ical_calendar` (made-up sample data: a week from two calendars, "Personal" and "Family"), or with real data: `uv run paperpi render ical_calendar --live --set calendar_1=<address>`. An address typed on the command line stays in the shell's history, so prefer the config file or the web interface for real addresses.
