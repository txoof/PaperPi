# relative paths are difficult to sort out -- this makes it easier
import os
from pathlib import Path
dir_path = os.path.dirname(os.path.realpath(__file__))

version = '0.1.0'
name = 'slideshow'
data = {
    'time': 'time in HH:MM format',
    'filename': 'filename',
    'image': 'a static image',
}
sample_config = '''
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
'''
# default path for images if none is provided
default_image_path = Path(dir_path+'/fallback_images')

# supported image file types 
supported_image_types = ['.gif', '.jpg', '.jpeg', '.png']

# recent images pickle file
recent_images = 'recent_images.pkl'

# expected options from configuration file
expected_config = {
    'image_path': (str, default_image_path),
    'order': (str, 'sequential'),
}
