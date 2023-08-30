# relative paths are difficult to sort out -- this makes it easier
import os
dir_path = os.path.dirname(os.path.realpath(__file__))

version = '0.1.0'
name = 'demo_plugin'
data = {
    'welcome_str': 'welcome string',
    'time': 'time in HH:MM format',
    'extra': 'extra text under "special" conditions',
    'image': 'a static image',
}

json_config = {
  "layout": "layout",
  "plugin": "demo_plugin",
  "refresh_rate": 30,
  "min_display_time": 60,
  "max_priority": 1,
  "your_name": {
    "description": "Name that will be used in plugin",
    "value": "Slartybartfast"
  },
  "your_color": {
    "description": "Color that will be used in plugin",
    "value": "chartruse"
  } 
}

sample_config = '''
[Plugin: A Demo Plugin]
# this is a sample config users can use to help setup the plugin
# default layout
layout = layout
# the literal name of your module
plugin = demo_plugin
# recommended display time
min_display_time = 30
# maximum priority in display loop
max_priority = 1
# your name
your_name = Slartybartfast
# your favorite color
your_color = chartreuse
'''
img_file = dir_path+'/image.jpg'
