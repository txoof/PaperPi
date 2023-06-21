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
    'cpuload': 'cpu load',
    'ipaddress': 'ip address',
    'cputemp': 'cpu temperature',

}

storage_units = {
    'KB': 10**3,
    'MB': 10**6,
    'GB': 10**9,
    'TB': 10**12,
    'EB': 10**15
    
}

sample_config = '''
[Plugin: System Info]
# this is a sample config users can use to help setup the plugin
# default layout
layout = layout
# the literal name of your module
plugin = 
# recommended display time
min_display_time = 45
# maximum priority in display loop
max_priority = 2
# storage units in decimal: [KB] KiloByte 10^3; [MB] MegaByte 10^6; [GB] GigaByte 10^12; [TB] TeraByte 10^12
storage_unit = GB
# 
'''
img_file = dir_path+'/image.jpg'
