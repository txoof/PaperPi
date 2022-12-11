#!/usr/bin/env python3
# coding: utf-8






import logging
import sys
sys.path.append('../')

from paperpi.library import Plugin, CacheFiles, get_help
from importlib import import_module
from pathlib import Path
import paperpi.my_constants as paperpi_constants
import logging
# from IPython.display import Image 
import argparse
import re






def get_base_prefix_compat():
    """Get base/real prefix, or sys.prefix if there is none."""
    return getattr(sys, "base_prefix", None) or getattr(sys, "real_prefix", None) or sys.prefix

def in_virtualenv():
    return get_base_prefix_compat() != sys.prefix






def do_exit(status=0, msg=None):
    if msg:
        print(msg)
    sys.exit(status)






def font_path(layout):
    '''add font path to layout'''
    for k, block in layout.items():
        font = block.get('font', None)
        if font:
            font = font.format(paperpi_constants.FONTS)
            block['font'] = font
    return layout






def find_plugins(project_root, plugin_list=None):
# , resolution=(600, 400), skip_layouts=False):
    
    plugin_path = Path(project_root)/paperpi_constants.PLUGINS
    if not plugin_path.exists() and not plugin_path.is_dir():
        raise NotADirectoryError
        
    # discover plugins
    found_plugins = get_help._get_modules(plugin_path)
    plugin_dict = {}
    
    if not plugin_list:
        plugin_list = []
    
    good_plugins = []

    
    for i in plugin_list:
        if i not in found_plugins:
            logging.warning(f'Plugin [{i}] was not found in the plugin directory, skipping')
        else:
            good_plugins.append(i)
    
    for i in found_plugins:
        plugin_dict[i] = {}
        if (not plugin_list) or (i in good_plugins):
            logging.info(f'[{i}]: queued for update')
            plugin_dict[i] = {'update': True}
        else:
            plugin_dict[i] = {'update': False}
        plugin_dict[i].update({'path': plugin_path/i})
    return plugin_dict






def create_plugins(plugin_dict, resolution=(640, 400)):
    logging.info('creating plugins to generating sample images')
    cache = CacheFiles()

    for plugin, value in plugin_dict.items():

        if not value.get('update'):
            logging.debug(f'***** {plugin:^20} *****')
            logging.debug(f'plugin not queued for update\n')        
        else:
            logging.info(f'***** {plugin:^20} *****')
        
        path = value.get('path', '.None')
        pkg_name = '.'.join([i for i in path.parts if not i.startswith('.')])
        all_layouts = {}
        
        logging.debug(f'[{plugin}] processing components')            
        try:
            module = import_module(f'{pkg_name}.{plugin}')
            layout_import = import_module(f'{pkg_name}.layout')
            sample_import = import_module(f'{pkg_name}.sample')
        except ModuleNotFoundError as e:
            logging.warning(f'skipping [{plugin}] due to error: {e}')
            continue
            
        
        
        # get all the layout dictionaries
        for a in dir(layout_import):
            if not a.startswith('_') and isinstance(getattr(layout_import, a), dict):
                all_layouts[a] = getattr(layout_import, a)
        if len(all_layouts) < 1:
            logging.warning(f'[{plugin}]: no valid layouts found; skipping')
            continue
        
        # check configuration
        try:
            config = sample_import.config
        except AttributeError as e:
            logging.warning(f'[{plugin}] has no valid sample configuration; skipping')
            continue
        
        # setup a different plugin instance for each layout
        plugin_dict[plugin].update({'layouts': []})
        for name, layout in all_layouts.items():

            # create valid font paths
            layout = font_path(layout)
            
            if not value.get('update'):
#                     logging.debug(f'skipping plugin update')
                    my_plugin = None
            else:
                logging.info(f'adding plugin with layout: {name}')
                my_plugin = Plugin(resolution=resolution,
                                   cache=cache,
                                   layout=layout,
                                   update_function=module.update_function,
                                   config=config)
                my_plugin.refresh_rate = 1

                try:
                    if 'kwargs' in config:
                        my_plugin.update(**config['kwargs'])
                    else:
                        my_plugin.update()
                except Exception as e:
                    logging.warning(f'[{plugin}]: could not be configured due to errors {e}')

            plugin_dict[plugin]['layouts'].append({
                'plugin': module,
                'plugin_obj': my_plugin,
                'layout_name': name})
            
    return plugin_dict
            
        
        
                






