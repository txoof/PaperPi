from pathlib import Path

from os import path


APP_NAME = 'PaperPi'
CONTACT='aaron.ciuffo@gmail.com'
DEVEL_NAME = f'com.txoof.{APP_NAME.lower()}'
VERSION='0.6'
URL = 'https://github.com/ txoof/PaperPi'

CONFIG_FILENAME = f'{APP_NAME.lower()}_cfg.json'
CONFIG_VERSION = 2.0
# expected sections in configuration - only these will be processed
CONFIG_SECTIONS = ['config_version', 'main', 'plugins']


# reliably identify the current working directory
BASE_DIRECTORY = path.dirname(path.abspath(__file__))

# base configuration
CONFIG_PATH = Path(f'{BASE_DIRECTORY}/config').resolve()
CONFIG_BASE = CONFIG_PATH/CONFIG_FILENAME

# per-user configuration
CONFIG_USER = Path(f'~/.config/{DEVEL_NAME}/{CONFIG_FILENAME}').expanduser().resolve()

# system configuration
CONFIG_SYSTEM = Path(f'/etc/default/{CONFIG_FILENAME}')


# path to plugins
PLUGINS = 'plugins'
# required keys that every plugin configuration needs to have
REQ_PLUGIN_KEYS = {
  "name": {
    "description": "Human readable plugin identifier",
    "value": ""
  },
  "id": {
      "description": "unique plugin identifier",
      "value": "",
      "hidden": True
  },
  "enabled": {
    "description": "Plugin is enabled and should be displayed",
    "value": True,
    "type": "bool"
  },
  "layout": {
    "description": "Layout to use in displaying plugin output",
    "value": "layout"
  },
  "plugin": {
    "description": "Formal plugin name",
    "value": "None"
  },
  "refresh_rate": {
    "description": "Time in seconds between requests for new data from plugin. This is **not** the display time.",
    "value": 60,
    "type": "int"
  },
  "min_display_time": {
    "description": "Minimum time in seconds plugin should display before a new plugin is displayed",
    "value": 60,
    "type": "int"
  },
  "max_priority": {
    "description": "Maximum priority this plugin should reach. This is best left at the plugin default (typically 2) unless you **really** know what you're doing.",
    "value": 2,
    "type": "int"
  }
}

# path to fonts 
FONTS = Path(f'{BASE_DIRECTORY}/fonts').resolve()

LOGGING_CONFIG = Path(CONFIG_PATH)/'logging.cfg'

VERSION_STRING = f'''
{APP_NAME}
Version: {VERSION}
{URL}
'''

# sleep delay in the update loop in seconds
UPDATE_SLEEP = 5
