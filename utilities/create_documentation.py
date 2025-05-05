#!/usr/bin/env python3
# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.1
#   kernelspec:
#     display_name: venv_paperpi-9876705927
#     language: python
#     name: venv_paperpi-9876705927
# ---

# !jupytext create_documentation.ipynb --update-metadata '{"jupytext":{"executable":"/usr/bin/env python3"}}'


import logging
import inspect
import sys
sys.path.append('../')
from pathlib import Path
import argparse
from importlib import import_module
from pathlib import Path
import re
from copy import deepcopy

try:
    from paperpi.library import get_help, CacheFiles, Plugin
    import paperpi.my_constants as paperpi_constants
except Exception as e:
    print(e)
    print('This must be run within the paperpi virtual environment.')
    sys.exit(0)


class ErrorLog:
    def __init__(self):
        self.name = self._caller_name()
        self.errors = []

    def __str__(self):
        return f'function: {self.name}()'

    def __repr__(self):
        return f'ErrorLog for function: {self.name}'
    
    def log_error(self, error, level='WARNING', data=None):
        caller_name = self._caller_name()
        num_level = logging.getLevelName(level)
        if not isinstance(num_level, int):
            num_level = 0
        level_name = logging.getLevelName(num_level)
        if level_name in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:        
            logger = getattr(logging, str(level_name.lower()))
            logger(f'{caller_name}: {error}')
                
        self.errors.append({'error': error,
                            'level': num_level,
                            'data': data}
                          )
        return None
    
    @property
    def error_dict(self):
        return {self.name: self.errors}
    
    @staticmethod
    def _error_set(errors):
        error_set = set()
        for i in errors:
            error_set.add(i['level'])
        return error_set
        
    def max_error(self):
        error_set = self._error_set(self.errors)
        if error_set:
            error = max(error_set)
        else:
            error = 0
        
        return error
    
    def min_error(self):
        error_set = self._error_set(self.errors)
        if error_set:
            error = min(error_set)
        else:
            error = None
        
        return error        
    
    def get_errors(self, level):
        errors = []
        try:
            level = logging.getLevelName(level.upper())
        except AttributeError:
            pass
        
        for i in self.errors:
            # consider making this >=
            if i['level'] >= level:
                errors.append(i)
        
        return errors

    def _caller_name(self, level=2):
        return f'{inspect.stack()[level][3]}'