def update_readmes(plugin_dict, project_root, overwrite_images=False):
    logging.info('generating readmes for plugins')
    
    base_plugin_path = Path(project_root)/paperpi_constants.PLUGINS
    
    readme_name = 'README'
    readme_additional = '_additional'
    readme_suffix = 'md'    
        
    for plugin, value in plugin_dict.items():
        logging.info(f'***** {plugin:^20} *****')        
        if value.get('update', False):
            logging.info('updating...')
        else:
            logging.debug(f'gathering data, skipping update')

        plugin_path = base_plugin_path/plugin
        plugin_readme = plugin_path/f'{readme_name}.{readme_suffix}'
        logging.debug(f'readme file: {plugin_readme}')
        plugin_readme_additional = plugin_path/f'{readme_name}{readme_additional}.{readme_suffix}'
        layout_image = plugin_path/f'{plugin}.layout-sample.png'
        value['default_layout_image'] = {'filename': 'not found',
                                         'path': 'none',
                                         'layout_name': 'layout'}
                
        # produce an image from each layout
        for layout in value['layouts']:
            layout_name = layout.get('layout_name', None)
            image_filename = f'{plugin}.{layout_name}-sample.png'
            image_path = plugin_path/image_filename

            if overwrite_images or not image_path.exists():                
                try:
                    logging.info(f'saving image: {image_path}')
                    image = layout['plugin_obj'].image
                    image.save(image_path)
                except (AttributeError, OSError):
                    logging.warning(f'failed to get image for layout {layout_name}')
            else:
                logging.debug(f'will not overwrite: {image_path}')
            
            # record the filename
            layout_entry = {'filename': image_filename,
                            'path': image_path,
                            'layout_name': layout_name}        
        
            if layout_name == 'layout':
                value['default_layout_image'].update(layout_entry)
                layout['image_data'] = layout_entry
            else:
                layout['image_data'] = layout_entry
                            
        # get the help text  from all the user-facing functions
        readme_text = get_help.get_help(module=plugin, print_help=False, plugin_path=base_plugin_path)        
        if 'error importing' in readme_text:
            logging.warning(f'could not find any valid plugin information')
            continue
        
        # get the additional text
        if plugin_readme_additional.exists():
            logging.debug(f'adding additional text: {plugin_readme_additional}')
            with open(plugin_readme_additional, 'r') as file:
                additional_text = file.read()
        else:
            logging.debug(f'no additional text to add')
            additional_text = ''            
        
        # open the readme file and write
        with open(plugin_readme, 'w') as file:
            file.write(f'# {plugin}\n\n')
            file.write(f'![sample image for plugin {plugin}](./{value["default_layout_image"]["filename"]})\n')
            file.write(f'```ini\n{readme_text}\n```\n\n')
            file.write(f'## Provided Layouts\n\n')
            for layout in value['layouts']:
                file.write(f'layout: **{layout["layout_name"]}**\n\n')  
                file.write(f'![sample image for plugin {layout["layout_name"]}](./{layout["image_data"]["filename"]}) \n\n\n')
                
            file.write(additional_text)
            
        if plugin_readme.exists():
            value['README'] = plugin_readme
            
    return plugin_dict
    






# def update_readmes(plugin_dict, project_root, overwrite_images=False):
#     '''update readme files for each plugin'''
    
#     logging.info('generating readmes for plugins')
    
#     plugin_path = Path(project_root)/paperpi_constants.PLUGINS
    
#     readme_name = 'README'
#     readme_additional = '_additional'
#     readme_suffix = 'md'    

#     for plugin, value in plugin_dict.items():
        
#         if not value.get('update', False):
#             logging.debug(f'***** {plugin:^20} *****')
#             logging.debug('plugin not queued for update\n')
#             continue        
#         else:
#             logging.info(f'***** {plugin:^20} *****')
#             logging.info(f'updating...')
   
