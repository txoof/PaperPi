# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.0rc0
#   kernelspec:
#     display_name: venv_paperpi-9876705927
#     language: python
#     name: venv_paperpi-9876705927
# ---

# %load_ext autoreload
# %autoreload 2

import logging
import logging.config
import sys
import shutil
from itertools import cycle
from inspect import getfullargspec
from importlib import import_module
from pathlib import Path
from distutils.util import strtobool
from time import sleep
from configparser import DuplicateSectionError
from configparser import Error as ConfigParserError
from json import JSONDecodeError

# +

import ArgConfigParse
from epdlib import Screen
from epdlib.Screen import Update
from epdlib.Screen import ScreenError
# -

from library.Plugin import Plugin
from library.CacheFiles import CacheFiles
from library.InterruptHandler import InterruptHandler
from library import get_help
from library import run_module
from library import config_tools
import my_constants as constants

# load the logging configuration
logging.config.fileConfig(constants.LOGGING_CONFIG)
logger = logging.getLogger(__name__)


def do_exit(status=0, message=None, **kwargs):
    '''exit with optional message
    Args:
        status(int): integers > 0 exit with optional message
        message(str): optional message to print'''
    if message:
        if status > 0:
            logger.error(f'failure caused exit: {message}')
        border = '\n'+'#'*70 + '\n'
        message = border + message + border + '\n***Exiting***'
        print(message)
        
    try:
        sys.exit(status)
    except Exception as e:
        pass


def clean_up(cache=None, screen=None, no_wipe=False):
    '''clean up the screen and cache
    
    Args:
        cache(cache obj): cache object to use for cleanup up
        screen(Screen obj): screen to clear
        no_wipe(bool): True - leave last image on screen; False - wipe screen
    '''
    logging.info('cleaning up')
    try:
        logging.debug('clearing cache')
        cache.cleanup()
    except AttributeError:
        logging.debug('no cache passed, skipping')
    
    if no_wipe:
        logging.info('not clearing screen due to [main][no_wipe]=True')
    else:
        try:
            logging.debug('clearing screen')
            screen.clearEPD()
        except AttributeError:
            logging.debug('no screen passed, skipping cleanup')
        
    logging.debug('cleanup completed')
    return    


def build_plugins_list(config, resolution, cache):
    '''Build a dictionary of configured plugin objects
    
    Args:
        config(dict): configuration dictionary 
        resolution(tuple): X, Y resolution of screen
        cache(obj: Cache): cache object for managing downloads of images
        
    Returns:
        dict of Plugin'''
    
    def font_path(layout):
        '''add font path to layout'''
        for k, block in layout.items():
            font = block.get('font', None)
            if font:
                font = font.format(constants.FONTS)
                block['font'] = font
        return layout
    
    # get the expected key-word args from the Plugin() spec
    spec_kwargs = getfullargspec(Plugin).args

    plugins = []
    
    for section, values in config.items():
        if section.startswith('Plugin:'):
            logger.info(f'[[ {section} ]]')
            
            plugin_config = {}
            # add all the spec_kwargs from the config
            plugin_kwargs = {}
            for key, val in values.items():
                if key in spec_kwargs:
                    plugin_config[key] = val
                else:
                    # add everything that is not one of the spec_kwargs to this dict
                    plugin_kwargs[key] = val

            # populate the kwargs plugin_config dict that will be passed to the Plugin() object
            plugin_config['name'] = section
            plugin_config['resolution'] = resolution
            plugin_config['config'] = plugin_kwargs
            plugin_config['cache'] = cache
            plugin_config['force_onebit'] = config['main']['force_onebit']
            plugin_config['screen_mode'] = config['main']['screen_mode']
            plugin_config['plugin_timeout'] = config['main'].get('plugin_timeout', 35)
            # force layout to one-bit mode for non-HD screens
#             if not config['main'].get('display_type') == 'HD':
#                 plugin_config['force_onebit'] = True

            logging.debug(f'plugin_config: {plugin_config}')
    
            try:
                module = import_module(f'{constants.PLUGINS}.{values["plugin"]}')
                plugin_config['update_function'] = module.update_function
                layout = getattr(module.layout, values['layout'])
                layout = font_path(layout)
                plugin_config['layout'] = layout
            except KeyError as e:
                logger.info('no module specified; skipping update_function and layout')
                continue
            except ModuleNotFoundError as e:
                logger.warning(f'error: {e} while loading module {constants.PLUGINS}.{values["plugin"]}')
                logger.warning(f'skipping plugin')
                continue
            except AttributeError as e:
                logger.warning(f'could not find layout "{plugin_config["layout"]}" in {plugin_config["name"]}')
                logger.warning(f'skipping plugin')
                continue
            my_plugin = Plugin(**plugin_config)
            try:
                my_plugin.update()
            except AttributeError as e:
                logger.warning(f'ignoring plugin {my_plugin.name} due to missing update_function')
                logger.warning(f'plugin threw error: {e}')
                continue    
            logger.info(f'appending plugin {my_plugin.name}')
            
    
            plugins.append(my_plugin)
            
    
    return plugins


