#!/usr/bin/env python3
# coding: utf-8






import logging
import shutil
import json
from json import JSONDecodeError
from inspect import getfullargspec
from importlib import import_module



import jsonmerge
import ArgConfigParse

from jsonpath_ng import jsonpath, parse

from library.Plugin import Plugin

import my_constants as constants






logger = logging.getLogger(__name__)






def get_cmd_line_args():
    '''process command line arguments
    
    Returns:
        dict of parsed config values'''
    
    cmd_args = ArgConfigParse.CmdArgs()
    
#     cmd_args.add_argument('--add_config', 
#                          required=False, default=None, nargs=2,
#                          metavar=('plugin', 'user|daemon'),
#                          ignore_none = True,
#                          help='copy sample config to the user or daemon configuration file')    
    
    cmd_args.add_argument('-c', '--config', ignore_none=True, metavar='CONFIG_FILE.ini',
                         type=str, dest='user_config',
                         help='use the specified configuration file')
    
    cmd_args.add_argument('-C', '--compatible', required=False,
                         default=False, action='store_true', 
                         help='list compatible displays and exit')
    
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






def get_config_files(cmd_args=None):
    '''Load json configuration files and merge options destructively
    
    Args:
        cmd_args(`ArgConfigPars.CmdArgs` obj)
        
    Returns:
        json dict of configuration including the following keys:
            config_files: [list of PosixPath objects for each config file used]
            config_version: float representation of config version
            main: json structured dict of dict containing the main configuration
            plugin: [list of json structured dict containing plugin configuration]
            __cmd_line: json structured dict dict of command line options and their values
    '''
    # FIXME - consider removing ArgConfigParse and switching to standard python lib
    

    # all the possible config files
    config_files_dict = {
        'base': constants.CONFIG_BASE,
        'system': constants.CONFIG_SYSTEM,
        'user': constants.CONFIG_USER,
        'cmd_line': None
    }
    
    # always include the base configuration file
    config_files_list = [config_files_dict['base']]

    json_config = {}
    
    json_config['config_files'] = config_files_list
    
    
    try:
        daemon_mode = cmd_args.options.main__daemon
    except AttributeError:
        logging.info(f'daemon mode not set')
        daemon_mode = False
    
    # use the user provided config file if possible
    try:
        config_file_user = cmd_args.options.user_config
    except AttributeError:
        logging.debug('no user specified config file')
        user_config_file = None
    else:
        config_files_dict['cmd_line'] = config_file_user
        
    if config_files_dict['cmd_line']:
        if daemon_mode:
            logging.warning(f'daemon mode was set, but is ignored due to user specified config file')
        config_files_list.append(config_files_dict['cmd_line'])
    elif daemon_mode:
        config_files_list.append(config_files_dict['system'])
    else:
        config_files_list.append(config_files_dict['user'])
        if not config_files_dict['user'].exists():
            try:
                constants.CONFIG_USER.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                msg=f'could not create user configuration directory: {constants.CONFIG_USER.parent}'
                logger.critical(msg)
                do_exit(1, msg)
            try:
                shutil.copy(constants.CONFIG_BASE, constants.CONFIG_USER)
            except Exception as e:
                msg=f'could not copy user configuration file to {constants.CONFIG_USER}'
                logging.critical(1, msg)
                do_exit(1, msg)
            
    logging.debug(f'using config files: {config_files_list}')
        
    for cfg_file in config_files_list:
        logging.info(f'parsing {cfg_file}')
        try:
            with open(cfg_file) as f:
                data = json.load(f)
        except OSError as e:
            logging.warning(f'failed to load config file: {e}')
            data = {}
        except JSONDecodeError as e:
            logging.warning(f'error in JSON file "{f.name}": {e}')
            data = {}
        logging.debug(f'data: {data}')
        json_config = jsonmerge.merge(json_config, data)
    
    # convert command line options into 'key' {'value': value} format
    # this is a little round-about, but keeps all of the merging in one place
    cmd_options_dict = {}
    
    try:
        cmd_nested_dict = cmd_args.nested_opts_dict
    except AttributeError:
        logging.warning('cmd_args: invalid ArgConfigParse.CmdArgs object')
        cmd_nested_dict = None
    
    if isinstance(cmd_nested_dict, dict):
        for section, options in cmd_nested_dict.items():
            cmd_options_dict[section] = {}
            try:
                for key, value in options.items():
                    cmd_options_dict[section][key] = {"value": value}
            except AttributeError as e:
                logging.warning(f'{e}: skipping unparsable command arg: {section}: {options}')
   
    # merge command lines options into main configuration
    try:
        json_config = jsonmerge.merge(json_config, cmd_options_dict)
    except AttributeError:
        logging.debug(f'ArgConfigPars.CmdArgs object was not provided or was malformed')
    
    
    return json_config






def parse_config(json_config=None):
    '''Parse configuration file and return only the values for each dictionary entry
    
    Args:
        json_config(`dict`): json formatted configuration file
        
    Returns:
        dict of dict key/values
        '''
    logging.debug('processing configuration values')    
    parsed_config = {}
    
    if not isinstance(json_config, dict):
        logging.error('no valid JSON data passed')
        return parsed_config

    # match all keys
    key_expression = parse('$[*].*')
    # search specifically for the key 'value'
    value_expression = parse('$.value')


    # process all the expected sections in the config
    for section in constants.CONFIG_SECTIONS:
        logging.debug(f'section: {section}')
        
        # set the jsonpath search string
        jsonpath_expression = parse(f'$.{section}.[*]')
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






def configure_plugin(main_cfg, config, resolution, cache):
    '''configure a single plugin
    
        Args:
        main_cfg(dict): main application configuration
        config(dict): configuration for a single plugin 
        resolution(tuple): X, Y resolution of screen
        cache(obj: Cache): cache object for managing downloads of images
        
    Returns:
        Plugin object'''
    
    def font_path(layout):
        '''add font path to layout'''
        for k, block in layout.items():
            font = block.get('font', None)
            if font:
                font = font.format(constants.FONTS)
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
        layout = font_path(layout)
        plugin_config['layout'] = layout
    except KeyError as e:
        msg = 'no module specified; skipping plugin'
        logger.warning(msg)
        exceptions.append(msg)
#         continue
    except ModuleNotFoundError as e:
        msg = f'error: {e} while loading plugin module; skipping plugin'
        logger.warning(msg)
        exceptions.append(msg)
#         continue
    except AttributeError as e:
        msg = f'could not find layout "{plugin_config["layout"]}" in {plugin_config["name"]}; skipping plugin'
        logger.warning(msg)
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
        logger.warning(msg)
        exceptions.append(msg)
        my_plugin = None

        
    if len(exceptions) > 0:
        logging.error(f'errors encountered while creating plugin:')
        for idx, e in enumerate(exceptions):
            logging.error(f'     {idx}: {e}')

            
    return my_plugin       




