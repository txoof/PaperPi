# layout for splash screen
import os
dir_path = os.path.dirname(os.path.realpath(__file__))

layout =  {
  'app_name': {
            'type': 'TextBlock',
            'image': None,
            'max_lines': 1,
            'padding': 10,
            'width': 1,
            'height': .6,
            'abs_coordinates': (0, 0),
            'hcenter': True,
            'vcenter': True,
            'rand': False,
            'inverse': False,
            'relative': False,
            'font': dir_path+'/../../fonts/Anton/Anton-Regular.ttf',
            'mode': 'L',
            'font_size': None,
            'bkground': 'WHITE',
            'fill': 'BLACK'
  },

  'version':
          {
           'type': 'TextBlock',
           'image': None,
           'max_lines': 1,
           'padding': 10,
           'width': 1,
           'height': .1,
           'abs_coordinates': (0, None),
           'hcenter': True,
           'vcenter': True,
           'rand': False,
           'inverse': False,
           'relative': ['version', 'app_name'],
           'font': dir_path+'/../../fonts/Dosis/static/Dosis-SemiBold.ttf',
           'font_size': None,
           'mode': 'L',
           'rgb_support': True,
           'bkground': 'WHITE',
           'fill': 'BLACK'
  },

  'url':
          {
           'type': 'TextBlock',              
           'image': None,
           'max_lines': 2,
           'padding': 10,
           'width': 1,
           'height': .3,
           'abs_coordinates': (0, None),
           'hcenter': True,
           'vcenter': True,
           'rand': False,
           'inverse': False,
           'relative': ['url', 'version'],
           'font': dir_path+'/../../fonts/Dosis/static/Dosis-SemiBold.ttf',
           'font_size': None,
           'mode': 'L',
           'bkground': 'WHITE',
           'fill': 'BLACK'}
}
