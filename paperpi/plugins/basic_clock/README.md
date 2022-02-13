# basic_clock
![sample image for plugin ...paperpi.plugins.basic_clock](./basic_clock.layout-sample.png) 

```
 
PLUGIN: basic_clock v:0.1.1

 
FUNCTION: update_function
provides system time string in the format HH:MM
    
    Args:
        None
    

    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))
    
___________________________________________________________________________
 
 

SAMPLE CONFIGURATION FOR paperpi.plugins.basic_clock.basic_clock

[Plugin: Basic Clock]
layout = layout
plugin = basic_clock
refresh_rate = 30
min_display_time = 50
max_priority = 2

 
LAYOUTS AVAILABLE:
  basic_clock
  layout
 

DATA KEYS AVAILABLE FOR USE IN LAYOUTS PROVIDED BY paperpi.plugins.basic_clock.basic_clock:
   digit_time
```

## Provided Layouts:

layout: **basic_clock**

![sample image for plugin basic_clock](./basic_clock.basic_clock-sample.png) 


layout: **layout**

![sample image for plugin layout](./basic_clock.layout-sample.png) 


