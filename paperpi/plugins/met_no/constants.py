import os
dir_path = os.path.dirname(os.path.realpath(__file__))

version = "0.1.6"
name = "PaperPi Met No Weather plugin"
app_source = "github.com/txoof/PaperPi"

# open street maps location lookup
osm_endpoint = 'https://nominatim.openstreetmap.org/search?'
osm_query = "format=json&addressdetails=0&limit=0"

# met.no endpoints
yr_endpoint = "https://api.met.no/weatherapi/locationforecast/2.0/complete.json?"

# local images
symbol_codes_path = dir_path+"/./images/symbol_codes/"
wind_barbs_path = dir_path+"/./images/wind_barbs/"

abreviations = {'celsius': '°C',
                'fahrenheit': '°F',
                'degrees': '',
                'kelvin': 'K',
                '1': ' of 1',
                'inch': ' in',
                'knot': ' kt',
                'm/h': ' m/h',
                'm/s': ' m/s',
                'mm': ' mm',
                }

text = {'t_precipitation': 'Precipitation',
        't_max': 'Max',
        't_min': 'Min',
        't_temperature': 'Temperature',
        't_wind': 'Wind',
        't_presure': 'Presure',
        't_humidity': 'Humidity',
        't_wind_direction': 'Wind Direction',
        't_uv_index': 'UV Index',
        }

json_config = {
  "layout": "layout",
  "plugin": "met_no",
  "refresh_rate": 300,
  "min_display_time": 50,
  "max_priority": 2,
  "location_name": {
    "description": "Name of location to display on screen",
    "value": "Adis Ababa"
  },
  "lat": {
    "description": "Latitude of location",
    "value": 9.000,
    "type": "float"
  },
  "email": {
    "description": "Your email address - required by met.no API. Failure to use a real value can lead to a perma-ban from the service",
    "value": "you@host.diamond"
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
[Plugin: Weather Adis Ababa]
layout = layout
plugin = met_no
refresh_rate = 300
min_display_time = 50
max_priority = 2
location_name = Adis Ababa
lat = 9.000
lon = 38.750
# this is required by Met.no -- please use a real value
email = you@host.diamond
# Text color [RED, ORANGE, YELLOW, GREEN, BLUE, BLACK WHITE] or random
# bkground color is not supported in this plugin 
# text_color = BLUE 
'''
