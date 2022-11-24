# slideshow
![sample image for plugin slideshow](./slideshow.layout-sample.png) 

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
# frame style to use (see README)
frame = black & silver: matted

 
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


## Additional Plugin Information

### Configuration Options:

```ini
image_path = /full/path/to/source/images
order = sequential | random
frame = frame style | random
```

* `image_path`: is the full path to the images that should be used for each update
* `order`: choose either `sequential` or `random`
* `frame`: choose one of the frame styles below or `None`

|  |  |  |
|:---:|:---:|:---:|
| <img src=./slideshow-framed-black_silver_matted.png><br />black & silver: matted | <img src=./slideshow-framed-dim_gray_and_silver_matted.png><br />dim-gray & silver: matted | <img src=./slideshow-framed-thick_black_matted.png><br />thick black: matted |
| <img src=./slideshow-framed-thin_black_matted.png><br />thin black: matted | <img src=./slideshow-framed-thick_black.png><br />thick black | <img src=./slideshow-framed-thin_black.png><br />thin black |
| <img src=./slideshow-framed-none.png><br />none | random (choose random frame style) |  |

Valid Frame Values:

* black & silver: matted
* dim-gray & silver: matted
* thick black: matted
* thin black: matted
* thick black
* thin black
* none


### Attributions

If the slideshow plugin fails to access the configured image path, it will fall back to several supplied images. The included images were sourced from the Flicker [Biodiversity Heritage Library](https://www.flickr.com/photos/61021753@N02/).


