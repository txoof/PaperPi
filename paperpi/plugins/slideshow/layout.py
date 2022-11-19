# slideshow plugin layouts
# handling file locations with relative paths is hard
# this simplifies locating the fonts needed for this layout
import os
dir_path = os.path.dirname(os.path.realpath(__file__))


image_only_centered_blackbkground = {
    'image': {
        'type': 'ImageBlock',
        'image': True,
        'mode': 'L',
        'width': 1,
        'height': 1,
        'abs_coordinates': (0, 0),        
        'random': False,
        'relative': False,
        'hcenter': True,
        'vcenter': True,
        'bkground': 0,     
    }
}

image_only_centered_whitebkground = {
    'image': {
        'type': 'ImageBlock',
        'image': True,
        'mode': 'L',
        'width': 1,
        'height': 1,
        'abs_coordinates': (0, 0),        
        'random': False,
        'relative': False,
        'hcenter': True,
        'vcenter': True,
        'bkground': 255,
        
    }
}


image_time_centered_blackbkground = {
    'image': {
        'type': 'ImageBlock',
        'image': True,
        'mode': 'L',
        'width': 1,
        'height': 9/10,
        'abs_coordinates': (0, 0),        
        'random': False,
        'relative': False,
        'hcenter': True,
        'vcenter': True,
        'bkground': 0
    },
    'time': {
        'type': 'TextBlock',
        'image': False,
        'mode': 'L',
        'width': 1,
        'height': 1/10,
        'abs_coordinates': (0, None),
        'relative': ['time', 'image'],
        'hcenter': True,
        'vcenter': True,
        'align': 'center',
        'inverse': True,
        'font': dir_path+'/../../fonts/Anton/Anton-Regular.ttf',
    }
}

image_time_centered_whitebkground = {
    'image': {
        'type': 'ImageBlock',
        'image': True,
        'mode': 'L',
        'width': 1,
        'height': 9/10,
        'abs_coordinates': (0, 0),        
        'random': False,
        'relative': False,
        'hcenter': True,
        'vcenter': True,
        'bkground': 255
    },
    'time': {
        'type': 'TextBlock',
        'image': False,
        'mode': 'L',
        'width': 1,
        'height': 1/10,
        'abs_coordinates': (0, None),
        'relative': ['time', 'image'],
        'hcenter': True,
        'vcenter': True,
        'inverse': False,
        'align': 'center',        
        'font': dir_path+'/../../fonts/Anton/Anton-Regular.ttf',
    }
}



# set the default layout here
layout = image_only_centered_whitebkground

