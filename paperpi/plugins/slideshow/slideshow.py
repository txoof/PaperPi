#!/usr/bin/env python3
# coding: utf-8






# your function must import layout and constants
# this is structured to work both in Jupyter notebook and from the command line
try:
    from . import layout
    from . import constants
except ImportError:
    import layout
    import constants
    
from random import randrange
from datetime import datetime
from pathlib import Path






# make sure this function can accept *args and **kwargs even if you don't intend to use them
def update_function(self, *args, **kwargs):
    '''update function for slideshow plugin
    
    This plugin choose an image from a specified directory and displays it

    Requirments:
        self.config(dict): {
            'img_path': '/absolute/path/to/images',
            'order': 'random',
        }
        
    Args: 
        self(namespace): namespace from plugin object
    
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))

    %U'''   
    
    time = datetime.now().strftime('%H:%M')
    
    is_updated = False
    data = {
        'image': None,
        'time': time,
        'filename': None,
    }
    priority = self.max_priority

    
    # pull information from the plugin section of the configuration file (slimpi.ini)
#     try:
#         img_path = self.config['img_path']
#         order = self.config['order']
#     except AttributeError as e:
    
#     # do something with the configuration data
#     strings = [
#         f'Hi {name}! I hear your color is {color}',
#         f'{name}, did you know your color has {len(color)} characters in it?',
#         f'Your name spelled backwards is "{name[::-1]}"',
#         f'If you sort your favorite color alphabetically, you get: {("").join(sorted(color))}',
#         f'If you sort your name alphabetically, you get: {("").join(sorted(name))}',
#         f'My temporary cache path is: {self.cache.path}'
#     ]
    
#     # define the components of the data that will be returned
#     my_string = strings[randrange(0, len(strings)-1)]
#     time = datetime.now().strftime("%H:%M")
#     minute = datetime.now().strftime("%M")
#     image = Path(constants.img_file).resolve()

#     # optionally raise the priority under certain circumstances
    
#     # if the minute is even, raise the priority, else, leave it at the normal priority
#     if int(minute) % 2 == 0:
#         priority = self.max_priority - 1
#         extra_string = 'The minute is EVEN! I will raise the priority!'
#     else:
#         priority = self.max_priority
#         extra_string = f'The minute is odd; this is my file cache: {self.cache.path}'
    
    # build the output
    
    
    return (is_updated, data, priority)










import logging
logging.root.setLevel('DEBUG')
from library.CacheFiles import CacheFiles
def test_plugin():
    '''This code snip is useful for testing a plugin from within Jupyter Notebook'''
    from library import Plugin
    from IPython.display import display
    # this is set by PaperPi based on the configured schreen
    test_plugin = Plugin(resolution=(1200, 800))
    # this is pulled from the configuration file; the appropriate section is passed
    # to this plugin by PaperPi during initial configuration
    test_plugin.config = {
        'img_path': './fallback_images', 
        'order': 'sequential'}
    test_plugin.layout = layout.layout
    # this is done automatically by PaperPi when loading the plugin
    test_plugin.cache = CacheFiles()
    test_plugin.update_function = update_function
    test_plugin.update()
    display(test_plugin.image)
    return test_plugin
my_plugin = test_plugin






# this simulates calling the plugin from PaperPi
q = my_plugin()




