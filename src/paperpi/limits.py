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
