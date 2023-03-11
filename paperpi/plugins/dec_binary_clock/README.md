# dec_binary_clock

![sample image for plugin dec_binary_clock](./dec_binary_clock.layout-L-sample.png)
```ini
 
PLUGIN: dec_binary_clock v:0.1.0

 
FUNCTION: update_function
update function for dec_binary_clock 
    
    This plugin provides time as an image and string in 
    four, four-bit numbers in little-endian format (see EXAMPLE).
    
    
    
    EXAMPLE:
    Time 14:49
    o o | o x
    o x | x o
    o o | o o
    x o | o x 
    
    Requirements:
        None
        
    Args:
        self(`object namespace`)
        time(`str`): HH:MM formatted string to display (this is primarily for testing)
        
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))
        
    
___________________________________________________________________________
 
 

SAMPLE CONFIGURATION FOR paperpi.plugins.dec_binary_clock.dec_binary_clock

[Plugin: decimal binary clock]
layout = layout
plugin = dec_bin_clock
refresh_rate = 30
min_display_time = 50
max_priority = 2

 
LAYOUTS AVAILABLE:
  dec_binary_clock
  layout
 

DATA KEYS AVAILABLE FOR USE IN LAYOUTS PROVIDED BY paperpi.plugins.dec_binary_clock.dec_binary_clock:
   bin_img
   time
```

## Provided Layouts

layout: **dec_binary_clock**

![sample image for plugin dec_binary_clock](./dec_binary_clock.dec_binary_clock-L-sample.png) 


layout: **layout**

![sample image for plugin layout](./dec_binary_clock.layout-L-sample.png) 


