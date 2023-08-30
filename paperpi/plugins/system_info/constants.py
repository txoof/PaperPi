# relative paths are difficult to sort out -- this makes it easier
import os
dir_path = os.path.dirname(os.path.realpath(__file__))

version = '0.1.0'
name = 'system_info'
data = {
    'hostname': 'name of host',
    'time': 'time in HH:MM format',
    'disk_total': 'total storage',
    'diskuse': 'disk use as units',
    'diskuse_pct': 'disk use as percent of total',
    'diskfree': 'disk use as units',
    'diskfree_pct': 'disk use as percent of total',
    'cpuload_5': '5 min cpu load',
    'cpuload_10': '10 min cpu load',
    'cpuload_15': '15 min cpu load',    
    'ipaddress': 'ip address',
    'cputemp': 'cpu temperature',

}

image_path = dir_path+'/images/'

storage_units = {
    'KB': 10**3,
    'MB': 10**6,
    'GB': 10**9,
    'TB': 10**12,
    'EB': 10**15
    
}

json_config = {
  "layout": "layout",
  "plugin": "system_info",
  "refresh_rate": 90,
  "min_display_time": 45,
  "max_priority": 2,
  "storage_units": {
    "description": "Units to use when displaying disk useage",
    "value": "GB",
    "choice": [
      "KB",
      "MB",
      "GB",
      "TB",
      "EB"
    ]
  },
  "bkground": {
    "description": "Color to use for display background on 7 Color displays",
    "value": "WHITE",
    "choice": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "BLACK", "WHITE"]
  },
  "text_color": {
    "description": "Color to use for display background on 7 Color displays",
    "value": "BLACK",
    "choice": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "BLACK", "WHITE"]
  }
}

sample_config = '''
[Plugin: System Info]
# show basic facts about the system including IP, Hostname, CPU usage, temperature and storage
# default layout
layout = layout
# the literal name of your module
plugin = system_info
# recommended display time
min_display_time = 45
# maximum priority in display loop
max_priority = 2
# storage units in decimal: [KB] KiloByte 10^3; [MB] MegaByte 10^6; [GB] GigaByte 10^12; [TB] TeraByte 10^12
storage_unit = GB
# colors for RGB screens
text_color = BLUE
bkground_color = WHITE
'''
img_file = dir_path+'/image.jpg'