class Editor:
    def __init__(self, file, name=None, overwrite=False):
        self.overwrite = overwrite
        self.re_tags = {'start': '\s*\[start:\s*(.*)\]:\s*#\s*',
                     'end': '\s*\[end:\s*(.*)\]:\s*#\s*'}
        self.blank_tags = {'start': '\n[start: {}]: #',
                           'end': '\n[end: {}]: #' }
        self.name = name
        self.text = []
        self.section_index = {}
        self.file = file
        self.last = []
        
    def __str__(self):
        return str(self.name)
    
    def __repr__(self):
        return f'Editor for {self.name}: {self.file}'
    
    @property
    def file(self):
        return self._file
    
    @file.setter
    def file(self, fn):
        if fn:
            self._file = Path(fn).expanduser().absolute()
            self.text = self.load_file(self._file, overwrite=self.overwrite)
            self.index_sections()
            if not self.name:
                self.name = self._file.name
    
    @staticmethod
    def load_file(file, overwrite=False):
        '''open file and read text into list
        
        if the file path in the `file` property does not exist or `overwrite` property is true,
        set to an empty list'''
        if not file.exists() or overwrite:
            text = []
        else:
            with open(file) as f:
                text = f.read().splitlines()
        return text
        
    def index_sections(self):
        '''find the start & end index for the start/end tags and sets
        self.section_index property
        
        Args:
            value(str): tag name
        
        Returns:
            tuple of start/end index (int)'''
        tag_d = {}
        for i, j in enumerate(self.text):
            start = re.search(self.re_tags['start'], j)
            end = re.search(self.re_tags['end'], j)
            if start:
                tag_d.setdefault(start[1], {}).update({'start': i})
            if end:
                tag_d.setdefault(end[1], {}).update({'end': i})
        self.section_index = tag_d
        
    def get_section(self, section):
        '''return the contents of a section
        
        Args:
            section(str): name of section within start/end tags in .md file
            
        Returns:
            list of str'''
        index = self.section_index.get(section, {})
        if len(index)  == 2:
            selection = self.text[index['start']:index['end']+1]
        elif len(index) == 0:
            logging.debug(f'section "{section}" not found')
            selection = []
        elif len(index) < 2 or len(index) > 2:
            selection = []
            logging.warning(f'section "{section}" has ambigious start/end values')
        
        return selection

    def lookup_section(self, section):
        return self.section_index.get(section, {})

    def insert_section(self, section, text, index=None, before=None, after=None, tag=True, replace=False):
        if index and(before or after) or (before and after):
            raise ValueError('choose ONE of the following values: index, before, after')
        
        if section in self.section_index:
            logging.info(f'section "{section}" already exists; replacing')
            if replace:
                self.replace_section(section=section, text=text)
                return
            else:
                raise LookupError(f'section "{section}" already exists. try `replace=True`.')
        
        if before or after:
            get_section = before if before else after
            indicies = self.section_index.get(get_section, {'start': None, 'end': None})
            if before:
                index = indicies['start']-1
            if after:
                index = indicies['end']+1
            
        if tag:
            text.insert(0, self.blank_tags['start'].format(section))
            text.append(self.blank_tags['end'].format(section))
        
        self.text[index:index] = text
        self.index_sections()
    
    def del_section(self, section):
        '''deletes a section from the file 
        
        Args:
            section(str): section name
            
        Returns:
            list of deleted text
            
        Sets:
            section_index
            
        Raises:
            KeyError if section does not have valid start/end keys'''
        start_end = self.section_index.get(section, None)
        if not start_end:
            raise KeyError(f'section "{section}" does not exist in the buffer')
        start = start_end.get('start', None)
        end = start_end.get('end', None)
        
        if start and end:
            text = self.text[:start] + self.text[end+1:]
            deleted = self.text[start:end+1]
        else:
            raise KeyError(f'section "{section}" is missing start/end keys: {start_end}')
            
        self.text = text
        self.section_index.pop(section)
        self.index_sections()
        self.last = deleted
        
        return deleted
      
    def replace_section(self, section, text):
        '''replace an existing section with the specified text
        
        Args:
            section(str): name of section to replace
            text(str or list of sr): text to replace
            
        Returns:
            deleted text
        
        Sets:
            triggers reindex of section_index'''
        del_index = self.section_index.get(section, None)
        if not del_index:
            raise KeyError(f'section "{section}" could not be found')
        del_text = self.del_section(section)
        add_text = self.insert_section(section=section, text=text, index=del_index['start']+1)
        self.index_sections()
        self.last = del_text
        return del_text
        
    def append_section(self, section, text, check=False, tag=True):
        '''append text at to the end of the loaded text without checking for end tags
        
        Args:
            section (str): name of the new section
            text (list): text to append
            check (bool): False: do not check if line above has [end: ] tag
            tag (bool): True: add start/end tags
        
        Returns:
            text added
            '''
        
        self.insert_section(section=section, text=text, check=check, tag=tag, index=len(self.text)+1)
        
        self.last = text
        
    def sort_sections(self, sections, reverse=False, ignore_missing=True):
        
        sections.sort(reverse=reverse)
        starts = set()
        temp_buffer = []
        for i in sections:
            # get the insertion locations 
            starts.add(self.section_index.get(i, {}).get('start', 2**32))
            # delete the sections from the buffer and save in a temporary buffery
            try:
                temp_buffer = temp_buffer + self.del_section(i)
            except KeyError as e:
                if ignore_missing:
                    logging.warning(f'section {i} does not exist in the buffer')
                else:
                    raise KeyError(e)
            
        # get the index of the lowest position
        index = min(starts)
        
        # insert the sorted sections at the index, skip tagging
        self.insert_section(section=None, tag=False, text=temp_buffer, index=index)
        
    def append_file(self, file, section='', check=False, tag=False):
        '''append a file to the loaded text
        
        Args:
            file(str): path to file
            section(str): name of section to add (ignored if tag=False)
            check(bool): False: do not check if previous section is has an [end: ] tag 
            tag(bool): False: skip adding a start/end tag
        
        Returns:
            text appended'''
        file = Path(file)
        text = self.load_file(file)
        
        self.last = text
        
        self.insert_section(section=section, text=text, check=check, tag=tag, index=len(self.text)+1)  
            
    def fix_tags(self):
        mismatched = self.mismatched_tags

        for section, value in mismatched.items():
            if value.get('start'):
                for i in range(value.get('start')+1, len(self.text)):
                    if re.search(self.re_tags['start'], self.text[i]):
                        self.text[i:i] = [self.blank_tags['end'].format(section)]
                        break
            if value.get('end'):
                for i in reversed(range(0, value.get('end'))):
                    if re.search(self.re_tags['end'], self.text[i]):
                        self.text[i+1:i+1] = [self.blank_tags['start'].format(section)]
                        break
        self.index_sections()

    @property
    def mismatched_tags(self):
        mismatched = {}
        for section, value in self.section_index.items():
            
            if isinstance(value.get('start'), int):
                start_ok = True
            else:
                start_ok = False
                
            if isinstance(value.get('end'), int):
                end_ok = True
            else:
                end_ok = False
            
            if not (start_ok and end_ok):
                mismatched[section] = {'start': value.get('start', None),
                                       'end': value.get('end', None)}
        return mismatched

    @property
    def tags_ok(self):
        return len(self.mismatched_tags) < 1
    
    def write_file(self, filename=None):
        if filename:
            fn = Path(filename).expanduser().absolute()
        else:
            fn = self.file
        with open(fn, 'w') as f:
            f.writelines(line + '\n' for line in self.text)
            
    def save_as(self, filename):
        self.write_file(filename=filename)
    
    def print_indexed(self):
        for i, j in enumerate(self.text):
            print (f'{i:<5}: {j}')
    
    def print_text(self):
        for i in self.text:
            print(i)


