# relative paths are difficult to sort out -- this makes it easier
import os
from pathlib import Path
dir_path = os.path.dirname(os.path.realpath(__file__))

version = '0.1.2'
name = 'slideshow'
data = {
    'time': 'time in HH:MM format',
    'filename': 'filename',
    'image': 'a static image',
}

json_config = {
  "layout": "layout",
  "plugin": "slideshow",
  "refresh_rate": 90,
  "min_display_time": 50,
  "max_priority": 2,
  "image_path": {
    "description": "Path to images on local device",
    "value": "/pi/documents/images"
  },
  "order": {
    "description": "Order to pull images",
    "value": "random",
    "choice": ["random", "sequential"]
  },
  "frame": {
    "description": "Frame to display around image",
    "value": "black & silver: matted",
    "choice": [
      "black & silver: matted",
      "dim-gray & silver: matted",
      "thick black: matted",
      "thick black",
      "thin black"]
  }
}

sample_config = '''
[Plugin: Slideshow]
# default layout
layout = layout
plugin = slideshow
# time between choosing new image (seconds)
refresh_rate = 90
# recommended display time (seconds)
min_display_time = 50
# maximum priority in display loop
max_priority = 2
# path to image directory
image_path = /pi/documents/images
# order to pull images in: random, sequential
order = random
# frame style to use (see README)
frame = black & silver: matted
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
    'frame': (str, 'None'),
}

# frame colors (RGB)
white = (255, 255, 255)
gainsboro = (220, 220, 220)
lightgray = (211, 211, 211)
silver = (192, 192, 192)
gray = (128, 128, 128)
dimgray = (105, 105, 105)
darkgray = (80, 80, 80)
black = (0, 0, 0)


# Frame styles
f_white_mat_silver_black = [(0.02, white), (0.01, silver), (0.08, black)]
f_white_mat_silver_dimgray = [(0.05, white), (0.01, silver), (0.08, dimgray)]
f_white_mat_thick_black = [(0.1, white), (0.2, black)]
f_white_mat_thin_black = [(0.025, white), (0.05, black)]
f_thick_black = [(0.2, black)]
f_thin_black = [(0.05, black)]

# these should all be lowercase
frames = {
    'black & silver: matted': f_white_mat_silver_black,
    'dim-gray & silver: matted': f_white_mat_silver_dimgray,
    'thick black: matted': f_white_mat_thick_black,
    'thin black: matted': f_white_mat_thin_black,
    'thick black': f_thick_black,
    'thin black': f_thin_black,
}