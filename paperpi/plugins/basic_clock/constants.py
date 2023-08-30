version = '0.2.1'
name = 'basic clock'

config_keys = {
    
}

data = { 'digit_time': '00:00' }

json_config = {
  "layout": "layout",
  "plugin": "basic_clock",
  "refresh_rate": 30,
  "min_display_time": 50,
  "max_priority": 2
}

sample_config = '''
[Plugin: Basic Clock]
layout = layout
plugin = basic_clock
refresh_rate = 30
min_display_time = 50
max_priority = 2
'''