def get_base_prefix_compat():
    """Get base/real prefix, or sys.prefix if there is none."""
    # return getattr(sys, "base_prefix", None) or getattr(sys, "real_prefix", None) or sys.prefix
    return hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

def in_virtualenv():
    return get_base_prefix_compat()


def check_errors(errorlog, func_name, max_level=30, exit=True):
    last_function_errors = errorlog.get(func_name, None)
    
    if last_function_errors:
        if last_function_errors.max_error() > max_level:
            print(f'Errors found in {func_name}')
            print(errorlog.get_errors(max_level))
            if exit:
                do_exit(msg='bailing out due to previous errors')






def do_exit(status=0, msg=None):
    if msg:
        print(msg)
    sys.exit(status)






def find_plugins(project_root, plugin_list=[], exclude_list=[]):
    '''locate all the plugins available in the /paperpi/plugins directory
    
    Args:
        project_root (str): path to the root of the paperpi directory
        plugin_list (list of str): list of the plugins to be updated
            if none are specified, all will be updated
        exclude_list (list of str): list of plugins to be excluded from updates
        
    Returns:
        dict of plugin data
        '''
            
    plugin_path = Path(project_root)/paperpi_constants.PLUGINS
    
    plugin_dict = {'plugins': {},
                   'errors': {},
                   'plugin_path': plugin_path}
    plugins = {}
    
    errorlog = ErrorLog()
    
    if not plugin_path.exists() or not plugin_path.is_dir():
        errorlog.log_error(f'Plugin path "{plugin_path}" does not exist or is not a directory', 'CRITICAL', plugin_path)
        plugin_dict['errors'].update(errorlog.error_dict)
        return plugin_dict
    

    # discover plugins
    found_plugins = get_help._get_modules(plugin_path)
    
    update_plugins = []
    
    if len(plugin_list) > 0:
        for i in plugin_list:
            if i in found_plugins:
                update_plugins.append(i)
            else:
                errorlog.log_error(f'Specified plugin "{i}" could not be found; will not update', 'WARNING')
    else:
        update_plugins = found_plugins
            
    for i in update_plugins:
        plugins[i] = {}
        logging.info(f'Plugin "{i}" found and queued for update')
        if i in exclude_list:
            errorlog.log_error(f'Plugin {i} in exclude list, will not be updated', 'INFO', exclude_list)
            plugins[i].update({'update': False, 'path': plugin_path/i})
        else:
            plugins[i].update({'update': True, 'path': plugin_path/i})
        

    plugin_dict['plugins'] = plugins
    plugin_dict['errors'][errorlog.name] = errorlog
    
    return plugin_dict