def setup_splash(config, resolution):
    if config['main'].get('splash', False):
        logger.debug('displaying splash screen')
        from plugins.splash_screen import splash_screen
        splash_config = {
            'name': 'Splash Screen',
            'layout': splash_screen.layout.layout,
            'update_function': splash_screen.update_function,
            'resolution': resolution,
        }
        splash = Plugin(**splash_config)
        splash.update(app_name=constants.APP_NAME, 
                      version=constants.VERSION, 
                      url=constants.URL)
    else:
        logger.debug('skipping splash screen')
        splash = False
    
    return splash


def setup_display(config):
    def ret_obj(obj=None, status=0, message=None):
        return{'obj': obj, 'status': status, 'message': message} 
    
    keyError_fmt = 'configuration KeyError: section[{}], key: {}'    
    
    moduleNotFoundError_fmt = 'could not load epd module {} -- error: {}'
    
    epd = config['main'].get('display_type', None)
    vcom = config['main'].get('vcom', None)
    mirror = config['main'].get('mirror', False)
        
    try:
        screen = Screen(epd=epd, vcom=vcom)
        # this may not be necessary; most writes necessarily involve wiping the screen
#         screen.clearEPD()
    except ScreenError as e:
        logging.critical('Error loading epd from configuration')
        return_val = ret_obj(None, 1, moduleNotFoundError_fmt.format(epd, e))
        return return_val
    except PermissionError as e:
        logging.critical(f'Error initializing EPD: {e}')
        logging.critical(f'The user executing {constants.app_name} does not have access to the SPI device.')
        return_val = ret_obj(None, 1, 'This user does not have access to the SPI group\nThis can typically be resolved by running:\n$ sudo groupadd <username> spi')
        return return_val
    except FileNotFoundError as e:
        logging.critical(f'Error initializing EPD: {e}')
        logging.critical(f'It appears that SPI is not enabled on this Pi. Try:')
        logging.critical(f'   $ sudo raspi-config nonint do_spi 0')
        return_val = ret_obj(None, 1, moduleNotFoundError_fmt.format(epd, e))
        return return_val
    
    
    try:
        screen.rotation = config['main'].get('rotation', 0)
    except (TypeError, ValueError) as e:
        logger.error('invalid screen rotation [main][rotation] - acceptable values are (0, 90, -90, 180)')
        return_val = ret_obj(None, 1, keyError_format.format('main', 'rotation'))
        return return_val
    
    try:
        screen.mirror = config['main'].get('mirror', False)
    except (TypeError, ValueError) as e:
        logger.error('invalid mirror value [main][mirror] - acceptable values are: (True, False)')
        return_val = ret_obj(None, 1, keyError_format.format('main', 'rotation'))
        return return_val
            
    
    return ret_obj(obj=screen)    


