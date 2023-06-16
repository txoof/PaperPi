#!/usr/bin/env python3
# coding: utf-8




import logging






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






from datetime import datetime
def update_function(self, msg=None, high_priority=False, *args, **kwargs):
    '''update function for default provides time string and message
    
    This plugin is designed to display if all other plugins fail to load
    
    Args:
        self(`namespace`)
        msg(`str`): string to display
    %U'''
    if not msg:
        msg = constants.msg
    data = {
        'digit_time': datetime.now().strftime("%H:%M:%S"),
        'msg': msg,
    }
    if high_priority:
        priority = -2**15
    else:
        priority = 2**14
        
    is_updated = True
    return (is_updated, data, priority) 






# # this code snip simulates running from within the display loop use this and the following
# # cell to test the output
# import logging
# logging.root.setLevel('DEBUG')
# from library.CacheFiles import CacheFiles
# from library.Plugin import Plugin
# from IPython.display import display
# test_plugin = Plugin(resolution=(800, 600), screen_mode='L')
# test_plugin.config = {
#     'text_color': 'random',
#     'bkground_color': 'White'
# }
# test_plugin.refresh_rate = 5
# l = layout.layout
# test_plugin.layout = l
# test_plugin.cache = CacheFiles()
# test_plugin.update_function = update_function
# test_plugin.update()
# test_plugin.image











