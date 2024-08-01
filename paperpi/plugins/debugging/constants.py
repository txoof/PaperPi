version = '0.1.0'
name = 'debugging'

default_title = 'Debug'

# do not include a sample INI configuration
include_ini = False

sample_config='''
[Plugin: Debugging 50]
layout = debugging_basic
plugin = debugging
min_display_time = 50
max_priority = 1
refresh_rate = 5
title = Debugging 50
crash_rate = .5
max_priority_rate = .1
min_priority = 2
'''

data = {
    'title': 'title of plugin',
    'crash_rate': 'float between 0 and 1 indicating how frequently plugin should crash'
}