# +
def update_loop(plugins, screen, max_refresh=5):
    def _update_plugins(force_update=False):
        '''private function for updating plugins'''
        s = ' '*5
        logger.info(f'>>__________UPDATING PLUGINS__________<<')
        logger.debug(f'{len(plugins)} total plugins available')
        my_priority_list = [2**16]
        for plugin in plugins:
            logger.info(f'{"#"*10}{plugin.name}{"#"*10}')
            if force_update:
                logger.info(f'{s}forcing update')
                plugin.force_update()
            else:
                plugin.update()

            logger.info(f'{s}PRIORITY: {plugin.priority} of max {plugin.max_priority}')
            my_priority_list.append(plugin.priority)

            logger.debug(f'{s}DATA: {len(plugin.data)} elements')
            logger.debug(f'{s}IMAGE: {plugin.image}')

        return my_priority_list
    
    logger.debug(f'max refresh before total wipe: {max_refresh}')
    
    logger.info(f'starting update loop with {len(plugins)} plugins')
    logger.debug(f'plugins: {plugins}')
    
    exit_code = 1
    priority_list = []
    priority_list = _update_plugins(force_update=True)
    # cycle to next item in list
    plugin_cycle = cycle(plugins)
    current_plugin = next(plugin_cycle)
    refresh_count = 0
    current_hash = ''
    # lower numbers are of greater importance
    max_priority = min(priority_list)
    last_priority = max_priority
    
    # display the first plugin with appropriately priority
    for i in range(0, len(plugins)):
        if current_plugin.priority <= max_priority:
            current_timer = Update()
            current_plugin_active = True
            logger.info(f'DISPLAY PLUGIUN: {current_plugin.name}')
            break
        else:
            current_plugin = next(plugin_cycle)
            
    interrupt_handler = InterruptHandler()
    while not interrupt_handler.kill_now:
        logger.info(f'{current_plugin.name}--display for: {current_plugin.min_display_time-current_timer.last_updated:.1f} of {current_plugin.min_display_time} seconds')
        
        priority_list = _update_plugins()
        last_priority = max_priority
        max_priority = min(priority_list)
        
        

        
        # if the timer has expired or the priority has increased, display a different plugin
        if current_timer.last_updated > current_plugin.min_display_time:
            logger.info(f'display time for {current_plugin} elapsed, cycling to next')
            current_plugin_active = False
        
        if max_priority > last_priority:
            logger.info(f'priority level increased; cycling to higher priority plugin')
            current_plugin_active = False
            
        
        if not current_plugin_active:
            logger.debug(f'{current_plugin} inactive; searching for next active plugin')
            for attempt in range(0, len(plugins)):
                current_plugin = next(plugin_cycle)
                logger.debug(f'checking plugin: {current_plugin}')
                if current_plugin.priority <= max_priority:
                    current_plugin_active = True
                    logger.debug(f'using plugin: {current_plugin}' )
                    current_timer.update()
                    break
    
        # check data-hash for plugin; only update screen if hash has changed to avoid uneccessary updates
        if current_hash != current_plugin.hash:
            logger.debug('data update required')
            current_hash = current_plugin.hash
            
            if refresh_count >= max_refresh-1 and screen.HD:
                logger.debug(f'{refresh_count} reached maximum of {max_refresh}')
                refresh_count = 0
                screen.clearEPD()
                
            try:
                screen.writeEPD(current_plugin.image)
            except FileNotFoundError as e:
                msg = 'SPI does not appear to be enabled. Paperpi requires SPI access'
                logging.critical(msg)
                do_exit(1, msg)
            except ScreenError as e:
                logging.critical(f'{current_plugin.name} returned invalid image data; screen update skipped')
                logging.debug(f'DATA: {current_plugin.data}')
                logging.debug(f'IMAGE: {current_plugin.image}')
                logging.debug(f'IMAGE STRING: {str(current_plugin.image)}')
                current_plugin_active = False
        else:
            logging.debug('plugin data not refreshed, skipping screen update')

            
        
        sleep(constants.UPDATE_SLEEP)
        
    
    
# -

