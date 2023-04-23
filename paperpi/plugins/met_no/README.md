# met_no <font color="red">R</font><font color="green">G</font><font color="blue">B</font>

![sample image for plugin met_no](./met_no.layout-L-sample.png)
```ini
 
PLUGIN: met_no v:0.1.6

 
FUNCTION: get_coord
USER FACING HELPER FUNCTION:
    lookup and print the latitude, longitude of a place given as a string:
    
    usage: --run_plugin_func met_no.get_coord "Horsetooth Reservoir, Fort Collins CO, USA"
    
    Args:
        place(`str`): "City, Provence, Country
    
    Returns:
        `tuple`: lat, lon
        
    Example:
        get_coord("Denver, Colorado, USA")
        get_coord("Bamako, Mali")
        
___________________________________________________________________________
 
FUNCTION: update_function
update function for met_no plugin provides extensive forecast data
    
    This plugin provides hourly forecast data for a given location. 
    Data is pulled from the Norwegian Meterological Institute (met.no)
    Multiple met_no plugins can be active each with different locations 
    
    Forecast images are provided courtesy of Met.no
    
    All "local" time strings are converted to the system time
    
    Configuration Requirements:
        self.config(`dict`): {
            'lat': latitude of forecast location (`float`),
            'lon': longitude of forecast location (`float`),
            'location_name': name of location (`str`)
            'email': user contact email address -- required by met.no (`str`)
            'temp_units': 'celsius' or 'fahrenheit' (`str`), #optional
            'rain_units': 'mm' or 'inch' (`str`), #optional
            'windspeed': 'm/s', 'm/h', 'knot', 'k/h' (`str)#optional
        }
        self.cache(`CacheFiles` object)
        
    Args:
        self(namespace): namespace from plugin object
    
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))
    
___________________________________________________________________________
 
 

SAMPLE CONFIGURATION FOR paperpi.plugins.met_no.met_no

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

 
LAYOUTS AVAILABLE:
  layout
  three_column_icon_wind_temp_precip
  three_row_icon_wind_temp
  two_column_icon_wind_temp_precip
 

DATA KEYS AVAILABLE FOR USE IN LAYOUTS PROVIDED BY paperpi.plugins.met_no.met_no:
   no keys available
```

## Provided Layouts

layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> layout**

![sample image for plugin layout](./met_no.layout-RGB-sample.png) 


layout: **layout**

![sample image for plugin layout](./met_no.layout-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> three_column_icon_wind_temp_precip**

![sample image for plugin three_column_icon_wind_temp_precip](./met_no.three_column_icon_wind_temp_precip-RGB-sample.png) 


layout: **three_column_icon_wind_temp_precip**

![sample image for plugin three_column_icon_wind_temp_precip](./met_no.three_column_icon_wind_temp_precip-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> three_row_icon_wind_temp**

![sample image for plugin three_row_icon_wind_temp](./met_no.three_row_icon_wind_temp-RGB-sample.png) 


layout: **three_row_icon_wind_temp**

![sample image for plugin three_row_icon_wind_temp](./met_no.three_row_icon_wind_temp-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> two_column_icon_wind_temp_precip**

![sample image for plugin two_column_icon_wind_temp_precip](./met_no.two_column_icon_wind_temp_precip-RGB-sample.png) 


layout: **two_column_icon_wind_temp_precip**

![sample image for plugin two_column_icon_wind_temp_precip](./met_no.two_column_icon_wind_temp_precip-L-sample.png) 


