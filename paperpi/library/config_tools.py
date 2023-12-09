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

# +
import logging
from pathlib import Path
import json
from importlib import import_module
from inspect import getfullargspec

from json import JSONDecodeError

import ArgConfigParse
import jsonmerge
from jsonmerge.exceptions import JSONMergeError
import jsonpath_ng as jsonpath

# manage relative imports in Jupyter/shell
try:
    from .Plugin import *
except ImportError:
    import Plugin
# -



## testing
import sys
sys.path.append('../')
import my_constants as constants


def get_cmd_line_args():
    '''process command line arguments
    
    Returns:
        dict of parsed config values'''
    
    cmd_args = ArgConfigParse.CmdArgs()
    
    cmd_args.add_argument('-c', '--configfile', ignore_none=True, metavar='CONFIG_FILE.json',
                         type=str, dest='user_config',
                         help='use the specified configuration file')
    
    cmd_args.add_argument('-C', '--compatible', required=False,
                         default=False, action='store_true', 
                         help='list compatible displays and exit')

    cmd_args.add_argument('-i', '--interactive_configure', required=False, default=False,
                          action='store_true',
                          help='start interactive configuration of PaperPi')
    
    cmd_args.add_argument('-l', '--log_level', ignore_none=True, metavar='LOG_LEVEL',
                         type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                         dest='main__log_level', help='change the log output level')
    
    cmd_args.add_argument('-d', '--daemon', required=False, default=False,
                         dest='main__daemon', action='store_true', 
                         help='run in daemon mode (ignore user configuration if found)')    
    
    cmd_args.add_argument('--list_plugins', required=False,
                         default=False, action='store_true', 
                         help='list all available plugins')

    cmd_args.add_argument('--plugin_info', metavar='[plugin|plugin.function]',
                         required=False, default=None,
                         ignore_none=True,
                         help='get information for plugins and user-facing functions provided by a plugin')   
    
    cmd_args.add_argument('--run_plugin_func',
                         required=False, default=None, nargs='+',
                         metavar=('plugin.function', 'optional_arg1 arg2 argN'),
                         ignore_none=True,
                         help='run a user-facing function for a plugin')
    
    cmd_args.add_argument('-V', '--version', required=False, default=False, ignore_false=True,
                          action='store_true',
                          help='display version and exit')

    
    cmd_args.parse_args()    

    return cmd_args