#         plugin_path = value.get('path', None)
#         if not plugin_path:
#             logging.warning('plugin not found!')
#             continue
        
#         plugin_readme = plugin_path/f'{readme_name}.{readme_suffix}'
#         plugin_readme_additional = plugin_path/f'{readme_name}{readme_additional}.{readme_suffix}'
        
#         if not plugin_readme.exists():
#             value['README'] = None
#         else:
#             value['README'] = plugin_readme
            
#         layout_image = Path(plugin_path)/f'{plugin}.layout-sample.png'
        
#         value['default_layout_image'] = {'filename': 'not found',
#                                          'path': 'none',
#                                          'layout_name': 'layout'}
#         if layout_image.exists():
#             value['default_layout_image'].update({'filename': layout_image.name,
#                                                   'path': layout_image,
#                                                   'layout_name': 'layout'})
#         else:
#             logging.warning('no default layout image exists for this plugin!')        
            
#         # get the help text  from all the user-facing functions
#         readme_text = get_help.get_help(module=plugin, print_help=False, plugin_path=plugin_path.parent)        
#         if 'error importing' in readme_text:
#             logging.warning(f'could not find any valid plugin information')
#             continue
            
#         # get the additional information
#         if plugin_readme_additional.exists():
#             logging.debug(f'adding additional text: {plugin_readme_additional}')
#             with open(plugin_readme_additional, 'r') as file:
#                 additional_text = file.read()
#         else:
#             logging.debug(f'no additional text to add')
#             additional_text = ''            
        
        
#         # produce an image from each layout
#         for layout in value['layouts']:
#             layout_name = layout.get('layout_name', None)
#             image_filename = f'{plugin}.{layout_name}-sample.png'
#             image_path = Path(plugin_path)/image_filename
                        
#             if (image_path.exists() and overwrite_images) or not image_path.exists():                
#                 try:
#                     image = layout['plugin_obj'].image
#                 except AttributeError:
#                     logging.warning(f'failed to get image for layout {layout_name}')
                
#                 logging.info(f'saving image: {image_path}')
#                 image.save(image_path)
#             else:
#                 logging.debug(f'will not overwrite: {image_path}')

#             layout_entry = {'filename': image_filename,
#                             'path': image_path,
#                             'layout_name': layout_name}        
        
        
#             if layout_name == 'layout':
#                 value['default_layout_image'].update(layout_entry)
#             else:
#                 layout['image_data'] = layout_entry
        
#     return plugin_dict






def update_documentation(plugin_dict, doc_path):
    '''
    update the Plugin.md documentation in the documentation dir using
    the READMEs from each plugin
    
    '''
    
    doc_path = Path(doc_path)
    plugin_readme_source = Path(doc_path)/'source/Plugins.md'
    plugin_readme_post_source = Path(doc_path)/'source/Plugins_post.md'
    plugin_readme_final = Path(doc_path)/plugin_readme_source.name
    
    logging.info(f'updating master documentation at: {plugin_readme_final}')
    
    final_text = ''

    try:
        with open(plugin_readme_source, 'r') as file:    
            source = file.read()

        with open(plugin_readme_post_source, 'r') as file:
            post = file.read()
    except OSError as e:
        logging.error(f'{e}')
        return False
        
    
    plugin_text = {}
    
    for plugin, value in plugin_dict.items():
        logging.info(f'***** {plugin:^20} *****')
        
        plugin_text[plugin] = [f'### [{plugin}]({value["README"]})\n']
        plugin_text[plugin].append(f'![{plugin} sample image]({value["default_layout_image"]["path"]})\n')
        
        
    with open(plugin_readme_final, 'w') as file:
        file.write(source)
        for plugin, text in sorted(plugin_text.items()):
            for each in text:
                file.write(each)
        file.write(post)
    
    return True
 






