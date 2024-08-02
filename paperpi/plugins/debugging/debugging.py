# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:light
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

# %load_ext autoreload
# %autoreload 2

import logging
from datetime import datetime
from time import time
import random
from pathlib import Path

# two different import modes for development or distribution
try:
    # import from other modules above this level
    from . import layout
    from . import constants
except ImportError:
    import constants
    # development in jupyter notebook
    import layout


import sys
# fugly hack for making the library module available to the plugins
sys.path.append(layout.dir_path+'/../..')

logger = logging.getLogger(__name__)


def remove_non_alphanumeric(s):
    # Using list comprehension to filter out non-alphanumeric characters
    filtered_string = ''.join([char for char in s if char.isalnum()])
    return filtered_string


def update_function(self, title=None, crash_rate=None, *args, **kwargs):
    '''update function for debugging plugin provides title, time, crash rate
    
    This plugin shows minimal data and is designed to throw exceptions to test other functionality. 
    The plugin will deliberately and randomly throw exceptions at the rate specified in the configuration. 
    When an exception is not thrown, the plugin will randomly change its priority to the max set in the 
    configuration. Set the rate at which the plugin should jump to the higher priority status in the configuration.
    
    
    Args:
        self(`namespace`)
        title(`str`): title of plugin to display
        crash_rate(`float`): value between 0 and 1 indicating probability of throwing 
            exception on execution
    %U'''

    crash = False
    priority = self.max_priority
    is_updated = False
    
    if not title:
        title = self.config.get('title', constants.default_title)

    # sentinal file to indicate that the plugin has been setup
    filename = ''.join([char for char in title if char.isalnum()])
    first_run_file = Path(str(self.cache))/filename
    logging.info(f'first-run sentinal file: {first_run_file}')    
    
    if not crash_rate:
        crash_rate = self.config.get('crash_rate', 0)

    max_priority_rate = self.config.get('max_priority_rate', 0)
    
    
    random.seed(time())
    rand_val = random.random()
    rand_priority = random.random()
    # if this is the first run, do NOT crash; paperpi will exclude any
    # plugin that crashes during setup
    if not first_run_file.exists():
        logging.info(f'This is the first run of this plugin; creating sential file: {first_run_file}')
        rand_val = 2
        logging.info('plugin will not crash on first run')
        first_run_file.touch()
    else:
        pass

    logging.info(f'rand_priority: {rand_priority}, max_priority_rate: {max_priority_rate}')
    if rand_priority <= max_priority_rate:
        priority = self.max_priority
    else:
        priority = self.config.get('min_priority', 2)

    logging.info(f'priority set to: {priority}')
    
    
    data = {
        'title': f'{title}',
        'crash_rate': f'Crash Rate: {crash_rate*100:.0f}%',
        'digit_time': datetime.now().strftime("%H:%M:%S"),
        'priority': f'priority: {priority}',
    }

    logging.info(data)

    
    if rand_val <= crash_rate:
        logging.info('random crash occurred: will throw exception')
        crash = True
    else:
        logging.info('random crash did not occur: will not throw exception')
        crash = False

    if crash:
        raise Exception(f'random crash occured: random value {rand_val:.2f} <= {crash_rate:.2f}')
    else:
        is_updated = True
        
    is_updated = True
    return is_updated, data, priority


# +
# # this code snip simulates running from within the display loop use this and the following
# # cell to test the output
# import logging
# logging.root.setLevel('DEBUG')
# from library.CacheFiles import CacheFiles
# from library.Plugin import Plugin
# from IPython.display import display
# test_plugin = Plugin(resolution=(800, 600), screen_mode='L', max_priority=0)
# test_plugin.config = {
#     'text_color': 'random',
#     'bkground_color': 'White'
# }
# test_plugin.refresh_rate = 1
# l = layout.layout
# test_plugin.config = {
#     'title': 'Dummy 00',
#     'crash_rate': .33,
#     'max_priority_rate': .5,
#     'min_priority': 2
# }
# test_plugin.layout = l
# test_plugin.cache = CacheFiles()
# test_plugin.update_function = update_function
# # test_plugin.update()
# # test_plugin.image

# +
# test_plugin.update()
# test_plugin.image