def load_config(config_file, config_base, plugin_keys={}, cmd_args=None):
    '''Load JSON configuration files and merge main options destructively

    Merge the master (base) configuration file with user or system configuration file.
    The base config file provides default and missing values. The user/system file overwrites
    values from the base. 

    Add any missing, required plugin keys from each plugin configuration. Any missing key will be 
    added without changing existing values.

    Args:
        config_file(str or Path): file to use
        config_base(str or Path): file with default configuration options
        plugin_keys(dict): keys that are required for plugins
        cmd_args(`ArgConfigPars.CmdArgs` obj)

    Returns:
        json dict of configuration including the following keys:
            config_files: [list of PosixPath objects for each config file used]
            config_version: float representation of config version
            main: json structured dict of dict containing the main configuration
            plugin: dict of json structured dict containing plugin configuration
            __cmd_line: json structured dict dict of command line options and their values
    '''

    json_config = {
        'config_files': [],
    }
    config_file_list = [Path(config_base).expanduser().absolute(), 
                        Path(config_file).expanduser().absolute()]

    # load each config file, upserting destructively favoring the last config file in the list
    # this ensures that any missing keys in the config file are added in
    for config_file in config_file_list:
        if not config_file.exists():
            raise FileNotFoundError(f'config file "{config_file}" does not exist')
        
        try:
            with open(config_file) as f:
                data = json.load(f)
        except OSError as e:
            msg = (f'failed to load config file "{config_file}": {e}')
            raise OSError(msg)
        except JSONDecodeError as e:
            msg = (f'failed to load config file "{config_file}": {e}')
            raise JSONDecodeError(msg)

        try:
            json_config = jsonmerge.merge(json_config, data)
        except Exception as e:
            raise Exception(f'fatal error while merging data from "{config_file}": {e}')

    json_config['config_files'] = config_file_list

    # prepare the command line args as a dict
    cmd_options_dict = {}
    try:
        cmd_nested_dict = cmd_args.nested_opts_dict
    except AttributeError:
        logging.info('cmd_args: invalid ArgConfigParse.CmdArgs object; cannot merge command line arguments')
        cmd_nested_dict = None

    # process the dict
    if cmd_nested_dict:
        for section, options in cmd_nested_dict.items():
            cmd_options_dict[section] = {}
            try:
                for key, value in options.items():
                    cmd_options_dict[section][key] = {"value": value}
            except AttributeError as e:
                logging.warning(f'skiping unparsable command arg: {section} = {options}')
    else: 
        cmd_options_dict = {}

    # add the dict to the config json
    try:
        json_config = jsonmerge.merge(json_config, cmd_options_dict)
    except AttributeError:
        logging.warning(f'ArgConfigPars.CmdArgs object was not provided or was malformed')


    # upsert default plugin values from plugins_base dictionary
    # this ensures that any missing keys are added to the plugin configurations
    plugins = json_config.get('plugins', [])
    logging.info(f'processing {len(plugins)} plugins')
    for idx, plugin in enumerate(plugins):
        try:
            plugin = jsonmerge.merge(plugin_keys, plugin)
        except JSONMergeError as e:
            logging.warning(f'Error in json_config["plugins"] section index #{idx}: {e}')
            logging.warning(f'skipping plugin: {plugin.get("name", "NO NAME AVAILABLE")} - {plugin.get("id", "INVALID HASH")}')
            continue
        # update plugin
        plugins[idx] = plugin
    json_config['plugins'] = plugins
    
    return json_config


def parse_config(json_config, config_sections):
    '''parse configuration JSON and return only the `value` for each entry
    
    Args:
        json_config(`dict`): json formatted configuration file
        config_sections(`list`): sections to process
        
    Retruns:
        dict of dict key/value'''

    parsed_config = {}
    
    # match all keys
    key_expression = jsonpath.parse('$[*].*')
    # search specifically for the key 'value'
    value_expression = jsonpath.parse('$.value')

    # process all the expected config_sections
    for section in config_sections:
        logging.debug(f'parsing config section: {section}')

        # set the jsonpath search string
        jsonpath_expression = jsonpath.parse(f'$.{section}.[*]')
        # find all matching
        try:
            section_vals = [match.value for match in jsonpath_expression.find(json_config)]
        except TypeError:
            # pass over key: value sections that have no depth (e.g. config_version: 2.0)
            parsed_config[section] = json_config[section]
            continue
        # create a list of extracted dictionary values
        extracted_values = []

        for each in section_vals:
            value_dict = {}
            
            # process all the matched values extracted from the section
            for match in key_expression.find(each):
                # further process dictionaries to find the `value` key
                if isinstance(match.value, dict):
                    my_match = value_expression.find(match.value)[0].value
                else:
                    # else take the flat value
                    my_match = match.value
                    
                value_dict[str(match.path)] = my_match
            extracted_values.append(value_dict)
            
        # flatten out the main section into a dict
        if section == 'main':
            parsed_config[section] = extracted_values[0]
        else:
            parsed_config[section] = extracted_values
    
    return parsed_config