def create_plugins(plugin_dict, resolution=(640, 400)):
    '''Build plugin objects for all plugins
    
    Args:
        plugin_dict (dict): of plugin information
        resolution (tuple): resolution to use when setting up plugins
        
    Returns:
        dict of plugin objects and data'''
    logging.info('creating plugin objects')
    cache = CacheFiles()
    errorlog = ErrorLog()

    if not 'errors' in plugin_dict:
        errorlog.log_error('malformed plugin_dict: missing "errors" key', 'ERROR')
        plugin_dict['errors'] = {}
    
    if len(plugin_dict.get('plugins', {})) < 1:
        errorlog.log_error('no plugins found in plugin_dict', 'CRITICAL')
    
    for plugin, value in plugin_dict.get('plugins', {}).items():
        logging.info(f"PLUGIN [{plugin:^30}]")
        if not value.get('update'):
            logging.debug(f'{plugin} not queued for update\n')
            continue
        
        path = value.get('path', '.None')
        
        pkg_name = '.'.join([i for i in path.parts if not i.startswith('.')])
        plugin_layouts = {}
        
        try:
            module = import_module(f'{pkg_name}.{plugin}')
            layout_import = import_module(f'{pkg_name}.layout')
            sample_import = import_module(f'{pkg_name}.sample')
        except ModuleNotFoundError as e:
            errorlog.log_error(f'skipping [{plugin}]', 'WARNING', e)
            continue
        
        # get all the layout dictionaries
        for a in dir(layout_import):
            if not a.startswith('_') and isinstance(getattr(layout_import, a), dict):
                plugin_layouts[a] = getattr(layout_import, a)
        if len(plugin_layouts) < 1:
            errorlog.log_error(f'no valid layouts foound for plugin "{plugin}"', 'WARNING')
            continue
        
        # check configuration
        try:
            config = sample_import.config
        except AttributeError as e:
            errorlog.log_error(f'no valid sample configuration for plugin "{plugin}"', 'WARNING', e)
            continue
            
  
        # setup a different plugin instance for each layout
        # check to see if there is an RGB capable block and use the sample fill/bkground values here
        value.update({'layouts': []})
        for name, layout in plugin_layouts.items():
#             value['layouts'].append(layout)
            screen_modes = {'L'}
            for section, properties in layout.items():
                if properties.get('rgb_support', False):
                    screen_modes.add('RGB')
            logging.info(f'{" "*5}Added {name}, supported modes: {screen_modes}')
            
            for screen_mode in screen_modes:
                try:
                    my_plugin = Plugin(resolution=resolution, 
                                         cache=cache,
                                         name=name,
                                         layout=layout,
                                         update_function=module.update_function, 
                                         config=config, 
                                         screen_mode=screen_mode,
                                         refresh_rate=1)

                except Exception as e:
                    errorlog.log_error(f'error building plugin "{plugin}", mode {screen_mode}: {e}', 'ERROR', e)
                    continue
                
                value['layouts'].append({
                    'plugin': module,
                    'plugin_obj': my_plugin,
                    'layout_name': name,
                    'screen_mode': screen_mode,
                    'layout': layout,
                    'config': config,
                    
                })
        
            
    plugin_dict['errors'][errorlog.name] = errorlog
            
    return plugin_dict               