def main():
    cmd_args = config_tools.get_cmd_line_args()

    # set the default error logging level
    if not cmd_args.options.main__log_level:
        logging.root.setLevel('ERROR')

    # bail out and print help when there are unknown args
    if hasattr(cmd_args, 'unknown'):
        msg = f'Unknown command line arguments: {cmd_args.unknown}\n\n'
        cmd_args.parser.print_help()
        do_exit (1, msg)

    if cmd_args.options.user_config and cmd_args.options.main__daemon:
        msg = 'Both daemon and user specified config files specified.'
        cmd_args.parser.print_help()
        do_exit(1, msg)

    # set the config file
    if cmd_args.options.main__daemon:
        daemon_mode = True
        config_file = Path(constants.CONFIG_SYSTEM)
    elif cmd_args.options.user_config:
        config_file = Path(cmd_args.options.user_config).expanduser().absolute()
    else:
        daemon_mode = False
        config_file = Path(constants.CONFIG_USER).expanduser().absolute()

    logger.info(f'configuring {constants.APP_NAME} using config file: {config_file}')
    
    try:
        config_json = config_tools.load_config(config_file=config_file,
                                  config_base=constants.CONFIG_BASE,
                                  plugin_keys=constants.REQ_PLUGIN_KEYS,
                                  cmd_args=cmd_args)
    except (PermissionError, OSError, JSONDecodeError) as e:
        msg = f'Fatal error when loading configuration files: {e}'
        logger.error(msg)
        do_exit(1, msg)
    except Exception as e:
        msg = f'an unexpected error occured while loading configuration files: {e}'
        logger.error(msg)
        do_exit(1, msg)

    config = config_tools.parse_config(json_config=config_json, config_sections=constants.CONFIG_SECTIONS)

    # set the log level
    log_level = config.get('main', {}).get('log_level', 'WARNING')
    logger.setLevel(log_level)
    logging.root.setLevel(log_level)

    if not config:
        msg = f'fatal error parsing configuration files ({config_file}). See the logs'
        logger.error(msg)
        do_exit(1, msg)

    if cmd_args.options.version:
        print(constants.VERSION_STRING)
        return

    if cmd_args.options.compatible:
        print('Compatible WaveShare Displays:\n')
        Screen.list_compatible()
        return
    
    if cmd_args.options.list_plugins:
        print('not implemented')
        # get_help.get_help(plugin_path=Path(constants.BASE_DIRECTORY)/'plugins')
        return
    
    if cmd_args.options.plugin_info:
        get_help(cmd_args.options.plugin_info)
        return
    
    if cmd_args.options.run_plugin_func:
        run_module.run_module(cmd_args.options.run_plugin_func)
        return

    
    if cmd_args.options.interactive_configure:
        # interactive_config.main()
        print('not implemented')
        return


    logger.info(f'********** {constants.APP_NAME} {constants.VERSION} Starting **********')
    if cmd_args.options.main__daemon:
        logger.info(f'{constants.APP_NAME} is running in daemon mode')
    else:
        logger.info(f'{constants.APP_NAME} is running in on-demand mode')

    # print entire configuration
    logger.debug(f'configuration:\n{config}\n\n')

    screen_return = setup_display(config)
    
    if screen_return.get('obj', False):
        screen = screen_return['obj']
    else:
        clean_up(None, None)
        logger.error(f'error setting up screen: config files used: {config_files.config_files}')
        do_exit(**screen_return)
    
    # # force to one-bit mode for non HD and non-color screens
    # if screen.mode == '1' or not config.get('main', {}).get('color', True):
    #     one_bit = True
    # else:
    #     one_bit = False
            
    # config['main']['force_onebit'] = one_bit
    # config['main']['screen_mode'] = screen.mode
    
    logging.info(f'screen configured: mode: {config.get("main", {}).get("screen_mode", "error getting mode")}, one_bit: {config.get("main", {}).get("force_onebit", "error getting one_bit status")}')
            
    splash = setup_splash(config, screen.resolution)
    
    if splash:
        splash_kwargs = {
            'app_name': constants.APP_NAME,
            'version': constants.VERSION,
            'url': constants.URL            
        }
        splash.force_update(**splash_kwargs)
        logger.debug('display splash screen')
        try:
            screen.writeEPD(splash.image)
        except FileNotFoundError as e:
            msg = 'SPI does not appear to be enabled. Paperpi requires SPI access'
            logging.critical(msg)
            do_exit(1, msg)            
        except ScreenError as e:
            logging.critical(f'Could not write to EPD: {e}')
            
    cache = CacheFiles(path_prefix=constants.APP_NAME)
    
    # get a list of all the plugins
    plugin_list = config.get('plugins', [])
    
    # always append the default plugin and ensure there is at least one plugin in the list
    try:
        plugin_list.append({'name': 'Default Plugin',
                           'plugin': 'default'})
    except (AttributeError) as e:
        msg = f'error loading plugins: {e}'
        logging.error(msg)
        do_exit(1, msg)
    
    # list of plugin objects
    plugins = []
    
    if not isinstance(plugin_list, list):
        msg = f'missing or malformed "plugin" section in config file'
        logging.error(msg)
        do_exit(1, msg)
    
    for item in plugin_list:
        if not isinstance(item, dict):
            logging.error(f'bad plugin config found in {item}; skipping and attempting to recover')
            logging.error(f'expected `dict` found: {type(item)}')
            continue 
        
        if item.get('enabled', True) == False:
            logging.info(f'Plugin: {item.get("name", "NO NAME")} is disabled, skipping')
            continue
        
        p = config_tools.configure_plugin(main_cfg=config.get('main', {}), 
                                         config=item, 
                                         resolution=screen.resolution, 
                                         cache=cache,
                                         font_path=constants.FONTS)
        if p:
            plugins.append(p)
        else:
            logging.error(f'failed to create plugin due to previous errors')
    

    if not plugins:
        msg = 'no plugins are configured; see previous errors. Exiting'
        do_exit(1, msg)
    
    exit_code = update_loop(plugins=plugins, screen=screen, max_refresh=config['main'].get('max_refresh', 5))
    
    clean_up(cache=cache, screen=screen, no_wipe=config['main'].get('no_wipe', False))
    
    return  exit_code

if __name__ == "__main__":
    # remove jupyter runtime junk for testing in Jupyter
    try:
        i = sys.argv.index('-f')
        t = sys.argv[:i] + sys.argv[i+2:]
        sys.argv = t
    except ValueError:
        pass
    exit_code = main()
    sys.exit(exit_code)

# !jupyter-nbconvert --to python --template python_clean paperpi.ipynb
