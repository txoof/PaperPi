from pathlib import Path

APP_NAME = 'PaperPi'
CONTACT='aaron.ciuffo@gmail.com'
DEVEL_NAME = f'com.txoof.{APP_NAME.lower()}'
VERSION='0.3.0.0'
URL = 'https://github.com/ txoof/epd_display'


CONFIG_FILENAME = f'{APP_NAME.lower()}.ini'

# base configuration
CONFIG_PATH = Path('./config')
CONFIG_BASE = CONFIG_PATH/CONFIG_FILENAME

# per-user configuration
CONFIG_USER = Path(f'~/.config/{DEVEL_NAME}/{CONFIG_FILENAME}').expanduser().resolve()

# system configuration
CONFIG_SYSTEM = Path(f'/etc/default/{CONFIG_FILENAME}')


# plugins 
PLUGINS = 'plugins'
FONTS = Path('./fonts').resolve()
