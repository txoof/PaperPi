import os
dir_path = os.path.dirname(os.path.realpath(__file__))


default = {
    'digit_time': {
        'type': 'TextBlock',
        'image': None,
        'max_lines': 3,
        'width': 1,
        'height': 1/2,
        'abs_coordinates': (0, 0),
        'rand': True,
        'font': dir_path+'/../../fonts/Kanit/Kanit-Medium.ttf',
        'fill': 'BLACK',
        'bkground': 'WHITE'
    },
    'msg': {
        'type': 'TextBlock',
        'image': None,
        'max_lines': 4,
        'width': 1,
        'height': 1/2,
        'abs_coordinates': (0, None),
        'relative': ['msg', 'digit_time'],
        'rand': True,
        'font': dir_path+'/../../fonts/Kanit/Kanit-Medium.ttf',
        'fill': 'BLACK',
        'bkground': 'WHITE'
    },
}

# default layout
layout = default