def update_readmes(plugin_dict, overwrite_images=False):
    logging.info('generating readmes for plugins')
    
    errorlog=ErrorLog()
    
    base_plugin_path = plugin_dict['plugin_path']
    
    readme_name = 'README'
    readme_additional = '_additional'
    readme_suffix = 'md'
    rgb_string = '<font color="red">R</font><font color="green">G</font><font color="blue">B</font>'

    
    for plugin, data in plugin_dict['plugins'].items():
        logging.info(f'[{plugin:^30}]')
        if data.get('update', False):
            logging.info(f'{" "*5}updating documentation')
        else:
            continue
        
        layouts = data.get('layouts', [])
        data['default_layout_image'] = {'filename': None,
                                        'path': None,
                                        'layout_name': 'layout'}
        plugin_path = data['path']
        plugin_readme = plugin_path/f'{readme_name}.{readme_suffix}'
        plugin_readme_additional = plugin_path/f'{readme_name}{readme_additional}.{readme_suffix}'
        layout_image = plugin_path/f'{plugin}.layout-sample.png'
        
        # identify plugins that support RGB
        rgb_support = ''
        for i in layouts:
            if i.get('screen_mode') == 'RGB':
                rgb_support = ' ' + rgb_string
                break
        data['rgb_string'] = rgb_support
        
        
        # generate images from each initialized plugin and layout
        for layout in layouts:
            layout_name = f"{layout['layout_name']}-{layout['screen_mode']}"
            image_filename = f'{plugin}.{layout_name}-sample.png'
            image_path = data['path']/image_filename
            logging.info(f'processing plugin layout: "{layout_name}"')
        
            if overwrite_images or not image_path.exists():
                logging.info(f'saving image: {image_path}')
                
                config = layout.get('config', {})
                kwargs = config.get('kwargs', {})
                
                try:
                    layout['plugin_obj'].update(**kwargs)
                    image = layout['plugin_obj'].image
                    image.save(image_path)
                except (AttributeError) as e:
                    errorlog.log_error(f'could not access image for layout \"{layout_name}\": {e}', 'ERROR', e)
                except (OSError) as e:
                    errorlog.log_error(f'could not write file for layout \"{layout_name}\": {e}', 'ERROR', e)
                except Exception as e:
                    errorlog.log_error(f'general error caused failure of documentation for \"{layout_name}\": {e}', 'ERROR', e)
            else:
                logging.info('skipping image update due to settings')
                
            layout_entry = {'filename': image_filename,
                            'path': image_path,
                            'layout_name': layout_name}
                
            if layout_name == 'layout-L':
                data['default_layout_image'].update(layout_entry)
                layout['image_data'] = layout_entry
            else:
                layout['image_data'] = layout_entry
            
        # get help text from all the user-facing functions for this plugin
        readme_text = get_help.get_help(module=plugin, print_help=False, plugin_path=base_plugin_path)
        
        if 'error importing' in readme_text:
            errorlog.log_error(f'error importing plugin functions', 'WARNING')
        
        # get the additional text
        if plugin_readme_additional.exists():
            logging.debug(f'adding additional text from: {plugin_readme_additional}')
            try:
                with open(plugin_readme_additional, 'r') as file:
                    additional_text = file.read()
            except OSError as e:
                errorlog.log_error(f'error reading "{plugin_readme_additional}": {e}', 'ERROR', e)
            except Exception as e:
                errorlog.log_error(f'general error reading "{plugin_readme_additional}": {e}', 'ERROR', e)
                
        else:
            logging.debug('no additional text found')
            additional_text = ''
            
        # open the readme file and write
        try:
            with open(plugin_readme, 'w') as file:
                logging.debug(f'writing readme for "{plugin}"')
                file.write(f'# {plugin}{rgb_support}\n\n')
                file.write(f'![sample image for plugin {plugin}](./{data["default_layout_image"]["filename"]})\n')
                file.write(f'```ini\n{readme_text}\n```\n\n')
                file.write(f'## Provided Layouts\n\n')
                
                # document each individual layout
                for layout in data['layouts']:
                    logging.debug(f'processing layout: {layout["layout_name"]}')
                    if layout.get('screen_mode', False) == 'RGB':
                        rgb_support = rgb_string+' '
                    else:
                        rgb_support = ''
                    file.write(f'layout: **{rgb_support}{layout["layout_name"]}**\n\n')  
                    file.write(f'![sample image for plugin {layout["layout_name"]}](./{layout["image_data"]["filename"]}) \n\n\n')

                file.write(additional_text)
        except OSError as e:
            errorlog.log_error(f'error writing to "{pluguin_readme}": {e}', 'ERROR', e)
            continue
        except Exception as e:
            errorlog.log_error(f'general error writing "{plugin_readme}": {e}', 'CRITICAL', e)
            continue
        
        if plugin_readme.exists():
            data['README'] = plugin_readme
    
    
    plugin_dict['errors'][errorlog.name] = errorlog

    return plugin_dict







