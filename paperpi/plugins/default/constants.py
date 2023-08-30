version = '0.1.0'
name = 'basic clock'

msg = 'No plugins are active, check the logs!'

data = { 
  'digit_time': '00:00',
  'msg': 'str',
}

json_config = {
  "layout": "layout",
  "plugin": "default",
  "configurable": false,
  "refresh_rate": 30,
  "min_display_time": 60,
  "max_priority": 32768
}

# do not include a sample INI configuration
include_ini = False

sample_config='''
[Plugin: default fallback plugin]
layout = layout
plugin = default
refresh_rate = 30
min_display_time = 60
max_priority = 2**15
'''