def update_ini(plugin_dict, project_root):
    '''append sample configurations for each module to the default paperpi.ini file'''
   
    project_root = Path(project_root)
    base_ini_file = project_root/'../install/paperpi_base.ini'
    output_ini_file = project_root/'config/paperpi.ini'
    
    logging.info(f'updating ini file: {output_ini_file}')

    config_sections = []
    
    
    
    for plugin, value in sorted(plugin_dict.items()):
        logging.info(f'***** {plugin:^20} *****')
        path = value.get('path', '.None')
        pkg_name = '.'.join([i for i in path.parts if not i.startswith('.')])
        
        try:
            module = import_module(f'{pkg_name}.{plugin}')
        except ModuleNotFoundError as e:
            logging.warning(f'skipping plugin: could not load module: {e}')
            continue
        
        try:
            if not module.constants.include_ini:
                logging.info(f'[{plugin}] plugin is explicitly excluded from the ini update process')
                continue
        except AttributeError:
            pass
        
        
        try:
            sample_config = module.constants.sample_config
        except AttributeError as e:
            logging.warning(f'skipping plugin: no sample ini config found: {e}')
            continue
        
        match = re.match('^\s{0,}\[Plugin', sample_config)
        
        try:
            if match.string:
                sample_config = re.sub('^\s{0,}\[Plugin', '[xPlugin', sample_config)
            else:
                logging.warning('skipping plugin: sample config does not have standard sample_config string')
                continue
        except AttributeError:
            logging.warning(f'skipping plugin: could not find standard sample_config string')
        
        logging.info(f'[{plugin}] appending ini file')
        config_sections.append(sample_config)
        config_sections.append('\n')
        
    output_ini_lines = []

    with open(base_ini_file, 'r') as file:
        for i in file:
            output_ini_lines.append(i)

    output_ini_lines.extend(config_sections)

    with open(output_ini_file, 'w') as file:
        for i in output_ini_lines:
            file.write(i)

    return output_ini_lines
        






def main():
    logging.basicConfig(level='INFO')
    logging.info('Creating documentation...')

    if not in_virtualenv():
        print('This script must be run within the PaperPi virtual environment\ntry:\npipenv run python3 {sys.argv[0]}')
        do_exit()
    
    
    parser = argparse.ArgumentParser(description='create_docs')

    
    parser.add_argument('-r', '--project_root', default='../paperpi/', nargs=1,
                       help='path to project root (default: ../paperpi)')
    
    parser.add_argument('-o', '--overwrite_images', default=False, action='store_true',
                       help='overwrite existing images for plugins when updating README files')
    
    parser.add_argument('-p', '--plugin_list', default=None, nargs='*', 
                       help='list of specific plugins to process')    
    
    parser.add_argument('-d', '--documentation_path', default='../documentation',
                       help='path to documentation directory (default: ../documentation)')
    
    parser.add_argument('--log_level', default='INFO', help='set logging output level')
    
    parser.add_argument('-i, ''--image_resolution', default=(640, 400),
                        help='resolution to use when generating sample images (default: 640x400)')
    
    
    
    args = parser.parse_args()
    
    logging.root.setLevel(args.log_level)
            
    try:
        plugin_dict = find_plugins(args.project_root, args.plugin_list)
    except OSError as e:
        do_exit(f'could not access project at path: {args.project_root}')
    
#     plugin_dict = find_plugins(args.project_root, args.plugin_list)
        
    plugin_dict = create_plugins(plugin_dict, )    
    
    plugin_dict = update_readmes(plugin_dict=plugin_dict, 
                                 project_root=args.project_root, 
                                 overwrite_images=args.overwrite_images)
    
    

    ret_val = update_documentation(plugin_dict=plugin_dict, doc_path=args.documentation_path)
    
    if not ret_val:
        logging.warning('problem updating main documentation archive -- see previous errors')
    
    ret_val = update_ini(plugin_dict=plugin_dict, project_root=args.project_root)
    
    if not ret_val:
        logging.warning('problem updating base ini file -- see previous errors')

    # do something with the ret_val??!
    
    
    return plugin_dict
    






if __name__ == "__main__":
    if '-f' in sys.argv:
        logging.debug('looks like this is running in a Jupyter notebook')
        idx = sys.argv.index('-f')
        del sys.argv[idx:idx+2]    
    r = main()




