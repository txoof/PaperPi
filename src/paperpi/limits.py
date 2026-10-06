"""Default time and size limits, all in one place.

The numbers come from ``docs/decisions/errors-and-time-limits.md``. All durations are in
seconds and are measured with the monotonic clock (``time.monotonic``), which does not jump
when the system time is corrected.
"""

#: Longest one plugin update (fetch data and draw) may take. Can be changed per plugin.
PLUGIN_UPDATE = 60.0

#: Highest time limit a user may set for one plugin update.
PLUGIN_UPDATE_MAX = 600.0

#: How long a plugin process may take to exit after it has handed over its image.
PLUGIN_EXIT = 5.0

#: Largest config file PaperPi reads. A real config is a few kilobytes.
CONFIG_FILE_BYTES = 256_000

#: Most ``[[plugin]]`` blocks PaperPi uses from one config file.
PLUGIN_BLOCKS = 100

#: Plugin updates that may run at the same time. Plugins update rarely, so 3 is enough, and
#: it keeps memory use low on a Pi 3.
PARALLEL_UPDATES = 3

#: Failed updates in a row after which a plugin is left out for a while.
FAILURES_BEFORE_LEFT_OUT = 3

#: How long a plugin that keeps failing is left out.
LEFT_OUT = 30 * 60.0

#: Default time before a dismissed alert that is still active comes back as a reminder.
ALERT_REMINDER = 60 * 60.0

#: Default longest time an alert is held; then it is dismissed in case the plugin is stuck.
ALERT_MAX_TIME = 24 * 60 * 60.0

#: Plugins that refresh "on the minute" start this many seconds after the minute changes.
ON_THE_MINUTE_DELAY = 1.0

#: Shortest time between two updates of a plugin. Faster is never wanted: a slow screen
#: takes tens of seconds to redraw, and a fast one would flicker.
SHORTEST_REFRESH = 5.0

#: Longest a ``refresh``, ``display_time``, ``alert_reminder`` or ``alert_max_time`` may be.
LONGEST_SETTING = 7 * 24 * 60 * 60.0

#: Longest the scheduler sleeps in one go. It wakes up earlier when something happens.
LONGEST_WAIT = 60 * 60.0

#: Longest wait to connect to a web server (one attempt).
WEB_CONNECT = 10.0

#: Longest one web request may take in total, including the retry and the wait before it.
#: Well under the plugin time limit, so a plugin still has time to draw.
WEB_TOTAL = 30.0

#: Wait before the one retry of a failed web request.
WEB_RETRY_WAIT = 5.0

#: Largest answer PaperPi accepts from a web server, after unpacking. A weather forecast is
#: well under 1 MB. JSON takes several times its size in memory once read, which matters on a
#: Pi Zero 2, so plugins that download large images pass a higher ``max_bytes`` themselves.
WEB_ANSWER_BYTES = 5_000_000

#: How often the scheduler loop reports "still running" to systemd and the health file.
HEALTH_REPORT = 30.0

#: A report older than this counts as "not responding": the watchdog restarts PaperPi.
HEALTH_STALE = 2 * 60.0

#: Longest sending one message to systemd may take.
SYSTEMD_MESSAGE = 5.0

#: Largest health file ``paperpi health`` reads. A report is under 200 bytes.
HEALTH_FILE_BYTES = 1_000
