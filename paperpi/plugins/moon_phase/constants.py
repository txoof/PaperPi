# relative paths are difficult to sort out -- this makes it easier
import os
dir_path = os.path.dirname(os.path.realpath(__file__))

version = '0.2.3'
name = 'moon_phase'
app_source = "github.com/ysadamt/PaperPi"
data = {
    'moonrise': 'time moon appears above horizon',
    'moonset': 'time moon sets below horizon',
    'image_file': 'location of image file to display',
    'phase_desc': 'description of phase e.g. Waxing Crescent'
}


# open street maps location lookup
osm_endpoint = 'https://nominatim.openstreetmap.org/search?'
osm_query = "format=json&addressdetails=0&limit=0"

# met.no endpoints
met_endpoint = "https://api.met.no/weatherapi/sunrise/3.0/moon?"

# configuration keys required for opperation
required_config_options = {
    'lat': None,  
    'lon': None, 
    'location_name': 'Europe/Amsterdam',
    'email': None,
}

phase_desc = {
    0: 'New Moon',
    5: 'Waxing Gibbous',
    175: 'Full Moon',
    180: 'Full Moon',
    184: 'Waning Gibbous',
    355: 'Waning Gibbous',
    360: 'New Moon'
}

fallback_time = '1970-01-01T00:00+00:00'


json_file = f'{name}.json'
# set to 4 hrs * 60 min * 60 seconds 
json_max_age = 60*60*4

# image file constants
image_path = dir_path+"/./images/"
img_suffix = '.jpeg'

error_image = image_path+'error_message.jpg'

default_data = {
    'moonrise': 'moon rise: 00:00',
    'moonset': 'moon set: 00:00',
    'image_file': error_image,
    'phase_desc': 'ER: Check Log'
}

sample_config = '''
[Plugin: Moon Phase]
# default layout
layout = layout
plugin = moon_phase
min_display_time = 30
max_priority = 2
refresh_rate = 1200
# your email address for MET.no API access -- failure to specify may lead to a perma-ban
email = you@host.diamond
# Timezone locale name in Region/City format (see --run_plugin_func moon_phase.list_country_locales)
# Use a known city in your timezone; this is critical for calculating the moonrise time
location_name = Europe/Amsterdam
# lat/lon of your physical location (optional) (see --run_plugin_func moon_phase.get_coord)
lat = 52.3
lon = 4.9
'''
