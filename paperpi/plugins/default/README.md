# default

![sample image for plugin default](./default.layout-sample.png)
```ini
 
PLUGIN: default v:0.1.0

 
FUNCTION: update_function
update function for default provides time string and message
    
    This plugin is designed to display if all other plugins fail to load
    
    Args:
        self(`namespace`)
        msg(`str`): string to display
    
___________________________________________________________________________
 
 

SAMPLE CONFIGURATION FOR paperpi.plugins.default.default

[Plugin: default fallback plugin]
layout = layout
plugin = default
refresh_rate = 30
min_display_time = 60
max_priority = 2**15

 
LAYOUTS AVAILABLE:
  default
  layout
 

DATA KEYS AVAILABLE FOR USE IN LAYOUTS PROVIDED BY paperpi.plugins.default.default:
   digit_time
   msg
```

## Provided Layouts

layout: **default**

![sample image for plugin default](./default.default-sample.png) 


layout: **layout**

![sample image for plugin layout](./default.layout-sample.png) 


