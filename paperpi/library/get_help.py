#!/usr/bin/env python3
# coding: utf-8




import importlib
import inspect
from pathlib import Path
import textwrap
import logging






logger = logging.getLogger(__name__)






class _multi_line_string():
    '''object that produces a wrapped string
    
    Args:
        s(str): string
        colunmns(int): number of colunns to wrap at
        
    Properties:
        string(str): original string
        string_list(list of str): word-wrapped string as a list
        wrapped_string(str): word-wrapped string with newline chars'''
    
    
    def __init__(self, s=' ', columns=65):
        self._string = []
        self.string = s
        self.columns=columns
    
    def __str__(self):
        return self.string
        
    @property
    def string(self):
        return '\n'.join(self._string)
            
    @string.setter
    def string(self, s):
        self._string.append(s)
    
    @property
    def string_list(self):
        return self._string
    
    @property
    def wrapped_string(self):
        return '\n'.join(textwrap.wrap(' '.join(self._string), self.columns)).lstrip()






def _get_modules(root='./plugins/'):
    '''get a list of modules contained within the path specified
    
    Args:
        root(str): path to search for modules
    
    Returns:
        list of str: list modules found within the root'''
    module_list = []
    p = Path(root).resolve()
    for i in p.glob('*'):
        if i.is_dir() and i.name[0] not in ('_', '.'):
            module_list.append(i.name)
    return module_list






def _get_module_docs(module):
    '''return only user-facing docstrings that contain "%U"
        
    Args:
        module: python module
        
    Returns:
        string containing docstrings
    '''
    mls = _multi_line_string()
    members = inspect.getmembers(module)
    for member in members:
        if inspect.isfunction(member[1]):
            # skip entries that don't have a docstring
            if not member[1].__doc__:
                continue
            # skip docstrings functions not tagged with '%U' as last characters
            if member[1].__doc__.endswith('%U'):
                mls.string = f'FUNCTION: {member[0]}'
                mls.string = member[1].__doc__.replace('%U', '')
                mls.string = '_'*75
                mls.string = ' '
            else:
                continue

    return mls.string






def _get_layouts(module):
    '''get layout names provided by a plugin
    
    Args:
        module: python module
        
    Returns:
        string containing layout names'''
    layout_ignore = ['os', 'dir_path']
    mls = _multi_line_string()
    try:
        my_dir = dir(getattr(module, 'layout'))
    except AttributeError:
        my_dir =[f'NO LAYOUTS FOUND IN {module.__name__}']

    mls.string = 'LAYOUTS AVAILABLE:'
    for item in my_dir:
        if not item.startswith('__') and not item in layout_ignore:
            mls.string = f'  {item}'
    return mls.string






def _get_data_keys(module):
    '''return data keys provided by plugin
    
    Args:
        module: python module
        
    Returns:
        string containing data keys provided by a plugin's update_function '''
    mls = _multi_line_string()
    try:
        data = module.constants.data
    except AttributeError:
        data = {'no keys available': None}
    mls.string = f'\nDATA KEYS AVAILABLE FOR USE IN LAYOUTS PROVIDED BY {module.__name__}:'
    for k in data.keys():
        mls.string = f'   {k}'
    return mls.string






def _get_sample_config(module):
    '''return sample configuration
    
    Args:
        module: python module
        
    Returns:
        string containing sample configuration if it exists'''
    
    mls = _multi_line_string()
    sample_config = None
    try:
        sample_config = module.constants.sample_config
    except AttributeError:
        sample_config = f'no sample configuration provided in {module.__name__}.constants'
        
    mls.string = f'\nSAMPLE CONFIGURATION FOR {module.__name__}'
    mls.string = sample_config
    
    return mls.string
    






def _get_doc_string(module, function):
    '''return a docstring for a function from within a module
        
    Args:
        module: python module
        function(str): string of function contained in module
        
    Returns:
        string containing docstring of for module.function'''
    try:
        f = getattr(module, function)
    except AttributeError as e:
        return e
    return f.__doc__






def get_help(module=None, print_help=True, plugin_path='./plugins'):
    '''display information for a plugin module including:
        * Functions available
        * Layouts defined
        * data keys returned by update_function()
        
    Args:
        module(`str`): "plugin_name" or "plugin_name.function" or None for a list of plugins
        when a function is provided, the function is executed'''
    plugin_path = Path(plugin_path)
    mls = _multi_line_string()
    plugin_list = []
    
    if not module:
        mls.string = 'get plugin information and user-facing functions:'
        mls.string = 'Usage: --plugin_info PLUGIN_NAME|PLUGIN_NAME.FUNCTION'
        mls.string = 'PLUGINS AVAILABLE:'
        for i in _get_modules(plugin_path):
            mls.string = f'  {i}'
        if print_help:
            print(mls.string)
        return mls.string
    
    my_module = module.split('.')
    logger.debug(f'gathering information for: {module}')
    
#     my_module = module.split('.')
#     logger.debug(f'my_module: {my_module}')
    
    try:
        plugin_name = f'{".".join(plugin_path.parts)}.{my_module[0]}.{my_module[0]}'
        logger.debug(f'attempting to import: {plugin_name}')
        imported = importlib.import_module(plugin_name)
    except ImportError as e:
        logger.warning(f'error importing {plugin_name}: {e}')
        mls.string = f'error importing {plugin_name}: {str(e)}'
        imported = False
    
#     try:
#         logger.debug(f'importing module: {my_module[0]}')
#         imported = importlib.import_module(f'{plugin_path.name}.{my_module[0]}.{my_module[0]}')
#     except Exception as e:
#         mls.string = f'error gathering information for module: {str(e)}'
#         logger.debug(mls.string)
#         imported = None

    try:
        version = imported.constants.version
    except AttributeError:
        version = 'no version provided'

#     try:
#         version = imported.constants.version
#     except AttributeError:
#         version = 'no version provided'


    if len(my_module) == 1 and imported:
        plugin_list.append(my_module)
        mls.string = f'PLUGIN: {my_module[0]} v:{version}\n'
        mls.string = _get_module_docs(imported)
        mls.string = _get_sample_config(imported)
        mls.string = _get_layouts(imported)
        mls.string = _get_data_keys(imported)
               
    elif len(my_module) > 1:
        mls.string = _get_doc_string(imported, my_module[1])
    else:
        pass
    
    if print_help:
        print(mls.string)
    return mls.string








