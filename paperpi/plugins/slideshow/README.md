# slideshow
![sample image for plugin ...paperpi.plugins.slideshow](./slideshow.layout-sample.png) 

```
 
PLUGIN: slideshow v:0.1.0

 
FUNCTION: update_function
update function for slideshow plugin
    
    This plugin choose an image from a specified directory and displays it
    along with some optional information such as the time and a filename. 
    
    Images are displayed in either `random` or `sequential` order. 
    
    Each time the plugin runs the `image_path` is re-indexed. If images are added
    or removed from the `image_path`, they will be used in the rotation. 
    
    
    Requirements:
        self.config(dict): {
            'image_path': '/absolute/path/to/images',
            'order': 'random',
        }
        
    Args: 
        self(namespace): namespace from plugin object
    
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))

    
___________________________________________________________________________
 
 

SAMPLE CONFIGURATION FOR paperpi.plugins.slideshow.slideshow

[Plugin: Slideshow]
# default layout
layout = layout
plugin = slideshow
# time between choosing new image (seconds)
refresh_rate = 90
# recommended display time (seconds)
min_display_time = 30
# maximum priority in display loop
max_priority = 2
# path to image directory
image_path = /pi/documents/images
# order to pull images in: random, sequential
order = random

 
LAYOUTS AVAILABLE:
  image_only_centered_blackbkground
  image_only_centered_whitebkground
  image_time_centered_blackbkground
  image_time_centered_whitebkground
  layout
 

DATA KEYS AVAILABLE FOR USE IN LAYOUTS PROVIDED BY paperpi.plugins.slideshow.slideshow:
   time
   filename
   image
```

## Provided Layouts:

layout: **image_only_centered_blackbkground**

![sample image for plugin image_only_centered_blackbkground](./slideshow.image_only_centered_blackbkground-sample.png) 


layout: **image_only_centered_whitebkground**

![sample image for plugin image_only_centered_whitebkground](./slideshow.image_only_centered_whitebkground-sample.png) 


layout: **image_time_centered_blackbkground**

![sample image for plugin image_time_centered_blackbkground](./slideshow.image_time_centered_blackbkground-sample.png) 


layout: **image_time_centered_whitebkground**

![sample image for plugin image_time_centered_whitebkground](./slideshow.image_time_centered_whitebkground-sample.png) 


layout: **layout**

![sample image for plugin layout](./slideshow.layout-sample.png) 


## Additional Plugin Information

If the slideshow plugin fails to access the configured image path, it will fall back to several supplied images. The included images were sourced from the Flicker [Biodiversity Heritage Library](https://www.flickr.com/photos/61021753@N02/).