def update_documentation(plugin_dict, doc_path='../documentation', insert_after='plugin_header'):
    plugin_header = '### [{}]({}){}'
    plugin_image = '![{} sample image]({})'
    
    doc_path = Path(doc_path).expanduser().absolute()
    plugin_readme = Path(doc_path)/'Plugins.md'
    
    logging.info(f'updating documentation at: {plugin_readme}')
    errorlog = ErrorLog()
    
    editor = Editor(plugin_readme)
    
    if not editor.tags_ok:
        errorlog.log_error(f'mismatched start/end tags in {plugin_readme}', 'ERROR', editor.mismatched_tags)
    
    for plugin, data in plugin_dict.get('plugins').items():
        if not data['update']:
            logging.info(f'skipping update for "{plugin}"')
            continue
        logging.info(f'inserting section "{plugin}" after "{insert_after}"')
        text = []
        text.append(plugin_header.format(plugin, data.get('README'), data.get('rgb_string')))
        text.append(plugin_image.format(plugin, data.get('default_layout_image')['path']))
    
        editor.insert_section(section=plugin, 
                              text=text,
                              after=insert_after, 
                              replace=True)
        editor.index_sections()
        
        insert_after = plugin
    
    logging.info('sorting plugin sections alphabetically')
    sections = [i for i in plugin_dict.get('plugins').keys()]
    
    editor.sort_sections(sections=sections)
    try:
        editor.write_file()
    except Exception as e:
        errorlog.log_error(f'error writing documentation file "{plugin_readme}": {e}', 'ERROR', e)
    
    plugin_dict['errors'][errorlog.name] = errorlog

    
    return plugin_dict






def update_ini_file(plugin_dict):
    
    project_root = plugin_dict['project_root']
    base_ini=Path(project_root)/'config/paperpi_base.ini'
    full_ini=Path(project_root)/'config/paperpi.ini'
    errorlog = ErrorLog()
    
    print(f'Updating {full_ini} file using sample configs from plugins')
    
    
    config_sections = {}
    
    for plugin, values in plugin_dict.get('plugins').items():
        print(f'processing [[{plugin}]]')
        
        layouts = values.get('layouts', [None])
        my_plugin = layouts[0].get('plugin', None)
        if my_plugin:
            try:
                sample_config = my_plugin.constants.sample_config
                config_sections[plugin] = sample_config
            except AttributeError as e:
                errorlog.log_error(f'failed to find sample_config for plugin {plugin}.', 'WARNING', e)
                sample_config = None
            
        
    
    for c, value in sorted(config_sections.items()):
        match = re.match('^\s{0,}\[Plugin', value)
        
        try:
            if match.string:
                value = re.sub('^\s{0,}\[Plugin', '[xPlugin', value)
                config_sections[c] = value
        except AttributeError as e:
            errorlog.log_error(f'sample configuration is does not have a valid header!', 'WARNING', e)
    
    output_ini = []
    with open(base_ini, 'r') as base_f:
        for i in base_f:
            output_ini.append(i)
    
    for i, v in config_sections.items():
        output_ini.append(v)
        output_ini.append('\n')
            
    print(f'writing updated .ini file to {full_ini}')
    with open(full_ini, 'w') as out_f:
        for i in output_ini:
            out_f.write(i)
                
    plugin_dict['errors'][errorlog.name] = errorlog
    return plugin_dict