def configure_plugin(main_cfg, config, resolution, cache, font_path):
    '''configure a single plugin module in memory
    
        Args:
        main_cfg(dict): main application configuration
        config(dict): configuration for a single plugin 
        resolution(tuple): X, Y resolution of screen
        cache(obj: Cache): cache object for managing downloads of images
        
    Returns:
        Plugin object'''
    
    def get_font_path(layout):
        '''add font path to layout'''
        for k, block in layout.items():
            font = block.get('font', None)
            if font:
                font = font.format(font_path)
                block['font'] = font
        return layout    
    
    logging.info(f'     >>>configuring {config.get("name", "UNKNOWN")} - {config.get("plugin", "UNKNOWN")}<<<')
    
    
    # try to guess the screen mode and bit depth based on the display_type
    if not 'force_onebit' in main_cfg.keys():
        logging.info('guessing `screen_mode` and bit-depth based on display type')
        if main_cfg.get('display_type', None) == 'HD':
            main_cfg['force_onebit'] = False
            main_cfg['screen_mode'] = 'L'
            logging.info(f'this looks to be an HD screen: screen_mode: {main_cfg["screen_mode"]}, force_onebit: {main_cfg["force_onebit"]}')
    
    
    logging.debug(f'main_cfg: {main_cfg}')
    logging.debug(f'plugin config: {config}')
    logging.debug(f'resolution: {resolution}')
    # get the expected key-word args from the Plugin() spec
    spec_kwargs = getfullargspec(Plugin).args
    try:
        spec_kwargs.remove('self')
    except ValueError as e:
        logging.warning(f'excpected to find kwarg `self` in kwargs: {e}')
    
    logging.debug(f'Plugin() spec: {spec_kwargs}')    
    
    
    plugin_config = {}
    plugin_kwargs = {}
    plugin_module = config.get('plugin', None)
    exceptions = []

    
    for key, value in config.items():
        if key in spec_kwargs:
            plugin_config[key] = value
        else:
            plugin_kwargs[key] = value

    # fill in the remaining kwargs
    plugin_config['resolution'] = resolution
    plugin_config['cache'] = cache
    plugin_config['force_onebit'] = main_cfg.get('force_onebit', True)
    plugin_config['screen_mode'] = main_cfg.get('screen_mode', '1')
    plugin_config['plugin_timeout'] = main_cfg.get('plugin_timeout', 35)
    plugin_config['name'] = config.get('name', 'NO NAME')
    
    

    plugin_config['config'] = plugin_kwargs
    logging.debug(f'plugin_config: {plugin_config}')
        
    try:
        module = import_module(f'{constants.PLUGINS}.{plugin_module}')
        plugin_config['update_function'] = module.update_function
        layout = getattr(module.layout, plugin_config.get('layout', 'layout'))
        layout = get_font_path(layout)
        plugin_config['layout'] = layout
    except KeyError as e:
        msg = 'no module specified; skipping plugin'
        logging.warning(msg)
        exceptions.append(msg)
#         continue
    except ModuleNotFoundError as e:
        msg = f'error: {e} while loading plugin module; skipping plugin'
        logging.warning(msg)
        exceptions.append(msg)
#         continue
    except AttributeError as e:
        msg = f'could not find layout "{plugin_config["layout"]}" in {plugin_config["name"]}; skipping plugin'
        logging.warning(msg)
        exceptions.append(msg)
        

    try:
        logging.debug(f'creating plugin {plugin_config["name"]}')
        my_plugin = Plugin(**plugin_config)
    except TypeError as e:
        msg = f'failed to create plugin "{plugin_config["name"]}": {e}'
        logging.warning('msg')
        exceptions.append(msg)
        my_plugin = None
    
    try:
        logging.debug('updating plugin')
        my_plugin.update()
    except (AttributeError, TypeError) as e:
        msg = f'ignoring plugin "{plugin_config["name"]}" due to errors: {e}'
        logging.warning(msg)
        exceptions.append(msg)
        my_plugin = None

        
    if len(exceptions) > 0:
        logging.error(f'errors encountered while creating plugin:')
        for idx, e in enumerate(exceptions):
            logging.error(f'     {idx}: {e}')

            
    return my_plugin           

# !jupytext paperpi.ipynb --update-metadata '{"jupytext":{"executable":"/usr/bin/env python"}}' --to py
