from pathlib import Path

from os import path


APP_NAME = 'PaperPi'
CONTACT='aaron.ciuffo@gmail.com'
DEVEL_NAME = f'com.txoof.{APP_NAME.lower()}'
VERSION='0.5.4.1 RGB'
URL = 'https://github.com/ txoof/PaperPi'


#CONFIG_FILENAME = f'{APP_NAME.lower()}.ini'
CONFIG_FILENAME = f'{APP_NAME.lower()}_cfg.json'

# reliably identify the current working directory
BASE_DIRECTORY = path.dirname(path.abspath(__file__))

# configuration file format version
CONFIG_VERSION = 2.0

# base configuration
CONFIG_PATH = Path(f'{BASE_DIRECTORY}/config').resolve()
CONFIG_BASE = CONFIG_PATH/CONFIG_FILENAME

# per-user configuration
CONFIG_USER = Path(f'~/.config/{DEVEL_NAME}/{CONFIG_FILENAME}').expanduser().resolve()

# system configuration
CONFIG_SYSTEM = Path(f'/etc/default/{CONFIG_FILENAME}')


# plugins 
PLUGINS = 'plugins'
FONTS = Path(f'{BASE_DIRECTORY}/fonts').resolve()

# required keys that every plugin configuration needs to have
REQ_PLUGIN_KEYS = {
    'layout': 'layout',
    'plugin': None,
    'refresh_rate': 60,
    'min_display_time': 60,
    'max_priority': 2
}


LOGGING_CONFIG = Path(CONFIG_PATH)/'logging.cfg'

VERSION_STRING = f'''
{APP_NAME}
Version: {VERSION}
{URL}
'''

# sleep delay in the update loop in seconds
UPDATE_SLEEP = 5