def main():
    logging.info('Creating documentation...')
    
    if not in_virtualenv():
        print('This script must be run within the PaperPi virtual environemnt\ntry:\npipenv run python3 {sys.argv[0]}')
        do_exit()
            
    
    parser = argparse.ArgumentParser(description='create_docs')


    parser.add_argument('-r', '--project_root', default='../paperpi/', nargs=1,
                       help='path to project root (default: ../paperpi)')
    
    parser.add_argument('-o', '--overwrite_images', default=False, action='store_true',
                       help='overwrite existing images for plugins when updating README files')
    
    parser.add_argument('-e', '--exclude_list', default=[], nargs='*',
                       help='list of plugins to exclude from processing')
    
    parser.add_argument('-p', '--plugin_list', default=[], nargs='*', 
                       help='list of specific plugins to process')    
    
    parser.add_argument('-d', '--documentation_path', default='../documentation',
                       help='path to documentation directory (default: ../documentation)')
    
    parser.add_argument('--log_level', default='INFO', help='set logging output level')
    
    parser.add_argument('-i', '--image_resolution', default=(640, 400),
                        help='resolution to use when generating sample images (default: 640x400)')
    
    parser.add_argument('-t', '--insert_after_tag', default='plugin_header', 
                        help='header in Plugin.md file after which to add plugin documentation strings (default: "plugin_header")')
    args = parser.parse_args()
    
    logging.root.setLevel(args.log_level)
        
        
    try:
        plugin_dict = find_plugins(project_root=args.project_root, 
                                  plugin_list=args.plugin_list,
                                  exclude_list=args.exclude_list)
        plugin_dict['project_root'] = Path(args.project_root).expanduser().absolute()
        plugin_dict['documentation_path'] = Path(args.documentation_path).expanduser().absolute()

    except Exception as e:
        do_exit(msg=f'Fatal error finding plugins{e}')
        
    check_errors(errorlog=plugin_dict.get('errors', {}), func_name='find_plugins', exit=True)
    
    try:
        plugin_dict = create_plugins(plugin_dict)
    except Exception as e:
        do_exit(msg=f'Fatal error creaing plugin objects: {e}')
        
    check_errors(errorlog=plugin_dict.get('errors', {}), func_name='create_plugins', exit=True)
    
    try:
        plugin_dict = update_readmes(plugin_dict,
                                    overwrite_images=args.overwrite_images)
    except Exception as e:
        do_exit(msg=f'Fatal error updaging plugin READMEs: {e}')
    
    check_errors(errorlog=plugin_dict.get('errors', {}), func_name='update_readme', exit=True)
        
    try:
        plugin_dict = update_documentation(plugin_dict, doc_path=plugin_dict['documentation_path'],
                                          insert_after=args.insert_after_tag)
    except Exception as e:
        return plugin_dict
        do_exit(msg=f'Fatal error updating Plugin.md: {e}')
    

    check_errors(errorlog=plugin_dict.get('errors', {}), func_name='update_documentation', exit=False)
    
    
    try:
        plugin_dict = update_ini_file(plugin_dict)
    except Exception as e:
        return plugin_dict
        do_exit(msg=f'Fatal error writing paperpi.ini file: {e}')
    
    check_errors(errorlog=plugin_dict.get('errors', {}), func_name='update_ini_file', exit=False)
    return plugin_dict

        






if __name__ == "__main__":
    if '-f' in sys.argv:
        logging.basicConfig(level='DEBUG')
        logging.debug('looks like this is running in a Jupyter notebook')
        idx = sys.argv.index('-f')
        del sys.argv[idx:idx+2]    
    r = main()

