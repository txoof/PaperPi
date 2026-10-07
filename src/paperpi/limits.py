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

#: Longest reading and checking the config file may take when it is loaded again (reload).
CONFIG_RELOAD = 10.0

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

#: At start, the splash screen (``[display] splash``) is shown at least this long.
SPLASH_TIME = 60.0

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

#: How often the health values are also written to the log, so they can be compared over
#: weeks (the health file only holds the newest).
HEALTH_LOG = 60 * 60.0

#: Longest sending one message to systemd may take.
SYSTEMD_MESSAGE = 5.0

#: Largest health file ``paperpi health`` reads. A report is under 200 bytes.
HEALTH_FILE_BYTES = 1_000

#: Longest one screen write may take before its redraw time is measured.
SCREEN_FIRST = 2 * 60.0

#: The same for colour screens, which take much longer to redraw.
SCREEN_FIRST_COLOR = 5 * 60.0

#: Once measured, a screen write may take this many times the last redraw ...
SCREEN_REDRAW_FACTOR = 3

#: ... but never less than this ...
SCREEN_SHORTEST = 30.0

#: ... or more than this.
SCREEN_LONGEST = 5 * 60.0

#: Failed screen writes in a row after which the screen is reset (new helper process).
SCREEN_FAILURES_BEFORE_RESET = 3

#: Resets that did not help, after which screen writes pause.
SCREEN_RESETS_BEFORE_REST = 3

#: While screen writes pause, the first wait before the next try. Each failed try doubles
#: the wait, up to :data:`SCREEN_REST_LONGEST`. A config change or a restart starts again here.
SCREEN_REST = 10 * 60.0

#: The longest wait between two tries while screen writes pause.
SCREEN_REST_LONGEST = 6 * 60 * 60.0

#: When PaperPi stops: how long to wait for a running screen write before clearing the
#: screen, and the longest the clear may take. A stop must stay well under systemd's stop
#: time limit (90 s by default).
SCREEN_EXIT_WAIT = 2.0
SCREEN_EXIT_CLEAR = 30.0

#: How long a screen helper process may take to end after it was told to (or killed).
SCREEN_STOP = 5.0

#: How long closing the screen may take when PaperPi stops.
SCREEN_CLOSE = 30.0

#: PaperPi exits because of a stuck screen helper process at most this often.
SCREEN_STUCK_EXIT = 60 * 60.0

#: Default size limit of a plugin's storage folder, in megabytes (1 MB = 1,000,000 bytes,
#: as everywhere in PaperPi). A plugin may suggest its own; the ``storage_mb`` setting wins.
STORAGE_MB = 500

#: Highest ``storage_mb`` a user may set (1 TB).
STORAGE_MB_MAX = 1_000_000

#: Default age in days after which a plugin's files are removed (0 = keep them).
STORAGE_DAYS = 30

#: Highest ``storage_days`` a user may set (100 years).
STORAGE_DAYS_MAX = 36_500

#: PaperPi keeps at least this much free on the disk that holds its files, in megabytes.
#: Below it, plugins are told the disk is low, so they don't save more.
FREE_DISK_MB = 2_000

#: Once the disk is low, it counts as fine again only with this much more free, so a value
#: around the limit doesn't give a pair of log lines at every update. In megabytes.
FREE_DISK_GAP_MB = 100

#: Longest cleaning up one plugin's storage folder may take, in seconds.
STORAGE_CLEAN = 10.0

#: While the disk stays low, the warning is repeated at most this often, in seconds.
LOW_DISK_REPEAT = 10 * 60.0

#: A plugin's storage folder is cleaned after an update at most this often, in seconds, so a
#: plugin that updates every minute doesn't read a large folder every minute.
STORAGE_CLEAN_EVERY = 5 * 60.0

#: Most files PaperPi looks at in one plugin's storage folder per clean-up; keeps the
#: memory a clean-up uses small (a few tens of megabytes at most).
STORAGE_MAX_FILES = 100_000

#: Longest cleaning up all plugin folders at start may take in all, in seconds.
STORAGE_CLEAN_START = 30.0
